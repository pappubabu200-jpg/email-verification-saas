# backend/app/services/bounce_classifier.py
# ULTIMATE BOUNCE CLASSIFIER — 2025 EDITION
# Now with 100+ patterns from Gmail, Outlook, Yahoo, Zoho, GoDaddy, Hostinger, AWS SES, SendGrid, etc.

import re
from typing import Optional, List

def _compile(patterns: List[str]):
    return [re.compile(p, re.IGNORECASE) for p in patterns]

# ===================================================================
# HARD BOUNCE — PERMANENT FAILURE
# ===================================================================
HARD_BOUNCE_PATTERNS = _compile([
    r"user unknown",
    r"no such user",
    r"recipient not found",
    r"unknown recipient",
    r"invalid recipient",
    r"mailbox unavailable",
    r"account does not exist",
    r"address rejected",
    r"does not exist",
    r"no mailbox here",
    r"user doesn\'t exist",
    r"undeliverable",
    r"550 5\.[012]\.",
    r"550 permanent failure",
    r"551 user not local",
    r"552 mailbox full.*permanent",
    r"553 mailbox name not allowed",
    r"554 no valid recipients",
    r"delivery failed.*permanently",
    r"recipient address rejected",
    r"unknown local user",
    r"mailbox not found",
    rfc822",
    r"rejected: user not found",
    r"invalid mailbox",
    r"account disabled",
    r"account inactive",
    r"user disabled",
    r"blocked address",
])

# ===================================================================
# SOFT BOUNCE — TEMPORARY FAILURE
# ===================================================================
SOFT_BOUNCE_PATTERNS = _compile([
    r"temporary failure",
    r"temporarily deferred",
    r"temporarily unavailable",
    r"try again later",
    r"greylisted",
    r"greylisting",
    r"mailbox full",
    r"over quota",
    r"quota exceeded",
    r"inbox is full",
    r"storage full",
    r"server busy",
    r"rate limit",
    r"too many connections",
    r"connection refused",
    r"connection timed out",
    r"421.*service not available",
    r"421.*too many concurrent",
    r"450.*greylisted",
    r"451.*temporary",
    r"452.*storage",
    r"4\.3\.\d",
    r"4\.4\.\d",
    r"4\.7\.\d",
    r"retry timeout exceeded",
    r"message expired",
    r"delivery time expired",
])

# ===================================================================
# ACCEPT-ALL / CATCH-ALL DOMAINS
# ===================================================================
ACCEPT_ALL_PATTERNS = _compile([
    r"catch[- ]?all",
    r"accept all",
    r"accepting all mail",
    r"undetermined users accepted",
    r"all recipients accepted",
    r"server accepts any recipient",
    r"will accept any address",
    r"role account",
    r"generic mailbox",
    r"abuse@.*accepted",
    r"postmaster@.*accepted",
])

# ===================================================================
# ISP-SPECIFIC SMART RULES (2024–2025 REAL-WORLD DATA)
# ===================================================================

# GMAIL / GOOGLE WORKSPACE
GMAIL_HARD = _compile([
    r"550-5\.1\.1",
    r"550 5\.1\.1.*user doesn\'t exist",
    r"r"gmail.*no such user",
    r"the email account that you tried to reach does not exist",
    r"550.*requested action not taken: mailbox unavailable",
])

# MICROSOFT 365 / OUTLOOK / HOTMAIL
MICROSOFT_HARD = _compile([
    r"550 5\.4\.1",
    r"550 5\.1\.1.*recipient address rejected",
    r"550 5\.2\.1.*mailbox disabled",
    r"550 5\.4\.316.*message expired",
    r"recipient address rejected: access denied",
    r"user unknown in local recipient table",
])
MICROSOFT_SOFT = _compile([
    r"421 4\.3\.2",
    r"421 rp-00.*too many connections",
    r"432 4\.3\.2.*concurrent connections",
    r"4\.7\.1.*try again later",
])

# YAHOO / AOL / VERIZON
YAHOO_HARD = _compile([
    r"554 5\.7\.9.*message not allowed",
    r"554 delivery error:.*user unknown",
    r"554.*invalid recipient",
])
YAHOO_SOFT = _compile([
    r"421 4\.7\.0.*temporary failure",
    r"421 message temporarily deferred",
    r"421 too many messages",
])

# ZOHO MAIL
ZOHO_HARD = _compile([
    r"550.*user not found",
    r"550.*invalid recipient",
    r"mail rejected.*zoho",
    r"not authorized to connect",
])
ZOHO_SOFT = _compile([
    r"421.*too many sessions",
    r"452.*storage full",
    r"temporary authentication failure",
])

# GODADDY / SECURESERVER
GODADDY_HARD = _compile([
    r"550.*#5\.1\.1",
    r"550.*mailbox not found",
    r"550.*recipient rejected",
])
GODADDY_SOFT = _compile([
    r"421.*service unavailable",
    r"452.*too many recipients",
])

# AWS SES
AWS_SES_HARD = _compile([
    r"550-5\.1\.1",
    r"mailbox unavailable.*amazon ses",
    r"recipient rejected by server",
])
AWS_SES_SOFT = _compile([
    r"454 throttling",
    r"421 rate control",
    r"too many concurrent",
])

# SENDGRID
SENDGRID_HARD = _compile([
    r"550.*unrouteable",
    r"550.*invalid mailbox",
])
SENDGRID_SOFT = _compile([
    r"421.*try again",
    r"429.*too many requests",
])

# HOSTINGER / 1&1 IONOS NAMECHEAP
HOSTINGER_IONOS = _compile([
    r"550.*no such user here",
    r"550.*mailbox not found",
    r"554.*delivery error",
    r"550.*account suspended",
])

# INDIAN ISPs (Rediff, BSNL, etc.)
INDIAN_ISPS = _compile([
    r"550.*user not found",
    r"553.*mailbox name invalid",
    r"550.*recipient rejected",
])

# ===================================================================
# MAIN CLASSIFIER — ULTRA ACCURATE
# ===================================================================

def classify_bounce(code: Optional[int], text: Optional[str]) -> str:
    t = (text or "").lower().strip()

    # 1. SMTP code fast path
    if code:
        if 500 <= code < 600:
            return "hard"
        if 400 <= code < 500:
            return "soft"

    # 2. ISP-specific overrides (highest priority)
    if any(p.search(t) for p in (
        GMAIL_HARD + MICROSOFT_HARD + YAHOO_HARD + ZOHO_HARD +
        GODADDY_HARD + AWS_SES_HARD + SENDGRID_HARD + HOSTINGER_IONOS + INDIAN_ISPS
    )):
        return "hard"

    if any(p.search(t) for p in (
        MICROSOFT_SOFT + YAHOO_SOFT + ZOHO_SOFT + GODADDY_SOFT +
        AWS_SES_SOFT + SENDGRID_SOFT
    )):
        return "soft"

    # 3. Accept-all / catch-all
    if _match_any(ACCEPT_ALL_PATTERNS, t):
        return "accept_all"

    # 4. Generic hard/soft
    if _match_any(HARD_BOUNCE_PATTERNS, t):
        return "hard"
    if _match_any(SOFT_BOUNCE_PATTERNS, t):
        return "soft"

    # 5. Fallback
    return "unknown"


def _match_any(patterns: List[re.Pattern], text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in patterns)
