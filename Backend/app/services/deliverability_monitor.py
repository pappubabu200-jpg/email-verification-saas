import logging
from typing import Dict, Optional

try:
    import redis
    REDIS = redis.from_url("redis://redis:6379/0")
except Exception:
    REDIS = None

from backend.app.services.ip_intelligence import get_mx_ip_info

logger = logging.getLogger(__name__)

# Keys and scoring rules
DOMAIN_REPUTATION_KEY = "domain:reputation:{}"  # domain -> JSON object (score, last_updated)


def compute_domain_score(domain: str, mx_host: Optional[str] = None) -> Dict:
    """
    Compute a domain reputation score combining:
     - MX IP score
     - historical positives/negatives from Redis counters (if available)
    Returns: {domain, score, breakdown}
    """
    breakdown = {}
    score = 50  # baseline

    if mx_host:
        ip_info = get_mx_ip_info(mx_host)
        breakdown["mx_ip_score"] = ip_info.get("score", 50)
        score = int((score + ip_info.get("score", 50)) / 2)

    # historical metrics (if Redis available)
    if REDIS:
        try:
            good = int(REDIS.get(f"domain:{domain}:good") or 0)
            bad = int(REDIS.get(f"domain:{domain}:bad") or 0)
            total = good + bad
            breakdown["historical_good"] = good
            breakdown["historical_bad"] = bad
            if total > 0:
                ratio = good / total
                hist_score = int(ratio * 100)
                score = int((score + hist_score) / 2)
                breakdown["historical_score"] = hist_score
        except Exception as e:
            logger.debug("deliverability_monitor: redis read error %s", e)

    result = {"domain": domain, "score": int(score), "breakdown": breakdown}
    # Save to redis for quick access
    if REDIS:
        try:
            REDIS.set(DOMAIN_REPUTATION_KEY.format(domain), str(result))
        except Exception:
            pass
    return result


def record_domain_result(domain: str, success: bool):
    """
    Call this after each verification to update historical counters.
    success=True increments good, else increments bad.
    """
    if not REDIS:
        return
    try:
        if success:
            REDIS.incr(f"domain:{domain}:good")
        else:
            REDIS.incr(f"domain:{domain}:bad")
    except Exception:
        pass
