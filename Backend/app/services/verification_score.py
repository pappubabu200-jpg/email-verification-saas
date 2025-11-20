from typing import Dict

def score_verification(probe_result: Dict) -> Dict:
    """
    Simple rule-based scoring:
      - rcpt_code 2xx => valid
      - rcpt_code 4xx => unknown / greylist
      - rcpt_code 5xx => invalid
    Returns dict containing 'status' and 'risk_score' and 'details'
    """
    rc = probe_result.get("rcpt_code")
    details = probe_result.copy()

    try:
        rc_int = int(rc) if rc is not None else None
    except Exception:
        rc_int = None

    if rc_int and 200 <= rc_int < 300:
        return {"status": "valid", "risk_score": 5, "details": details}
    if rc_int and 400 <= rc_int < 500:
        # 4xx often temporary (greylist)
        return {"status": "unknown", "risk_score": 50, "details": details}
    # default invalid
    return {"status": "invalid", "risk_score": 95, "details": details}
