# backend/app/services/csv_parser.py

import io
import csv
import re
from typing import List, Optional, Set

# More accurate email regex - accepts longer TLDs, underscores, etc.
# Still fast, safe, and rejects most garbage
EMAIL_REGEX = re.compile(
    r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
)

# Alternative: use the official regex from the HTML5 spec (very permissive but correct)
# EMAIL_REGEX = re.compile(r"^[\w!#$%&'*+/=?`{|}~^-]+(?:\.[\w!#$%&'*+/=?`{|}~^-]+)*@"
#                          r"(?:[A-Z0-9-]+\.)+[A-Z]{2,}$", re.IGNORECASE)


def _normalize_headers(header_names: Optional[List[str]]) -> Set[str]:
    """Normalize expected header names to lowercase set for O(1) lookup."""
    if not header_names:
        return set()
    return {name.strip().lower() for name in header_names if name}


def _is_likely_email_column(header: str) -> bool:
    """Heuristic: does this header look like an email column?"""
    header = header.lower()
    return any(keyword in header for keyword in ("email", "e-mail", "mail", "courriel", "correo"))


def extract_emails_from_csv_bytes(
    content: bytes,
    header_names: Optional[List[str]] = None,
    max_sample_size: int = 8192,
) -> List[str]:
    """
    Extract valid, unique email addresses from CSV bytes.

    Features:
    - Auto-detects delimiter (comma, semicolon, tab, etc.)
    - Supports custom header names (e.g. ["Contact Email", "user_email"])
    - Robust email validation
    - Case-insensitive deduplication
    - Handles messy real-world CSVs gracefully

    Args:
        content: Raw CSV bytes
        header_names: Optional list of column names that contain emails
        max_sample_size: Size of sample used for dialect sniffing

    Returns:
        List of unique lowercase emails
    """
    try:
        text = content.decode("utf-8-sig")  # Handles BOM correctly
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    # Improve dialect detection reliability
    sample = text[:max_sample_size]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|:")  # Common delimiters
        if not csv.Sniffer().has_header(sample):
            # If no header detected, fall back to excel (common in exports)
            dialect = csv.excel
    except csv.Error:
        dialect = csv.excel  # Most common fallback

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    expected_headers = _normalize_headers(header_names)

    seen: Set[str] = set()
    emails: List[str] = []

    for row in reader:
        if not row:
            continue

        for raw_key, value in row.items():
            if not value or not isinstance(value, str):
                continue

            cell = value.strip()
            if not cell:
                continue

            key = (raw_key or "").strip()
            key_lower = key.lower()

            # Priority 1: Explicit header match
            if expected_headers and key_lower in expected_headers:
                candidate = cell.lower()
                if EMAIL_REGEX.match(candidate) and candidate not in seen:
                    seen.add(candidate)
                    emails.append(candidate)
                continue  # Don't double-check this cell

            # Priority 2: Header looks like email column
            if _is_likely_email_column(key):
                candidate = cell.lower()
                if EMAIL_REGEX.match(candidate) and candidate not in seen:
                    seen.add(candidate)
                    emails.append(candidate)

            # Priority 3: Cell itself looks like an email (fallback)
            elif "@" in cell and "." in cell.split("@")[-1]:
                candidate = cell.lower()
                if EMAIL_REGEX.match(candidate) and candidate not in seen:
                    seen.add(candidate)
                    emails.append(candidate)

    return emails
