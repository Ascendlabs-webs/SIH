"""Audio preprocessing tests: mono, resample 8k->16k, normalize, chunk, mu-law."""
from __future__ import annotations

import numpy as np
import pytest

from app.audio.codecs import decode_mulaw_8k, encode_mulaw_8k
from app.audio.preprocessor import chunk_audio, preprocess_audio, resample


def test_resampling_8k_to_16k():
    sr8 = 8000
    t = np.arange(sr8 * 2) / sr8
    audio8 = np.sin(2 * np.pi * 200 * t).astype(np.float32)
    out = resample(audio8, sr8, 16000)
    assert len(out) == 16000 * 2
    t16 = np.arange(16000 * 2) / 16000
    ideal = np.sin(2 * np.pi * 200 * t16)
    corr = float(np.corrcoef(out, ideal)[0, 1])
    assert corr > 0.95


def test_preprocessing_mono_normalize():
    stereo = np.random.default_rng(0).normal(0, 0.1, size=(16000, 2)).astype(np.float32) * 5
    out = preprocess_audio(stereo, 16000)
    assert out["sample_rate"] == 16000
    assert out["audio"].ndim == 1
    assert float(np.max(np.abs(out["audio"]))) <= 0.96
    assert out["duration_sec"] == pytest.approx(1.0, abs=0.01)


def test_chunking_window():
    audio = np.zeros(16000 * 6, dtype=np.float32)
    chunks = chunk_audio(audio, 16000, 2.5)
    assert len(chunks) == 3  # 6 s -> 2 full windows + 1.0 s tail zero-padded to full
    assert all(len(c) == int(2.5 * 16000) for c in chunks)


def test_mulaw_roundtrip():
    sr = 8000
    t = np.arange(sr) / sr
    tone = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    wire = encode_mulaw_8k(tone)
    back = decode_mulaw_8k(wire)
    assert back.shape == tone.shape
    corr = float(np.corrcoef(back, tone)[0, 1])
    assert corr > 0.9
