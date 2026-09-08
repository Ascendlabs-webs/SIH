"""Alert engine: level -> human + machine-readable recommendation."""
from __future__ import annotations


RECOMMENDATIONS = {
    "GREEN": "Likely genuine — proceed normally.",
    "YELLOW": "Proceed carefully — monitor for further signs.",
    "ORANGE": "Perform secondary verification before approving sensitive action.",
    "RED": "Escalate/block sensitive action — verify via OTP, callback, or supervisor approval.",
}

ACTIONS = {
    "GREEN": [],
    "YELLOW": ["monitor"],
    "ORANGE": ["otp", "callback", "additional_identity_verification"],
    "RED": ["otp", "callback", "supervisor_approval", "additional_identity_verification"],
}


class AlertEngine:
    def decide(self, alert_level: str, sensitive_action: bool = False) -> dict:
        level = alert_level if alert_level in RECOMMENDATIONS else "GREEN"
        requires = bool(level == "RED" or (level == "ORANGE" and sensitive_action))
        # RED always requires verification even without a flagged sensitive action.
        if level == "RED":
            requires = True
        return {
            "alert_level": level,
            "recommendation": RECOMMENDATIONS[level],
            "requires_secondary_verification": requires,
            "suggested_actions": list(ACTIONS[level]),
        }

    @staticmethod
    def classification_for(risk: float, threshold: float = 0.6) -> str:
        return "SYNTHETIC" if risk >= threshold else "REAL"
