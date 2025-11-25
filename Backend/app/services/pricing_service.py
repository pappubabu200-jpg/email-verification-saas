# backend/app/services/pricing_service.py

import logging
from decimal import Decimal
from typing import Dict

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# BASE PRICING TABLE (DEFAULT)
# ---------------------------------------------------------

DEFAULT_PRICING: Dict[str, Decimal] = {
    "verify.single": Decimal("1.0"),
    "verify.bulk_per_email": Decimal("0.8"),
    "decision_maker.search_per_result": Decimal("5.0"),
    "extractor.single_page": Decimal("2.0"),
    "extractor.bulk_per_url": Decimal("0.5"),
    "domain.reputation": Decimal("1.0"),
    "email_pattern.guess": Decimal("0.2"),
}

# ---------------------------------------------------------
# OPTIONAL SETTINGS OVERRIDES (ENV)
# ---------------------------------------------------------
# Example:
# PRICING_OVERRIDE = {
#   "verify.single": "1.2",
#   "extractor.single_page": "3.0"
# }

PRICING_OVERRIDE = getattr(settings, "PRICING_OVERRIDE", {}) or {}


def get_pricing_map() -> Dict[str, Decimal]:
    """
    Returns final computed pricing map:
        DEFAULT_PRICING → overridden by environment (if provided)
    """
    pricing = DEFAULT_PRICING.copy()

    # apply environment overrides
    try:
        for k, v in PRICING_OVERRIDE.items():
            pricing[k] = Decimal(str(v))
    except Exception as e:
        logger.error("Invalid pricing override in settings: %s", e)

    return pricing


def get_cost_for_key(key: str) -> Decimal:
    """
    Get cost for an operation.
    Returns Decimal("0") if key unknown.
    """
    try:
        return get_pricing_map().get(key, Decimal("0"))
    except Exception as e:
        logger.error("Invalid pricing lookup for '%s': %s", key, e)
        return Decimal("0")
