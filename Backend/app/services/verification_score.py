from typing import Dict, Any
from enum import StrEnum

class EmailStatus(StrEnum):
    VALID = "valid"
    RISKY = "risky"      # accept-all, greylisted, low rep
    INVALID = "invalid"
    UNKNOWN = "unknown"

# Risk Score: 0 = pristine, 100 = definitely bad
# This is the industry standard (Neverbounce, ZeroBounce, etc.)
WEIGHTS = {
    "valid_bonus": -40,           # Strongly reduces risk
    "hard_bounce_penalty": +90,
    "soft_bounce_penalty": +20,
    "spamtrap_penalty": +100,
    "disposable_penalty": +70,
    "role_account_penalty": +25,
    "greylist_penalty": +15,
    "accept_all_penalty": +30,
    "smtp_spam_hint_penalty": +40,
    "domain_rep_weight": 0.6,
    "ip_rep_weight": 0.4,
}

def score_verification(probe: Dict[str, Any]) -> Dict[str, Any]:
    """
    Production-grade email risk scoring engine (2025 edition)
    
    Risk Score: 0–100 where:
        0–20   → Very clean
        20–50  → Safe / low risk
        50–75  → Risky (monitor)
        75–90  → High risk
        90–100 → Toxic (block)
    """
    risk_score = 50  # Neutral start
    status = EmailStatus.UNKNOWN

    # Extract data
    rcpt_code = probe.get("rcpt_code")
    spam_flags = probe.get("spam_flags", [])
    bounce_class = probe.get("bounce_class")
    domain_rep = probe.get("domain_reputation") or {}
    ip_info = probe.get("ip_info") or {}

    domain_score = float(domain_rep.get("score", 50))  # 0–100, higher = better
    ip_score = float(ip_info.get("score", 50))

    # ------------------------------------------------------------------
    # 1. SMTP Response Code (RCPT TO)
    # ------------------------------------------------------------------
    try:
        rc = int(rcpt_code) if rcpt_code else None
    except (ValueError, TypeError):
        rc = None

    if rc is not None:
        if 200 <= rc < 300:
            risk_score += WEIGHTS["valid_bonus"]        # e.g. -40 → drops to ~10
            status = EmailStatus.VALID
        elif rc == 450 or rc == 451:  # Greylisting
            risk_score += WEIGHTS["greylist_penalty"]
            status = EmailStatus.RISKY
        elif 500 <= rc < 600:
            risk_score += WEIGHTS["hard_bounce_penalty"]  # +90 → ~100
            status = EmailStatus.INVALID

    # ------------------------------------------------------------------
    # 2. Critical Red Flags (override everything)
    # ------------------------------------------------------------------
    if "known_spamtrap_domain" in spam_flags or "spamtrap" in spam_flags:
        risk_score = 100
        status = EmailStatus.INVALID
        final = {"status": status, "risk_score": 100, "details": probe, "reason": "spamtrap"}
        return {**final, "risk_level": "toxic"}

    if "disposable_domain" in spam_flags:
        risk_score = max(risk_score, 85)
        risk_score += WEIGHTS["disposable_penalty"]
        status = EmailStatus.INVALID

    if "role_account" in spam_flags:
        risk_score += WEIGHTS["role_account_penalty"]

    if any(f in spam_flags for f in ["smtp_spam_hint", "smtp_spamtrap_hint", "honeypot"]):
        risk_score += WEIGHTS["smtp_spam_hint_penalty"]

    # ------------------------------------------------------------------
    # 3. Bounce Classification
    # ------------------------------------------------------------------
    if bounce_class == "hard":
        risk_score = max(risk_score, 90)
        risk_score += WEIGHTS["hard_bounce_penalty"]
        status = EmailStatus.INVALID
    elif bounce_class == "soft":
        risk_score += WEIGHTS["soft_bounce_penalty"]
        status = EmailStatus.RISKY
    elif bounce_class == "accept_all":
        risk_score += WEIGHTS["accept_all_penalty"]
        status = EmailStatus.RISKY

    # ------------------------------------------------------------------
    # 4. Reputation Adjustments (scaled contribution)
    # ------------------------------------------------------------------
    # Convert reputation scores: higher rep_score → lower risk
    domain_risk_contribution = (50 - domain_score) * WEIGHTS["domain_rep_weight"]
    ip_risk_contribution = (50 - ip_score) * WEIGHTS["ip_rep_weight"]

    risk_score += domain_risk_contribution + ip_risk_contribution

    # ------------------------------------------------------------------
    # 5. Final Clamp & Status Resolution
    # ------------------------------------------------------------------
    risk_score = max(0, min(100, risk_score))

    # Final status overrides
    if risk_score >= 90:
        status = EmailStatus.INVALID
    elif risk_score >= 70:
        status = EmailStatus.RISKY
    elif risk_score <= 25:
        status = EmailStatus.VALID

    # Risk level for frontend
    if risk_score <= 20:
        risk_level = "excellent"
    elif risk_score <= 50:
        risk_level = "good"
    elif risk_score <= 75:
        risk_level = "warning"
    elif risk_score <= 90:
        risk_level = "dangerous"
    else:
        risk_level = "toxic"

    return {
        "status": status.value,
        "risk_score": int(round(risk_score)),
        "risk_level": risk_level,
        "details": probe,
        "scoring_breakdown": {  # Optional: for debugging
            "base": 50,
            "smtp_adjustment": risk_score - 50 - domain_risk_contribution - ip_risk_contribution,
            "domain_rep_contribution": round(domain_risk_contribution, 1),
            "ip_rep_contribution": round(ip_risk_contribution, 1),
        }
    }
