"""Banking policy: maps a VAuth security decision + transaction to an outcome.

The PROTECTED ACTION matters — RED alone does not block everything:

  GREEN (+ anything)                    -> PENDING (approvable)
  YELLOW                                -> PENDING + caution flag (approvable)
  ORANGE/RED + NON-sensitive, small     -> PENDING + warning (alert, no hold)
  ORANGE/RED + SENSITIVE (flag or >= threshold) -> PENDING_VERIFICATION (hold)
  requires_secondary_verification + SENSITIVE   -> PENDING_VERIFICATION (hold)

Only the policy layer decides; VAuth only supplies the security decision.
"""
from __future__ import annotations

SENSITIVE_AMOUNT_THRESHOLD = 100_000.0
HOLD_LEVELS = ("ORANGE", "RED")


def decide(alert_level: str, requires_secondary_verification: bool,
           protection_state: str, amount: float,
           sensitive_action: bool) -> dict:
    level = (alert_level or "GREEN").upper()
    sensitive = bool(sensitive_action) or float(amount) >= SENSITIVE_AMOUNT_THRESHOLD
    required: list[str] = []
    if sensitive and (level in HOLD_LEVELS or requires_secondary_verification):
        if level == "RED":
            required = ["otp", "callback", "supervisor_approval"]
            reason = (f"VAuth {level} on a sensitive Rs.{amount:,.0f} action: "
                      "transaction held pending verification + escalation available.")
        else:
            required = ["otp", "callback", "additional_identity_verification"]
            reason = (f"VAuth {level} on a sensitive Rs.{amount:,.0f} action: "
                      "transaction held pending secondary verification.")
        return {"status": "PENDING_VERIFICATION", "reason": reason,
                "required_actions": required, "sensitive": sensitive}
    if level in HOLD_LEVELS:
        reason = (f"VAuth {level} noted, but the action is not sensitive: "
                  "transaction may proceed with a recorded warning.")
        return {"status": "PENDING", "reason": reason,
                "required_actions": ["monitor"], "sensitive": sensitive}
    if level == "YELLOW":
        return {"status": "PENDING",
                "reason": "VAuth YELLOW: proceed with caution; step-up available.",
                "required_actions": ["monitor"], "sensitive": sensitive}
    return {"status": "PENDING", "reason": "VAuth GREEN: normal flow.",
            "required_actions": [], "sensitive": sensitive}
