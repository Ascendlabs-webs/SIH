"""Prevention workflow: backend state machine for sensitive-action protection.

States:
    NORMAL -> WARNING -> SECONDARY_VERIFICATION_REQUIRED -> VERIFIED
                                                  \\-> BLOCKED -> VERIFIED
                                                       \\-> ESCALATED

Driven by real analysis results (alert level + sensitive_action flag):
  GREEN  -> NORMAL (clears transient WARNING)
  YELLOW -> WARNING
  ORANGE (+ sensitive action) -> SECONDARY_VERIFICATION_REQUIRED
  ORANGE (no sensitive action) -> WARNING
  RED    -> BLOCKED (action blocked pending verification + escalation offered)

Simulated demo actions (no real banking/money movement):
  request_otp / request_callback -> records a pending challenge
  mark_verified                  -> VERIFIED (simulated successful challenge)
  escalate                       -> ESCALATED (supervisor review)
  reset                          -> NORMAL (clears challenges)

Each AnalysisPipeline owns one engine; the global REST/demo pipeline's engine
is exposed via /api/protection/* so the dashboard panel reflects backend state.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Literal

ProtectionStateName = Literal[
    "NORMAL", "WARNING", "SECONDARY_VERIFICATION_REQUIRED", "VERIFIED", "ESCALATED", "BLOCKED"
]

TERMINAL_HELD = ("VERIFIED", "ESCALATED")


class ProtectionEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: ProtectionStateName = "NORMAL"
        self.required_actions: list[str] = []
        self.pending_challenges: list[dict] = []
        self.last_level: str = "GREEN"
        self.updated_at: str = datetime.now(timezone.utc).isoformat()

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def observe(self, alert_level: str, sensitive_action: bool = False) -> dict:
        """Advance state from a real analysis result. Returns snapshot."""
        with self._lock:
            self.last_level = alert_level
            prev = self.state
            if alert_level == "RED":
                self.state = "BLOCKED"
                self.required_actions = ["otp", "callback", "supervisor_approval"]
            elif alert_level == "ORANGE" and sensitive_action:
                if self.state not in ("BLOCKED", "ESCALATED"):
                    self.state = "SECONDARY_VERIFICATION_REQUIRED"
                self.required_actions = ["otp", "callback", "additional_identity_verification"]
            elif alert_level in ("ORANGE", "YELLOW"):
                if self.state not in ("BLOCKED", "ESCALATED", "SECONDARY_VERIFICATION_REQUIRED", "VERIFIED"):
                    self.state = "WARNING"
                if not self.required_actions:
                    self.required_actions = ["monitor"]
            else:  # GREEN
                if self.state not in TERMINAL_HELD and self.state != "SECONDARY_VERIFICATION_REQUIRED" and self.state != "BLOCKED":
                    self.state = "NORMAL"
                    self.required_actions = []
            self._touch()
            return self._snapshot_locked(prev_transition=(prev != self.state))

    def act(self, action: str) -> dict:
        """Apply a simulated protection action. Returns snapshot."""
        with self._lock:
            prev = self.state
            action = action.strip().lower()
            if action in ("request_otp", "request_callback"):
                channel = "otp" if action == "request_otp" else "callback"
                self.pending_challenges.append(
                    {"channel": channel, "status": "sent",
                     "at": datetime.now(timezone.utc).isoformat(), "demo": True}
                )
                # issuing a challenge does not itself verify
            elif action == "mark_verified":
                if self.state in ("SECONDARY_VERIFICATION_REQUIRED", "BLOCKED", "WARNING", "NORMAL"):
                    self.state = "VERIFIED"
                    self.required_actions = []
            elif action == "escalate":
                self.state = "ESCALATED"
                self.required_actions = ["supervisor_approval"]
            elif action == "reset":
                self.state = "NORMAL"
                self.required_actions = []
                self.pending_challenges = []
            else:
                raise ValueError(f"Unknown protection action: {action}")
            self._touch()
            return self._snapshot_locked(prev_transition=(prev != self.state))

    def reset(self) -> dict:
        return self.act("reset")

    def _snapshot_locked(self, prev_transition: bool = False) -> dict:
        return {
            "state": self.state,
            "required_actions": list(self.required_actions),
            "pending_challenges": [dict(c) for c in self.pending_challenges],
            "last_alert_level": self.last_level,
            "transitioned": prev_transition,
            "updated_at": self.updated_at,
        }

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_locked()
