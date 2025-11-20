import io
import csv
from typing import List

def extract_emails_from_csv_bytes(content: bytes, header_names: List[str] = None) -> List[str]:
    """
    Parse CSV bytes and extract obvious email columns.
    header_names (optional) can be a list of header names to focus on (e.g., ['email','Email','e-mail'])
    """
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    emails = []
    for row in reader:
        for k, v in row.items():
            if not v:
                continue
            key_lower = (k or "").strip().lower()
            if header_names:
                if key_lower in [h.lower() for h in header_names]:
                    emails.append(v.strip())
                    continue
            # default heuristic: header contains 'email' or value contains '@'
            if "email" in key_lower or "@" in v:
                emails.append(v.strip())
    # final cleanup: unique and filter
    uniq = []
    seen = set()
    for e in emails:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq
