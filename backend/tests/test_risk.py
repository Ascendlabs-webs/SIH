"""Risk engine tests: thresholds, rolling average, context, alerts."""
from __future__ import annotations

from app.risk.alerts import AlertEngine
from app.risk.context import ContextRiskEngine
from app.risk.rolling import RollingRiskEngine


def test_alert_thresholds():
    eng = RollingRiskEngine(window_size=1)
    assert eng.level_for(0.10) == "GREEN"
    assert eng.level_for(0.59) == "GREEN"
    assert eng.level_for(0.60) == "YELLOW"
    assert eng.level_for(0.75) == "YELLOW"
    assert eng.level_for(0.76) == "ORANGE"
    assert eng.level_for(0.90) == "ORANGE"
    assert eng.level_for(0.91) == "RED"


def test_rolling_average_smooths_spikes():
    eng = RollingRiskEngine(window_size=5)
    for _ in range(4):
        out = eng.update(0.1)
    assert out["alert_level"] == "GREEN"
    out = eng.update(0.99)  # single spike must not jump straight to RED
    assert out["alert_level"] in ("GREEN", "YELLOW")
    assert out["risk_score"] < 0.6


def test_rolling_converges_on_sustained_attack():
    eng = RollingRiskEngine(window_size=5)
    last = None
    for _ in range(5):
        last = eng.update(0.95)
    assert last is not None and last["alert_level"] == "RED"


def test_context_risk_bounded():
    ctx = ContextRiskEngine()
    out = ctx.score(0.5, {"caller_known": False, "pending_transaction": True, "sensitive_action": True, "call_type": "twilio"})
    assert out["final_risk"] > 0.5
    assert out["final_risk"] - 0.5 <= 0.15 + 1e-9  # bounded boost
    # context alone cannot fabricate RED from silence
    out2 = ctx.score(0.05, {"pending_transaction": True, "sensitive_action": True, "caller_known": False})
    assert out2["final_risk"] < 0.6
    # audio and context kept separate
    assert "audio_risk" in out and "context_boost" in out


def test_alert_engine_recommendations():
    eng = AlertEngine()
    assert "genuine" in eng.decide("GREEN")["recommendation"].lower()
    assert eng.decide("ORANGE", sensitive_action=True)["requires_secondary_verification"] is True
    assert eng.decide("RED")["requires_secondary_verification"] is True
    assert eng.decide("GREEN")["requires_secondary_verification"] is False
