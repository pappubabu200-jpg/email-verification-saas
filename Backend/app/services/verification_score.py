from typing import Dict, Any

# Score weights (adjust for your system)
WEIGHTS = {
    "valid_bonus": 30,
    "invalid_penalty": 40,
    "greylist_penalty": 10,
    "role_penalty": 10,
    "spam_penalty": 20,
    "disposable_penalty": 30,
    "smtp_spam_penalty": 15,
    "domain_reputation_weight": 0.5,
    "ip_reputation_weight": 0.5,
}


def score_verification(probe: Dict[str, Any]) -> Dict:
    """
    Production-grade scoring engine.
    
    Input: smtp_probe result
    Output:
        {
            status: "valid" | "invalid" | "unknown",
            risk_score: 0–100,
            details: {... merged payload ...}
        }
    """

    # Base score: 50 = neutral
    score = 50
    status = "unknown"

    rc = probe.get("rcpt_code")
    spam_flags = probe.get("spam_flags", [])
    bounce_class = probe.get("bounce_class")
    ip_info = probe.get("ip_info") or {}
    domain_rep = probe.get("domain_reputation") or {}
    mx_score = domain_rep.get("score", 50)

    # ----------------------------
    # 1. RCPT Code Scoring
    # ----------------------------
    try:
        rc_int = int(rc) if rc is not None else None
    except:
        rc_int = None

    if rc_int:
        if 200 <= rc_int < 300:
            status = "valid"
            score += WEIGHTS["valid_bonus"]
        elif 400 <= rc_int < 500:
            status = "unknown"
            score -= WEIGHTS["greylist_penalty"]
        elif 500 <= rc_int < 600:
            status = "invalid"
            score += WEIGHTS["invalid_penalty"]

    # ----------------------------
    # 2. Disposable or Spam Flags
    # ----------------------------
    if "known_spamtrap_domain" in spam_flags:
        score -= WEIGHTS["disposable_penalty"]
        status = "invalid"

    if "disposable_domain" in spam_flags:
        score -= WEIGHTS["disposable_penalty"]

    if "role_account" in spam_flags:
        score -= WEIGHTS["role_penalty"]

    if "smtp_spam_hint" in spam_flags or "smtp_spamtrap_hint" in spam_flags:
        score -= WEIGHTS["smtp_spam_penalty"]

    # ----------------------------
    # 3. Bounce Classification
    # ----------------------------
    if bounce_class == "hard":
        score += WEIGHTS["invalid_penalty"]
        status = "invalid"

    if bounce_class == "soft":
        score -= WEIGHTS["greylist_penalty"]

    if bounce_class == "accept_all":
        status = "unknown"  # risky
        score -= 5

    # ----------------------------
    # 4. Domain Reputation Score
    # ----------------------------
    domain_rep_score = domain_rep.get("score", 50)
    score += (domain_rep_score - 50) * WEIGHTS["domain_reputation_weight"]

    # ----------------------------
    # 5. MX IP Reputation
    # ----------------------------
    ip_rep = ip_info.get("score", 50)
    score += (ip_rep - 50) * WEIGHTS["ip_reputation_weight"]

    # ----------------------------
    # Safety Clamps & Finalization
    # ----------------------------
    if score < 0:
        score = 0
    if score > 100:
        score = 100

    # If invalid with low score
    if status == "invalid":
        score = max(score, 80)  # invalid should be high risk

    # Pack everything
    final = {
        "status": status,
        "risk_score": int(score),
        "details": probe
    }

    return final
