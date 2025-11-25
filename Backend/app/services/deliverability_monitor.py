# backend/app/services/deliverability_monitor.py

import json
import logging
from typing import Dict, Optional

from backend.app.config import settings
from backend.app.services.ip_intelligence import get_mx_ip_info

logger = logging.getLogger(__name__)

# ---------------------------------------------
# REDIS INITIALIZATION
# ---------------------------------------------

try:
    import redis
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None  # full graceful fallback


# ---------------------------------------------
# KEYS
# ---------------------------------------------

DOMAIN_REPUTATION_KEY = "domain:reputation:{}"     # stores JSON
GOOD_KEY = "domain:{}:good"
BAD_KEY = "domain:{}:bad"

REPUTATION_CACHE_TTL = 86400   # 24 hours (optional)


# ---------------------------------------------
# RECORD DOMAIN HISTORY
# ---------------------------------------------

def record_domain_result(domain: str, success: bool):
    """
    Increment historical counters.
    """
    if not REDIS:
        return

    try:
        if success:
            REDIS.incr(GOOD_KEY.format(domain))
        else:
            REDIS.incr(BAD_KEY.format(domain))
    except Exception:
        # NEVER break main verification flow
        pass


# ---------------------------------------------
# COMPUTE DOMAIN REPUTATION SCORE
# ---------------------------------------------

def compute_domain_score(domain: str, mx_host: Optional[str] = None) -> Dict:
    """
    Compute a reputation score from:

    - MX IP trust score
    - Historical good/bad ratio
    - Weighted average against baseline (50)

    Returns:
        {
          "domain": "gmail.com",
          "score": 87,
          "breakdown": { ... }
        }
    """

    score = 50  # baseline
    breakdown = {}

    # -----------------------------
    # MX IP SCORE
    # -----------------------------
    try:
        if mx_host:
            ip_info = get_mx_ip_info(mx_host) or {}
            ip_score = int(ip_info.get("score", 50))   # default 50

            breakdown["mx_ip_info"] = ip_info
            breakdown["mx_ip_score"] = ip_score

            # Weighted merge (MX weight = 0.6)
            score = int((score * 0.4) + (ip_score * 0.6))
    except Exception as e:
        logger.debug("compute_domain_score: mx_ip failed %s", e)

    # -----------------------------
    # HISTORICAL GOOD/BAD SIGNALS
    # -----------------------------
    if REDIS:
        try:
            good_raw = REDIS.get(GOOD_KEY.format(domain))
            bad_raw = REDIS.get(BAD_KEY.format(domain))

            good = int(good_raw.decode() if good_raw else 0)
            bad = int(bad_raw.decode() if bad_raw else 0)

            breakdown["historical_good"] = good
            breakdown["historical_bad"] = bad

            total = good + bad
            if total > 0:
                ratio = good / total
                hist_score = int(ratio * 100)

                breakdown["historical_score"] = hist_score

                # Weighted merge (History weight = 0.5)
                score = int((score * 0.5) + (hist_score * 0.5))

        except Exception as e:
            logger.debug("compute_domain_score: redis read error %s", e)

    # -----------------------------
    # FINAL RESULT OBJECT
    # -----------------------------
    result = {
        "domain": domain,
        "score": int(max(0, min(100, score))),  # clamp between 0–100
        "breakdown": breakdown,
    }

    # Save cache for UI preview / API response
    if REDIS:
        try:
            REDIS.set(
                DOMAIN_REPUTATION_KEY.format(domain),
                json.dumps(result),
                ex=REPUTATION_CACHE_TTL
            )
        except Exception:
            pass

    return result
