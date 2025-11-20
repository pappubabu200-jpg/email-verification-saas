from typing import List, Dict
import re

def common_patterns(first: str, last: str, domain: str) -> List[str]:
    """
    Generate email patterns (lowercase) commonly used.
    Returns candidates ordered by likelihood.
    """
    f = (first or "").strip().lower()
    l = (last or "").strip().lower()
    d = (domain or "").strip().lower()
    if not d:
        return []

    candidates = []
    # Basic combos
    if f and l:
        candidates.extend([
            f"{f}.{l}@{d}",
            f"{f}{l}@{d}",
            f"{f[0]}{l}@{d}",
            f"{f}.{l[0]}@{d}",
            f"{f[0]}.{l}@{d}",
            f"{l}.{f}@{d}",
            f"{f}@{d}"
        ])
    elif f:
        candidates.append(f"{f}@{d}")
        candidates.append(f"{f[0]}@{d}")
    elif l:
        candidates.append(f"{l}@{d}")

    # normalize duplicates & filter
    seen = set()
    out = []
    for c in candidates:
        c = re.sub(r"\s+", "", c)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
