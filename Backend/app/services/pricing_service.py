from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Base per-endpoint credits costs (update as you like)
DEFAULT_PRICING = {
    "verify.single": 1.0,
    "verify.bulk_per_email": 0.8,
    "decision_maker.search_per_result": 5.0,
    "extractor.single_page": 2.0,
    "extractor.bulk_per_url": 0.5,
    "domain.reputation": 1.0,
    "email_pattern.guess": 0.2,
}

# You can implement persistence in DB later; for now it's in-memory default + optional override via settings
def get_pricing_map() -> Dict[str, float]:
    return DEFAULT_PRICING

def get_cost_for_key(key: str) -> float:
    return float(get_pricing_map().get(key, 0.0))
