import re
from typing import List, Optional

# -----------------------------------------------------------
# Known spamtrap / disposable domains (extend your list here)
# -----------------------------------------------------------

KNOWN_SPAMTRAP_DOMAINS = {
    "spamtrap.example",
    "roottrap.example",
    "seedlist.example",
}

DISPOSABLE_PATTERNS = [
    r"mailinator",
    r"10minutemail",
    r"tempmail",
    r"guerrillamail",
    r"trashmail",
    r"yopmail",
    r"dispostable",
    r"getnada",
    r"fakeinbox",
    r"throwawaymail",
    r"sharklasers",
]

# -----------------------------------------------------------
# Role account detection — high bounce + low engagement
# -----------------------------------------------------------

ROLE_ACCOUNT_KEYWORDS = [
    "admin", "administrator", "postmaster", "root",
    "abuse", "support", "helpdesk", "info", "sales",
    "billing", "contact", "office", "team",
    "no-reply", "noreply", "donotreply",
]


def _is_role_account(local: str) -> bool:
    """
    Detects addresses like:
    - admin@example.com
    - support@example.com
    - info+abc@example.com
    """
    lp = (local or "").lower()

    for kw in ROLE_ACCOUNT_KEYWORDS:
        # Exact match (most important)
        if lp == kw:
            return True

        # Variants: support+tag, admin.test, info-xyz
        if lp.startswith(f"{kw}+") or lp.startswith(f"{kw}.") or lp.startswith(f"{kw}-"):
            return True

        # Partial match for short variants (admin1, abuse2)
        if lp.startswith(kw) and len(lp) <= len(kw) + 2:
            return True

    return False


# -----------------------------------------------------------
# Domain spamtrap detection
# -----------------------------------------------------------

def _domain_is_spamtrap(domain: str) -> bool:
    if not domain:
        return False

    domain = domain.lower()

    # Direct block list (manual)
    if domain in KNOWN_SPAMTRAP_DOMAINS:
        return True

    # Check disposable / high-risk patterns
    for p in DISPOSABLE_PATTERNS:
        if re.search(p, domain):
            return True

    # Common spam-service patterns
    if re.search(r"(spm|trap|blocklist|blackhole)", domain):
        return True

    return False


# -----------------------------------------------------------
# Main spam checker
# -----------------------------------------------------------

def spam_checks(email: str, smtp_response: Optional[str] = None) -> List[str]:
    """
    Returns list of spam flags:
        - role_account
        - known_spamtrap_domain
        - disposable_domain
        - smtp_spam_hint
        - suspicious_format
    """
    flags = []

    if not email or "@" not in email:
        return flags

    local, domain = email.split("@", 1)

    # 1. Role account detection
    if _is_role_account(local):
        flags.append("role_account")

    # 2. Spamtrap or disposable domain
    if _domain_is_spamtrap(domain):
        flags.append("known_spamtrap_domain")

        # More granular flag
        for p in DISPOSABLE_PATTERNS:
            if re.search(p, domain):
                flags.append("disposable_domain")
                break

    # 3. SMTP response hints
    if smtp_response:
        txt = smtp_response.lower()

        if "spamtrap" in txt:
            flags.append("smtp_spamtrap_hint")
        if "spam" in txt or "listed" in txt or "block" in txt:
            flags.append("smtp_spam_hint")

    # 4. Suspicious local-part format
    if re.match(r"^[a-z0-9]{1,4}$", local):  # too short
        flags.append("suspicious_format")
    if re.search(r"\.\.|--|__", local):  # repeated separators
        flags.append("suspicious_format")

    return flags
