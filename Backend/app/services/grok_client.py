
import requests
import logging
from typing import Dict, Any, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

GROK_ENDPOINT = getattr(settings, "GROK_API_ENDPOINT", None)
GROK_KEY = getattr(settings, "GROK_API_KEY", None)

def grok_enrich_person(name: str, domain: str, existing: Dict[str,Any] = None) -> Dict[str,Any]:
    """
    Use an LLM-like API to enrich or guess titles, bios, LinkedIn, or confirm likely email patterns.
    This is optional and will be a best-effort attempt. Keep usage gated (cost).
    """
    if not GROK_ENDPOINT or not GROK_KEY:
        return {}

    payload = {
        "prompt": f"Given the person name '{name}' at domain '{domain}', suggest likely title, seniority and possible LinkedIn or email patterns. Existing: {existing or {}}",
        "max_tokens": 150,
    }
    headers = {"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(GROK_ENDPOINT, json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            logger.debug("Grok returned %s: %s", r.status_code, r.text)
            return {}
        return r.json()
    except Exception as e:
        logger.exception("Grok request failed: %s", e)
        return {}
