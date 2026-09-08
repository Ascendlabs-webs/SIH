"""Contextual risk: small bounded adjustment, never overrides audio evidence."""
from __future__ import annotations


class ContextRiskEngine:
    # Bounded boosts so context can raise caution but never fabricate a RED alone.
    BOOST_PENDING_TX = 0.06
    BOOST_SENSITIVE = 0.06
    BOOST_UNKNOWN_CALLER = 0.03
    BOOST_TWILIO = 0.01
    RELIEF_KNOWN_NO_ACTION = -0.04
    MAX_TOTAL_BOOST = 0.15

    def score(self, audio_risk: float, context: dict | None) -> dict:
        ctx = context or {}
        boost = 0.0
        reasons: list[str] = []
        if ctx.get("pending_transaction"):
            boost += self.BOOST_PENDING_TX
            reasons.append("pending_transaction")
        if ctx.get("sensitive_action"):
            boost += self.BOOST_SENSITIVE
            reasons.append("sensitive_action")
        if not ctx.get("caller_known", False):
            boost += self.BOOST_UNKNOWN_CALLER
            reasons.append("unknown_caller")
        if ctx.get("call_type") == "twilio":
            boost += self.BOOST_TWILIO
            reasons.append("twilio_network")
        if ctx.get("caller_known") and not ctx.get("sensitive_action") and not ctx.get("pending_transaction"):
            boost += self.RELIEF_KNOWN_NO_ACTION
            reasons.append("known_caller_no_action")
        boost = max(-0.05, min(self.MAX_TOTAL_BOOST, boost))
        final = float(min(0.99, max(0.0, float(audio_risk) + boost)))
        return {"audio_risk": float(audio_risk), "context_boost": float(boost), "final_risk": final, "reasons": reasons}
