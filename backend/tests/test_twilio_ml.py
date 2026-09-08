"""Twilio adapter tests: TwiML webhook, config, and Media Streams WS path.

Exercises the full Twilio code path: 8 kHz mu-law frames -> decode ->
16 kHz pipeline -> analysis_result, using the SAME AnalysisPipeline as demos.
(No credentials needed; no live Twilio call is made.)
"""
from __future__ import annotations

import base64

import numpy as np
import pytest

requires_model = pytest.mark.requires_model


def test_twilio_voice_returns_twiml(client):
    r = client.post("/api/twilio/voice")
    assert r.status_code == 200
    assert "text/xml" in r.headers.get("content-type", "")
    assert "<Stream" in r.text
    assert "/ws/twilio" in r.text


def test_twilio_config_no_credentials_needed(client):
    r = client.get("/api/twilio/config")
    assert r.status_code == 200
    body = r.json()
    assert "stream_url" in body
    assert isinstance(body["configured"], bool)


def test_twilio_ws_mulaw_to_result(client):
    from app.audio.codecs import encode_mulaw_8k

    sr = 8000
    t = np.arange(sr * 3) / sr
    tone = (0.4 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    wire = encode_mulaw_8k(tone)
    # Twilio sends ~20 ms frames (160 bytes @ 8 kHz mu-law)
    frames = [wire[i:i + 160] for i in range(0, len(wire), 160)]

    with client.websocket_connect("/ws/twilio") as ws:
        ws.send_json({"event": "connected", "protocol": "Call", "version": "1.0"})
        first = ws.receive_json()
        assert first["type"] == "ready"
        got = None
        for fr in frames:
            ws.send_json({
                "event": "media",
                "media": {"payload": base64.b64encode(fr).decode()},
            })
            # drain any results without blocking forever: TestClient has no
            # timeout recv, so only read after enough audio was sent
        # 3 s @ 8 kHz -> ~1 full 2.5 s window at 16 kHz -> exactly one result
        got = ws.receive_json()
        assert got["type"] == "analysis_result", got
        assert 0.0 <= got["risk_score"] <= 1.0
        assert got["window_duration"] > 2.0
        ws.send_json({"event": "stop"})


@requires_model
def test_ml_mode_loads_real_detector():
    """With the real checkpoint present, ml mode loads AASIST (no fallback)."""
    from pathlib import Path

    import app.models.factory as factory
    from app.models.ml_detector import MLVoiceDetector

    if not Path("models/AASIST.pth").is_file():
        pytest.skip("AASIST checkpoint unavailable; run scripts/download_aasist.py")
    det = factory.get_detector("ml")
    assert isinstance(det, MLVoiceDetector)
    assert det.is_demo is False
    assert getattr(det, "_fallback_warning", None) is None


def test_ml_detector_missing_checkpoint_falls_back(monkeypatch):
    """Documented fallback: ml + missing checkpoint -> DemoVoiceDetector with
    an explicit visible warning. Asserts the fallback, never silent REAL ML."""
    import app.models.factory as factory
    from app.models.demo_detector import DemoVoiceDetector
    from app.models.ml_detector import MLVoiceDetector, ModelNotAvailableError

    # Construction with a bogus path refuses loudly...
    monkeypatch.setenv("VAUTH_MODEL_PATH", "models/does-not-exist.pt")
    try:
        MLVoiceDetector()
    except ModelNotAvailableError:
        pass
    else:
        raise AssertionError("MLVoiceDetector must refuse to run without a checkpoint")
    # ...and the factory falls back to DEMO only with an explicit warning.
    det2 = factory.get_detector("ml")
    assert isinstance(det2, DemoVoiceDetector)
    assert det2.is_demo is True
    warning = getattr(det2, "_fallback_warning", None)
    assert warning, "fallback must carry a visible warning"
    assert "DEMO" in warning
