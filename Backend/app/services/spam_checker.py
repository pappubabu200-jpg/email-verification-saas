import re
from typing import List, Optional

# Basic list of known spamtrap domains / role accounts (extend over time)
KNOWN_SPAMTRAP_DOMAINS = {
    "spamtrap.example",  # replace with real known lists if you have them
}

ROLE_ACCOUNT_KEYWORDS = [
    "admin", "administrator", "postmaster", "abuse", "no-reply", "noreply", "support", "info", "sales"
]

def _is_role_account(local_part: str) -> bool:
    lp = (local_part or "").lower()
    for kw in ROLE_ACCOUNT_KEYWORDS:
        if lp == kw or lp.startswith(kw + "+") or lp.startswith(kw + ".") or lp.startswith(kw + "-"):
            return True
        if lp.find(kw) != -1 and len(lp) <= (len(kw) + 8):
            # short matches like admin1, admin2 — treat as role-like
            return True
    return False

def _domain_is_spamtrap(domain: str) -> bool:
    if not domain:
        return False
    d = domain.lower()
    if d in KNOWN_SPAMTRAP_DOMAINS:
        return True
    # common disposable patterns
    if re.search(r"trashmail|tempmail|mailinator|10minutemail|disposable", d):
        return True
    return False

def spam_checks(email: str, smtp_response: Optional[str] = None) -> List[str]:
    """
    Return a list of spam flags.
    """
    flags = []
    if not email:
        return flags
    parts = email.split("@")
    local = parts[0] if len(parts) == 2 else ""
    domain = parts[1] if len(parts) == 2 else ""
    if _is_role_account(local):
        flags.append("role_account")
    if _domain_is_spamtrap(domain):
        flags.append("known_spamtrap_domain")
    # check smtp response text for spamtrap hints
    if smtp_response:
        tr = smtp_response.lower()
        if "spamtrap" in tr or "spam" in tr:
            flags.append("smtp_spam_hint")
    return flags
