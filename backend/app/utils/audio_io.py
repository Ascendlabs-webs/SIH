"""Audio IO helpers: base64 decode, upload validation."""
from __future__ import annotations

import base64
import io

import numpy as np


def decode_base64_audio(payload: str, sample_rate: int, encoding: str) -> tuple[np.ndarray, int]:
    from app.audio.preprocessor import decode_input

    raw = base64.b64decode(payload, validate=False)
    return decode_input(raw, sample_rate, encoding)


def samples_to_array(samples: list[float]) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32)
    if arr.size == 0:
        raise ValueError("Empty samples array")
    return np.clip(arr, -1.0, 1.0)
