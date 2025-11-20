import re
from typing import Optional

# Heuristics to classify bounce messages
HARD_BOUNCE_PATTERNS = [
    r"user unknown",
    r"no such user",
    r"recipient not found",
    r"account does not exist",
    r"550 5\.[12]\.\d",
    r"5\.1\.\d",
    r"mailbox unavailable",
]

SOFT_BOUNCE_PATTERNS = [
    r"greylist",
    r"temporar(y|ily)",
    r"try again later",
    r"4\.2\.\d",
    r"4\.3\.\d",
    r"mailbox full",
    r"over quota",
]

ACCEPT_ALL_PATTERNS = [
    r"accept all",
    r"accepting all addresses",
    r"catch-all",
]

def _match_any(patterns, text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for p in patterns:
        if re.search(p, t):
            return True
    return False

def classify_bounce(code: Optional[int], text: Optional[str]) -> str:
    """
    Return one of: "hard", "soft", "accept_all", "unknown"
    """
    t = (text or "").lower()

    # numeric code heuristics
    if code:
        try:
            c = int(code)
            if 500 <= c < 600:
                return "hard"
            if 400 <= c < 500:
                return "soft"
        except Exception:
            pass

    # textual heuristics
    if _match_any(ACCEPT_ALL_PATTERNS, t):
        return "accept_all"
    if _match_any(HARD_BOUNCE_PATTERNS, t):
        return "hard"
    if _match_any(SOFT_BOUNCE_PATTERNS, t):
        return "soft"

    return "unknown"
