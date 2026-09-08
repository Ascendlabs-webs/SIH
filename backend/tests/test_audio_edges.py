"""Audio edge cases: silence, short clips, invalid encodings, oversized input."""
from __future__ import annotations

import base64
import io

import numpy as np
import pytest

from app.audio.preprocessor import chunk_audio, decode_input, preprocess_audio
from app.audio.webrtc import float32_bytes_to_mono, int16_bytes_to_mono
from app.features.extractor import AudioFeatureExtractor
from app.models.demo_detector import DemoVoiceDetector


def test_silence_processes_without_crash():
    silent = np.zeros(16000 * 3, dtype=np.float32)
    pre = preprocess_audio(silent, 16000)
    assert pre["vad"]["active"] is False
    feats = AudioFeatureExtractor().extract(pre["audio"], 16000)
    out = DemoVoiceDetector().predict(feats)
    assert 0.0 <= out["synthetic_probability"] <= 1.0
    # silence carries no spoof evidence -> must stay low risk
    assert out["synthetic_probability"] < 0.5


def test_short_audio_single_padded_window():
    short = np.random.default_rng(3).normal(0, 0.1, size=16000).astype(np.float32)
    chunks = chunk_audio(short, 16000, 2.5)
    assert len(chunks) == 1
    assert len(chunks[0]) == int(2.5 * 16000)


def test_invalid_encoding_rejected():
    with pytest.raises(ValueError):
        decode_input(b"not audio at all" * 100, 16000, "flac")
    with pytest.raises(ValueError):
        float32_bytes_to_mono(b"\x00\x01\x02", 16000)  # not multiple of 4
    with pytest.raises(ValueError):
        int16_bytes_to_mono(b"", 16000)


def test_webrtc_converters_roundtrip():
    rng = np.random.default_rng(5)
    pcm = (rng.normal(0, 0.2, size=8000).astype(np.float32))
    vlan = float32_bytes_to_mono(pcm.tobytes(), 16000)
    assert vlan.shape == pcm.shape
    pcm16 = (np.clip(pcm, -1, 1) * 32767).astype(np.int16).tobytes()
    back = int16_bytes_to_mono(pcm16, 8000)  # 8 kHz in -> resampled to 16 kHz
    assert len(back) == 16000


def test_oversized_upload_rejected(client):
    big = b"\x00\x01" * (11 * 1024 * 1024)  # 22 MB > 10 MB cap
    r = client.post("/api/analyze-file", files={"file": ("big.wav", big, "audio/wav")})
    assert r.status_code == 413


def test_empty_upload_rejected(client):
    r = client.post("/api/analyze-file", files={"file": ("empty.wav", b"", "audio/wav")})
    assert r.status_code == 400


def test_mulaw_end_to_end(client):
    from app.audio.codecs import encode_mulaw_8k

    sr = 8000
    t = np.arange(sr * 3) / sr
    tone = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    wire = encode_mulaw_8k(tone)
    payload = {"audio_base64": base64.b64encode(wire).decode(), "sample_rate": 8000, "encoding": "mulaw8k"}
    r = client.post("/api/analyze", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["window_duration"] > 2.0


def test_ws_rejects_bad_messages(client):
    with client.websocket_connect("/ws/audio") as ws:
        ws.send_json({"type": "config", "sample_rate": 16000, "encoding": "pcm16"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_text("this is not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "frobnicate"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "config", "sample_rate": 16000, "encoding": "mp3"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "audio", "sample_rate": 16000, "encoding": "pcm16"})
        assert ws.receive_json()["type"] == "error"  # missing audio_base64
