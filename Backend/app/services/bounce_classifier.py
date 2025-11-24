# backend/app/services/bounce_classifier.py

import re
from typing import Optional, List

# ---------------------------------------------------------
# PRE-COMPILED REGEX (faster)
# ---------------------------------------------------------

def _compile(patterns: List[str]):
    return [re.compile(p, re.IGNORECASE) for p in patterns]

HARD_BOUNCE_PATTERNS = _compile([
    r"user unknown",
    r"no such user",
    r"recipient not found",
    r"account does not exist",
    r"mailbox unavailable",
    r"invalid recipient",
    r"address rejected",
    r"does not like recipient",
    r"no mailbox here",
    r"5\.1\.\d",
    r"5\.2\.\d",
    r"550 5\.[12]\.\d",
    r"550 permanent failure",
    r"recipient address rejected",
    r"unknown user",
])

SOFT_BOUNCE_PATTERNS = _compile([
    r"greylist",
    r"temporar(y|ily)",
    r"try again later",
    r"mailbox full",
    r"over quota",
    r"server busy",
    r"rate limited",
    r"resources temporarily unavailable",
    r"4\.2\.\d",
    r"4\.3\.\d",
    r"temporary failure",
    r"connection timed out",
])

ACCEPT_ALL_PATTERNS = _compile([
    r"accept all",
    r"accepting all addresses",
    r"catch[- ]?all",
    r"server will accept ANY address",
    r"undetermined users accepted",
])

# ISP-specific smart rules
GMAIL_HARD = _compile([r"550-5\.1\.1", r"gmail user not found"])
OUTLOOK_SOFT = _compile([r"421 4\.3\.2", r"service not available"])
YAHOO_TEMP = _compile([r"421 4\.7\.0", r"temporarily deferred"])
ZOHO_BLOCK = _compile([r"mail rejected .* zoho", r"not authorized to connect"])


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def _match_any(patterns: List[re.Pattern], text: str) -> bool:
    if not text:
        return False
    for p in patterns:
        if p.search(text):
            return True
    return False


# ---------------------------------------------------------
# CLASSIFIER
# ---------------------------------------------------------

def classify_bounce(code: Optional[int], text: Optional[str]) -> str:
    """
    Classify bounce type:
        - hard
        - soft
        - accept_all
        - unknown

    Combines:
        - SMTP numeric codes
        - Regex heuristics
        - Provider-specific logic
    """

    t = (text or "").lower()

    # -------------------------------------------------
    # SMTP numeric code rules
    # -------------------------------------------------
    if code:
        try:
            c = int(code)
            if 500 <= c < 600:
                return "hard"
            if 400 <= c < 500:
                return "soft"
        except Exception:
            pass

    # -------------------------------------------------
    # Provider-specific smart rules
    # -------------------------------------------------
    if _match_any(GMAIL_HARD, t):
        return "hard"
    if _match_any(OUTLOOK_SOFT, t):
        return "soft"
    if _match_any(YAHOO_TEMP, t):
        return "soft"
    if _match_any(ZOHO_BLOCK, t):
        return "hard"

    # -------------------------------------------------
    # Accept-all domain heuristics
    # -------------------------------------------------
    if _match_any(ACCEPT_ALL_PATTERNS, t):
        return "accept_all"

    # -------------------------------------------------
    # Generic hard/soft bounce patterns
    # -------------------------------------------------
    if _match_any(HARD_BOUNCE_PATTERNS, t):
        return "hard"

    if _match_any(SOFT_BOUNCE_PATTERNS, t):
        return "soft"

    # -------------------------------------------------
    # Default fallback
    # -------------------------------------------------
    return "unknown"
