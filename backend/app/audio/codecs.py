"""Telephony codec helpers (8 kHz mu-law -> 16 kHz PCM pipeline entry point)."""
from __future__ import annotations

import io

import numpy as np

try:
    import audioop  # Python 3.10 still ships audioop
except ImportError:  # pragma: no cover
    audioop = None  # type: ignore


def decode_mulaw_8k(data: bytes) -> np.ndarray:
    """Decode 8 kHz mu-law bytes to float32 mono in [-1, 1].

    Falls back to a pure-numpy G.711 decoder when audioop is unavailable.
    """
    if audioop is not None:
        pcm = audioop.ulaw2lin(data, 2)  # 8-bit ulaw -> 16-bit linear
        # NOTE: np.frombuffer rejects non-native byte-order dtypes on numpy>=2,
        # so use native int16 (little-endian on all supported platforms here).
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        return arr
    # Pure-python G.711 mu-law decode
    out = np.empty(len(data), dtype=np.float32)
    for i, b in enumerate(data):
        b = ~b & 0xFF
        sign = -1.0 if (b & 0x80) else 1.0
        exponent = (b >> 4) & 0x07
        mantissa = b & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        out[i] = sign * (sample - 0x84) / 32768.0
    return out


def encode_mulaw_8k(samples: np.ndarray) -> bytes:
    """Encode float samples to 8 kHz mu-law bytes (used by tests/demos)."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16).tobytes()
    if audioop is not None:
        return audioop.lin2ulaw(pcm16, 2)
    # fallback: crude 8-bit quantisation (not true G.711, only for smoke tests)
    arr = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    return ((arr * 127).astype(np.int8)).tobytes()


def decode_pcm16(data: bytes) -> np.ndarray:
    if len(data) % 2 != 0:
        data = data[:-1]
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def decode_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    """Decode WAV bytes -> (mono float32, sample_rate)."""
    import soundfile as sf

    bio = io.BytesIO(data)
    audio, sr = sf.read(bio, dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1).astype(np.float32)
    return audio, int(sr)
