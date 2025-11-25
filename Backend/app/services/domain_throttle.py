# backend/app/services/domain_throttle.py
"""
Async domain throttle service.

Provides:
- token-bucket via atomic Lua script: try_consume_tokens(domain, amount=1)
  (useful for rate-limiting / token quotas per domain)
- concurrency-slot (semaphore) API: acquire_slot_async / release_slot_async
  (useful when you want a fixed number of concurrent probes to a domain)

This file uses redis.asyncio. Configure REDIS_URL, token bucket capacity/refill via env.
"""

import os
import math
import time
import logging
from typing import Tuple

import redis.asyncio as redis

logger = logging.getLogger(__name__)
if not logger.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Token bucket defaults
TOKEN_BUCKET_CAPACITY = int(os.getenv("DOMAIN_TOKEN_BUCKET_CAPACITY", "50"))  # tokens
TOKEN_BUCKET_REFILL_PER_SEC = float(os.getenv("DOMAIN_TOKEN_BUCKET_REFILL_PER_SEC", "1.0"))  # tokens/sec

# Concurrency slot defaults
DOMAIN_MAX_CONCURRENCY = int(os.getenv("DOMAIN_MAX_CONCURRENCY", "5"))
SLOT_TTL = int(os.getenv("DOMAIN_SLOT_TTL", "60"))  # seconds - safety TTL for slot keys

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL)
    return _redis_client


# -----------------------------------------------------
# Token-bucket Lua script (atomic)
# Keys:
#   1 -> token_key (e.g. "tb:{domain}")
# ARGV:
#   1 -> capacity (int)
#   2 -> refill_per_sec (float)
#   3 -> now_ts (float seconds)
#   4 -> tokens_to_consume (int)
# Returns:
#   table: [allowed (0/1), tokens_left (float)]
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

-- store new state
local to_store = tostring(now) .. '|' .. tostring(tokens_left)
redis.call('SET', key, to_store)
-- set TTL to cover a few refill intervals (safety)
local ttl = math.ceil(math.max(60, capacity / math.max(1, refill_per_sec) * 2))
redis.call('EXPIRE', key, ttl)

return {allowed, tostring(tokens_left)}
"""


async def try_consume_tokens(domain: str, amount: int = 1,
                             capacity: int = TOKEN_BUCKET_CAPACITY,
                             refill_per_sec: float = TOKEN_BUCKET_REFILL_PER_SEC) -> Tuple[bool, float]:
    """
    Attempt to consume `amount` tokens from the domain token bucket.
    Returns (allowed: bool, tokens_left: float)
    """
    if not domain:
        return False, 0.0
    r = get_redis()
    key = f"tb:{domain}"
    now = time.time()
    try:
        res = await r.eval(_TOKEN_BUCKET_LUA, 1, key, capacity, refill_per_sec, now, amount)
        allowed = bool(int(res[0]))
        tokens_left = float(res[1])
        return allowed, tokens_left
    except Exception as e:
        logger.warning("Token-bucket eval failed for %s: %s", domain, e)
        # Fail-open: allow when Redis fails
        return True, float(capacity)


# -----------------------------------------------------
# Simple concurrency slots (semaphore) implemented with Redis INCR/DECR + TTL
# Keys: "slot:{domain}"
# acquire_slot_async(domain) -> True if allowed, else False
# release_slot_async(domain) -> decrements (safe)
# -----------------------------------------------------
async def acquire_slot_async(domain: str, max_slots: int = DOMAIN_MAX_CONCURRENCY, slot_ttl: int = SLOT_TTL) -> bool:
    """
    Acquire a concurrency slot for the domain. Returns True when slot acquired.
    """
    if not domain:
        return True
    r = get_redis()
    key = f"slot:{domain}"
    try:
        # Use Lua to atomically increment and check limit and set TTL when first created
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
        return bool(int(res))
    except Exception as e:
        logger.warning("acquire_slot_async redis error for %s: %s", domain, e)
        # Fail-open
        return True


async def release_slot_async(domain: str):
    """
    Release a previously acquired slot. Safe to call even if slot may not exist.
    """
    if not domain:
        return
    r = get_redis()
    key = f"slot:{domain}"
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
    except Exception as e:
        logger.warning("release_slot_async redis error for %s: %s", domain, e)
        # best-effort


# Backwards-compatible helpers (sync callers can import these names and await them)
async def acquire(domain: str) -> bool:
    return await acquire_slot_async(domain)


async def release(domain: str):
    await release_slot_async(domain)
