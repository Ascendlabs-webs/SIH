"""Prevention workflow tests: state machine transitions + REST endpoints."""
from __future__ import annotations

from app.services.protection import ProtectionEngine


def test_green_is_normal():
    eng = ProtectionEngine()
    snap = eng.observe("GREEN")
    assert snap["state"] == "NORMAL"


def test_yellow_warns():
    eng = ProtectionEngine()
    assert eng.observe("YELLOW")["state"] == "WARNING"


def test_orange_sensitive_requires_verification():
    eng = ProtectionEngine()
    snap = eng.observe("ORANGE", sensitive_action=True)
    assert snap["state"] == "SECONDARY_VERIFICATION_REQUIRED"
    assert "otp" in snap["required_actions"]


def test_orange_nonsensitive_is_warning():
    eng = ProtectionEngine()
    assert eng.observe("ORANGE", sensitive_action=False)["state"] == "WARNING"


def test_red_blocks():
    eng = ProtectionEngine()
    snap = eng.observe("RED", sensitive_action=True)
    assert snap["state"] == "BLOCKED"
    assert "supervisor_approval" in snap["required_actions"]


def test_challenge_then_verify():
    eng = ProtectionEngine()
    eng.observe("RED", sensitive_action=True)
    snap = eng.act("request_otp")
    assert snap["state"] == "BLOCKED"  # challenge alone does not verify
    assert len(snap["pending_challenges"]) == 1
    snap = eng.act("mark_verified")
    assert snap["state"] == "VERIFIED"


def test_escalate_and_reset():
    eng = ProtectionEngine()
    eng.observe("ORANGE", sensitive_action=True)
    assert eng.act("escalate")["state"] == "ESCALATED"
    assert eng.act("reset")["state"] == "NORMAL"


def test_bad_action_rejected():
    eng = ProtectionEngine()
    try:
        eng.act("wire_money")
    except ValueError:
        return
    raise AssertionError("unknown action must raise")


def test_protection_endpoints(client):
    r = client.get("/api/protection/state")
    assert r.status_code == 200
    assert "state" in r.json()
    r = client.post("/api/protection/action", json={"action": "request_otp"})
    assert r.status_code == 200
    assert len(r.json()["pending_challenges"]) >= 1
    r = client.post("/api/protection/action", json={"action": "nope"})
    assert r.status_code == 422
    client.post("/api/protection/action", json={"action": "reset"})


def test_demo_reset_alias(client):
    r = client.post("/api/demo/reset")
    assert r.status_code == 200
    assert r.json().get("reset") is True


def test_webrtc_config(client):
    r = client.get("/api/webrtc/config")
    assert r.status_code == 200
    assert "pcm16" in r.json()["encodings"]


def test_result_carries_protection_and_latency(client, genuine_audio):
    audio, sr = genuine_audio
    r = client.post("/api/analyze", json={"samples": [float(x) for x in audio[: sr * 3]], "sample_rate": sr})
    assert r.status_code == 200
    body = r.json()
    assert set(body["latency_breakdown"]) == {"preprocess_ms", "features_ms", "inference_ms", "risk_ms"}
    assert body["protection_state"] in (
        "NORMAL", "WARNING", "SECONDARY_VERIFICATION_REQUIRED", "VERIFIED", "ESCALATED", "BLOCKED")
