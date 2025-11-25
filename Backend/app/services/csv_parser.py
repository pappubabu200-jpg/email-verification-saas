# backend/app/services/csv_parser.py

import io
import csv
import re
from typing import List, Optional

# Strict but flexible email regex (fast + production safe)
EMAIL_REGEX = re.compile(
    r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$",
    re.IGNORECASE
)


def extract_emails_from_csv_bytes(
    content: bytes,
    header_names: Optional[List[str]] = None
) -> List[str]:
    """
    Parse CSV bytes and extract valid emails.

    Enhancements:
    - strict regex validation
    - header filtering (email, Email, E-mail…)
    - supports arbitrary CSV delimiters
    - removes duplicates (case-insensitive)
    """

    # decode safely
    text = content.decode("utf-8", errors="ignore")

    # Allow automatic delimiter detection
    try:
        sample = text[:1024]
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        dialect = csv.excel  # fallback

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    out: List[str] = []
    seen = set()

    # Normalize header names early
    header_set = {h.lower(): True for h in header_names} if header_names else {}

    for row in reader:
        if not row:
            continue

        for k, v in row.items():
            if not v:
                continue

            # clean value
            value = str(v).strip()

            key_lower = (k or "").strip().lower()

            # If header_names provided, apply strict match
            if header_names and key_lower in header_set:
                email = value.lower()
                if EMAIL_REGEX.match(email) and email not in seen:
                    seen.add(email)
                    out.append(email)
                continue

            # Default heuristics
            if "email" in key_lower or "@" in value:
                email = value.lower()
                if EMAIL_REGEX.match(email) and email not in seen:
                    seen.add(email)
                    out.append(email)

    return out
