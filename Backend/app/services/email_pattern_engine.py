# backend/app/services/email_pattern_engine.py

import re
from typing import List, Dict, Tuple

# Weighted pattern ranking — learned from industry datasets
PATTERN_WEIGHTS = [
    ("%f.%l", 0.32),
    ("%f%l",   0.25),
    ("%f_%l",  0.05),
    ("%f",     0.05),
    ("%l",     0.03),
    ("%f.%l0", 0.03),
    ("%f0.%l", 0.02),
    ("%f%l0",  0.02),
    ("%f.%l",  0.32),
    ("%fi.%l", 0.04),
    ("%f_%li", 0.04),
    ("%f-%l",  0.02)
]

def _format(pattern: str, f: str, l: str) -> str:
    """Replace pattern tokens with actual names."""
    return (
        pattern
        .replace("%f", f)
        .replace("%l", l)
        .replace("%fi", f[0] if f else "")
        .replace("%li", l[0] if l else "")
    )


def generate_patterns(first: str, last: str, domain: str) -> List[str]:
    """
    Generate all common corporate email patterns ranked by likelihood.
    Example:
        John Doe @ example.com ->
        [
            "john.doe@example.com",
            "johndoe@example.com",
            "j.doe@example.com",
            ...
        ]
    """
    f = (first or "").strip().lower()
    l = (last or "").strip().lower()
    d = (domain or "").strip().lower()

    if not d:
        return []

    patterns = []

    for pattern, weight in PATTERN_WEIGHTS:
        email = _format(pattern, f, l)
        if email and "@" not in email:
            patterns.append((f"{email}@{d}", weight))

    # Deduplicate while respecting weight
    seen = set()
    ranked = []
    for email, w in patterns:
        if email not in seen:
            seen.add(email)
            ranked.append((email, w))

    # Sort high → low confidence
    ranked.sort(key=lambda x: x[1], reverse=True)

    # Return only email strings
    return [r[0] for r in ranked]


def score_email_pattern(email: str) -> int:
    """
    Assign a confidence score based on how common the pattern is.
    0 - 100 score 
    Example:
        john.doe@example.com → 90
        jd@example.com        → 70
        random123@example.com → 30
    """
    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return 0

    # Highly professional patterns
    if re.match(r"^[a-z]+\.[a-z]+$", local):
        return 90
    if re.match(r"^[a-z]+[a-z]+$", local):
        return 80
    if re.match(r"^[a-z]\.[a-z]+$", local):
        return 75
    if re.match(r"^[a-z][a-z]+[0-9]$", local):
        return 65
    if re.match(r"^[a-z]{1}$", local):  # single letter
        return 40

    # Contains digits or random
    if re.search(r"\d", local):
        return 40

    # complex or non-standard
    return 50
