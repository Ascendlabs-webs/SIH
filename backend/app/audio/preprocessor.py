"""Audio preprocessing: decode -> mono -> resample(16k) -> normalize -> noise gate."""
from __future__ import annotations

import numpy as np

from app.audio.codecs import decode_mulaw_8k, decode_pcm16, decode_wav_bytes
from app.audio.vad import frame_energy_vad


TARGET_SR = 16000


def to_mono(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1).astype(np.float32)
    return audio


def resample(audio: np.ndarray, orig_sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    """Resample to target rate. Handles 8 kHz telephony -> 16 kHz explicitly."""
    audio = np.asarray(audio, dtype=np.float32)
    if orig_sr == target_sr or len(audio) == 0:
        return audio
    try:
        import librosa

        return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr).astype(np.float32)
    except Exception:
        pass
    # Fallback: scipy polyphase / linear interpolation
    try:
        from scipy import signal

        from math import gcd

        g = gcd(int(orig_sr), int(target_sr))
        up, down = int(target_sr // g), int(orig_sr // g)
        # guard against absurd ratios
        if up * down < 5000:
            return signal.resample_poly(audio, up, down).astype(np.float32)
    except Exception:
        pass
    # Last-resort linear interpolation
    duration = len(audio) / float(orig_sr)
    new_len = max(1, int(duration * target_sr))
    old_idx = np.linspace(0, 1, len(audio))
    new_idx = np.linspace(0, 1, new_len)
    return np.interp(new_idx, old_idx, audio).astype(np.float32)


def normalize(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio
    audio = audio - float(np.mean(audio))  # DC removal
    m = float(np.max(np.abs(audio)))
    if m < 1e-8:
        return audio
    if m > peak:
        audio = audio * (peak / m)
    return audio.astype(np.float32)


def noise_gate(audio: np.ndarray, threshold: float = 0.015, fade_ms: float = 5.0, sample_rate: int = TARGET_SR) -> np.ndarray:
    """Zero out sub-threshold samples with a short smoothing window."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio
    mask = np.abs(audio) >= threshold
    # smooth mask to avoid clicks
    win = max(1, int(sample_rate * fade_ms / 1000.0))
    if win > 1:
        kernel = np.ones(win, dtype=np.float32) / win
        smooth = np.convolve(mask.astype(np.float32), kernel, mode="same")
        mask = smooth > 0.3
    return (audio * mask.astype(np.float32)).astype(np.float32)


def preprocess_audio(audio: np.ndarray, sample_rate: int, target_sr: int = TARGET_SR) -> dict:
    """Full preprocessing chain. Returns processed audio + diagnostics."""
    audio = to_mono(np.asarray(audio, dtype=np.float32))
    resampled = resample(audio, int(sample_rate), target_sr)
    normalized = normalize(resampled)
    gated = noise_gate(normalized, sample_rate=target_sr)
    vad = frame_energy_vad(gated, sample_rate=target_sr)
    return {
        "audio": gated,
        "sample_rate": target_sr,
        "original_sample_rate": int(sample_rate),
        "num_samples": int(len(gated)),
        "duration_sec": float(len(gated) / target_sr) if len(gated) else 0.0,
        "vad": vad,
    }


def decode_input(data: bytes, sample_rate: int = 16000, encoding: str = "wav") -> tuple[np.ndarray, int]:
    """Decode raw request bytes according to declared encoding."""
    enc = encoding.lower()
    if enc == "wav":
        return decode_wav_bytes(data)
    if enc == "pcm16":
        return decode_pcm16(data), int(sample_rate)
    if enc == "mulaw8k":
        return decode_mulaw_8k(data), 8000
    raise ValueError(f"Unsupported encoding: {encoding}")


def telephony_degrade(audio: np.ndarray, target_sr: int = TARGET_SR) -> np.ndarray:
    """16 kHz -> 8 kHz -> mu-law -> decode -> 16 kHz telephony robustness path."""
    from app.audio.codecs import decode_mulaw_8k, encode_mulaw_8k

    audio = np.asarray(audio, dtype=np.float32)
    down = resample(audio, target_sr, 8000)
    wire = encode_mulaw_8k(down)
    back8 = decode_mulaw_8k(wire)
    return resample(back8, 8000, target_sr).astype(np.float32)


def chunk_audio(audio: np.ndarray, sample_rate: int, window_seconds: float = 2.5) -> list[np.ndarray]:
    """Split mono audio into non-overlapping windows of window_seconds.

    Drops a trailing fragment shorter than min(1.0s, window) to avoid
    degenerate inference windows. Returns list of float32 arrays.
    """
    audio = np.asarray(audio, dtype=np.float32)
    win = max(1, int(window_seconds * sample_rate))
    min_keep = max(1, int(min(1.0, window_seconds / 2.0) * sample_rate))
    chunks: list[np.ndarray] = []
    for start in range(0, len(audio), win):
        seg = audio[start : start + win]
        if len(seg) < min_keep and chunks:
            break  # drop tiny tail
        if len(seg) < win:
            # zero-pad short final window so the model always sees a full window
            seg = np.pad(seg, (0, win - len(seg)))
        chunks.append(seg.astype(np.float32))
    return chunks
