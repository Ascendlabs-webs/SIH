"""Shared test fixtures: deterministic synthetic signals (no audio files needed)."""
from __future__ import annotations

import numpy as np
import pytest


def make_tone(freq: float = 160.0, seconds: float = 3.0, sr: int = 16000, flat: bool = True) -> np.ndarray:
    rng = np.random.default_rng(11)
    t = np.arange(int(sr * seconds)) / sr
    if flat:
        f0 = np.full_like(t, freq)
        sig = np.sign(np.sin(2 * np.pi * freq * t)) * 0.4 + 0.2 * np.sin(2 * np.pi * freq * t)
    else:
        f0 = freq + 25 * np.sin(2 * np.pi * 1.1 * t)
        phase = 2 * np.pi * np.cumsum(f0) / sr
        sig = 0.5 * np.sin(phase) + 0.2 * np.sin(2 * phase) + rng.normal(0, 0.02, size=t.shape)
        # pauses
        sig[int(1.0 * sr):int(1.3 * sr)] *= 0.02
    sig = sig / max(1e-9, np.max(np.abs(sig))) * 0.8
    return sig.astype(np.float32)


@pytest.fixture()
def genuine_audio() -> tuple[np.ndarray, int]:
    return make_tone(flat=False), 16000


@pytest.fixture()
def synthetic_audio() -> tuple[np.ndarray, int]:
    return make_tone(flat=True), 16000


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
