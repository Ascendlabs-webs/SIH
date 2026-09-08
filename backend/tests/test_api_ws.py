"""REST + WebSocket integration tests (file upload, JSON analyze, streaming)."""
from __future__ import annotations

import base64
import io
import struct

import numpy as np


def _wav_bytes(audio: np.ndarray, sr: int = 16000) -> bytes:
    import soundfile as sf

    bio = io.BytesIO()
    sf.write(bio, audio.astype(np.float32), sr, format="WAV")
    return bio.getvalue()


def _pcm16_b64(audio: np.ndarray) -> str:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    return base64.b64encode(pcm).decode()


def test_analyze_endpoint_json(client, genuine_audio):
    audio, sr = genuine_audio
    payload = {"samples": [float(x) for x in audio[: sr * 3]], "sample_rate": sr, "context": {"call_type": "demo"}}
    r = client.post("/api/analyze", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("risk_score", "alert_level", "classification", "confidence", "recommendation", "timestamp", "window_duration"):
        assert key in body, key
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["latency_ms"] >= 0


def test_analyze_file_endpoint(client, genuine_audio):
    audio, sr = genuine_audio
    data = _wav_bytes(audio, sr)
    r = client.post("/api/analyze-file", files={"file": ("t.wav", data, "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json()["window_duration"] > 1.0


def test_reject_malformed_audio(client):
    r = client.post("/api/analyze", json={"samples": [], "sample_rate": 16000})
    assert r.status_code in (400, 422)


def test_history_records_results(client, genuine_audio):
    audio, sr = genuine_audio
    client.post("/api/demo/stop")
    client.post("/api/analyze", json={"samples": [float(x) for x in audio[: sr * 3]], "sample_rate": sr})
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_websocket_binary_frames_mic_path(client):
    """Browser-mic path: raw int16 binary frames -> buffered 2.5 s windows -> results."""
    import numpy as np

    from tests.conftest import make_tone

    audio = make_tone(flat=False, seconds=5.0)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    half = len(pcm) // 2
    with client.websocket_connect("/ws/audio") as ws:
        ws.send_json({"type": "config", "sample_rate": 16000, "encoding": "pcm16"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(pcm[:half])
        ws.send_bytes(pcm[half:])
        got = ws.receive_json()
        assert got["type"] == "analysis_result", got
        assert got["window_duration"] > 2.0


def test_websocket_streams_windows(client):
    from tests.conftest import make_tone

    audio = make_tone(flat=False, seconds=5.0)
    b64 = _pcm16_b64(audio)
    with client.websocket_connect("/ws/audio") as ws:
        ws.send_json({"type": "config", "sample_rate": 16000, "encoding": "pcm16"})
        first = ws.receive_json()
        assert first["type"] == "ready"
        # 5 s audio -> two 2.5 s windows -> expect at least one result
        ws.send_json({"type": "audio", "audio_base64": b64, "sample_rate": 16000, "encoding": "pcm16"})
        got = ws.receive_json()
        assert got["type"] == "analysis_result", got
        assert 0.0 <= got["risk_score"] <= 1.0
        assert got["alert_level"] in ("GREEN", "YELLOW", "ORANGE", "RED")
        assert "latency_breakdown" in got
        assert got["protection_state"] in (
            "NORMAL", "WARNING", "SECONDARY_VERIFICATION_REQUIRED", "VERIFIED", "ESCALATED", "BLOCKED",
        )
