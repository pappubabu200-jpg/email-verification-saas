# backend/app/services/domain_throttle.py

"""
Async domain throttle service.

Instrumentation added with Prometheus:
 - Token bucket metrics (allow/deny/tokens_left/errors)
 - Slot concurrency metrics (acquire/release/in_use)
 - Latency histograms
"""

import os
import math
import time
import logging
from typing import Tuple

import redis.asyncio as redis
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)
if not logger.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# -----------------------------------------------------
# Prometheus Metrics
# -----------------------------------------------------
DOMAIN_TOKEN_BUCKET_TOTAL = Counter(
    "domain_token_bucket_total",
    "Token bucket consumption attempts",
    ["domain", "allowed"]  # allowed=yes/no
)

DOMAIN_TOKENS_LEFT = Gauge(
    "domain_tokens_left",
    "Current estimated tokens left for domain",
    ["domain"]
)

DOMAIN_TOKEN_BUCKET_FAILURES = Counter(
    "domain_token_bucket_failures_total",
    "Token bucket failures due to Redis/Lua errors",
    ["domain"]
)

DOMAIN_THROTTLE_LATENCY = Histogram(
    "domain_throttle_latency_seconds",
    "Latency of throttle operations",
    ["operation"]  # token_bucket / acquire / release
)

DOMAIN_SLOT_ACQUIRE_TOTAL = Counter(
    "domain_slot_acquire_total",
    "Slot acquire decisions",
    ["domain", "result"]  # granted / denied / error
)

DOMAIN_SLOTS_IN_USE = Gauge(
    "domain_slots_in_use",
    "Number of concurrent slots in use for a domain",
    ["domain"]
)

DOMAIN_SLOT_RELEASE_TOTAL = Counter(
    "domain_slot_release_total",
    "Slot releases",
    ["domain", "result"]  # ok / error
)

# -----------------------------------------------------
# Environment Vars
# -----------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

TOKEN_BUCKET_CAPACITY = int(os.getenv("DOMAIN_TOKEN_BUCKET_CAPACITY", "50"))
TOKEN_BUCKET_REFILL_PER_SEC = float(os.getenv("DOMAIN_TOKEN_BUCKET_REFILL_PER_SEC", "1.0"))

DOMAIN_MAX_CONCURRENCY = int(os.getenv("DOMAIN_MAX_CONCURRENCY", "5"))
SLOT_TTL = int(os.getenv("DOMAIN_SLOT_TTL", "60"))

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL)
    return _redis_client


# -----------------------------------------------------
# Token-Bucket Lua
# -----------------------------------------------------
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local to_consume = tonumber(ARGV[4])

-- stored as: last_ts|tokens
local cur = redis.call('GET', key)
local last_ts = 0
local tokens = capacity

if cur then
  local sep = string.find(cur, "|")
  if sep then
    last_ts = tonumber(string.sub(cur, 1, sep - 1)) or 0
    tokens = tonumber(string.sub(cur, sep + 1)) or capacity
  end
end

local delta = math.max(0, now - last_ts)
local refill = delta * refill_per_sec
tokens = math.min(capacity, tokens + refill)
local allowed = 0
local tokens_left = tokens

if tokens >= to_consume then
  tokens_left = tokens - to_consume
  allowed = 1
end

local to_store = tostring(now) .. '|' .. tostring(tokens_left)
redis.call('SET', key, to_store)
local ttl = math.ceil(math.max(60, capacity / math.max(1, refill_per_sec) * 2))
redis.call('EXPIRE', key, ttl)

return {allowed, tostring(tokens_left)}
"""


async def try_consume_tokens(domain: str, amount: int = 1,
                             capacity: int = TOKEN_BUCKET_CAPACITY,
                             refill_per_sec: float = TOKEN_BUCKET_REFILL_PER_SEC) -> Tuple[bool, float]:

    if not domain:
        return False, 0.0

    r = get_redis()
    key = f"tb:{domain}"
    now = time.time()

    with DOMAIN_THROTTLE_LATENCY.labels(operation="token_bucket").time():
        try:
            res = await r.eval(_TOKEN_BUCKET_LUA, 1, key, capacity, refill_per_sec, now, amount)
            allowed = bool(int(res[0]))
            tokens_left = float(res[1])

            DOMAIN_TOKEN_BUCKET_TOTAL.labels(domain=domain, allowed="yes" if allowed else "no").inc()
            DOMAIN_TOKENS_LEFT.labels(domain=domain).set(tokens_left)

            return allowed, tokens_left

        except Exception as e:
            logger.warning("Token-bucket eval failed for %s: %s", domain, e)
            DOMAIN_TOKEN_BUCKET_FAILURES.labels(domain=domain).inc()

            # Fail-open behavior
            DOMAIN_TOKEN_BUCKET_TOTAL.labels(domain=domain, allowed="yes").inc()
            DOMAIN_TOKENS_LEFT.labels(domain=domain).set(capacity)

            return True, float(capacity)


# -----------------------------------------------------
# Concurrency Slot Control
# -----------------------------------------------------
async def acquire_slot_async(domain: str,
                             max_slots: int = DOMAIN_MAX_CONCURRENCY,
                             slot_ttl: int = SLOT_TTL) -> bool:
    if not domain:
        return True

    r = get_redis()
    key = f"slot:{domain}"

    with DOMAIN_THROTTLE_LATENCY.labels(operation="acquire").time():
        try:
            lua = """
            local k = KEYS[1]
            local max = tonumber(ARGV[1])
            local ttl = tonumber(ARGV[2])
            local cur = redis.call('INCR', k)
            if tonumber(cur) == 1 then
                redis.call('EXPIRE', k, ttl)
            end
            if tonumber(cur) > max then
                redis.call('DECR', k)
                return 0
            end
            return 1
            """
            res = await r.eval(lua, 1, key, max_slots, slot_ttl)
            ok = bool(int(res))

            if ok:
                DOMAIN_SLOT_ACQUIRE_TOTAL.labels(domain=domain, result="granted").inc()
                DOMAIN_SLOTS_IN_USE.labels(domain=domain).inc()
            else:
                DOMAIN_SLOT_ACQUIRE_TOTAL.labels(domain=domain, result="denied").inc()

            return ok

        except Exception as e:
            logger.warning("acquire_slot_async redis error for %s: %s", domain, e)
            DOMAIN_SLOT_ACQUIRE_TOTAL.labels(domain=domain, result="error").inc()
            # fail-open
            DOMAIN_SLOTS_IN_USE.labels(domain=domain).inc()
            return True


async def release_slot_async(domain: str):
    if not domain:
        return

    r = get_redis()
    key = f"slot:{domain}"

    with DOMAIN_THROTTLE_LATENCY.labels(operation="release").time():
        try:
            lua = """
            local k = KEYS[1]
            if redis.call('EXISTS', k) == 0 then
                return 0
            end
            local cur = redis.call('DECR', k)
            if tonumber(cur) <= 0 then
                redis.call('DEL', k)
            end
            return 1
            """
            await r.eval(lua, 1, key)

            DOMAIN_SLOT_RELEASE_TOTAL.labels(domain=domain, result="ok").inc()
            DOMAIN_SLOTS_IN_USE.labels(domain=domain).dec()

        except Exception as e:
            logger.warning("release_slot_async redis error for %s: %s", domain, e)
            DOMAIN_SLOT_RELEASE_TOTAL.labels(domain=domain, result="error").inc()
            # best effort


# backwards compatible API
async def acquire(domain: str) -> bool:
    return await acquire_slot_async(domain)

async def release(domain: str):
    await release_slot_async(domain)
