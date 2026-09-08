"""Energy-based voice activity detection (no mandatory native deps)."""
from __future__ import annotations

import numpy as np


def frame_energy_vad(
    audio: np.ndarray,
    sample_rate: int = 16000,
    frame_ms: float = 20.0,
    threshold_ratio: float = 0.08,
) -> dict:
    """Return per-frame VAD flags + summary stats.

    Simple, dependency-free: frames whose RMS exceeds
    max(rms_median * 2.0, global_rms * threshold_ratio, 1e-4) are active.
    """
    if audio.size == 0:
        return {"flags": [], "active_ratio": 0.0, "active": False, "silence_ratio": 1.0}
    frame_len = max(1, int(sample_rate * frame_ms / 1000.0))
    n_frames = max(1, int(np.ceil(len(audio) / frame_len)))
    padded = np.pad(audio, (0, n_frames * frame_len - len(audio)))
    frames = padded.reshape(n_frames, frame_len)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    global_rms = float(np.sqrt(np.mean(audio ** 2) + 1e-12))
    median_rms = float(np.median(rms)) if len(rms) else 0.0
    threshold = max(median_rms * 2.0, global_rms * threshold_ratio, 1e-4)
    flags = rms > threshold
    active_ratio = float(flags.mean()) if len(flags) else 0.0
    return {
        "flags": [bool(f) for f in flags],
        "active_ratio": active_ratio,
        "active": bool(active_ratio > 0.05),
        "silence_ratio": float(1.0 - active_ratio),
        "threshold": float(threshold),
        "global_rms": global_rms,
    }


def pause_statistics(vad_flags: list[bool], frame_ms: float = 20.0) -> dict:
    """Count pauses (consecutive inactive frames) and summarise durations."""
    pauses: list[float] = []
    cur = 0
    for f in vad_flags:
        if not f:
            cur += 1
        else:
            if cur > 0:
                pauses.append(cur * frame_ms / 1000.0)
                cur = 0
    if cur > 0:
        pauses.append(cur * frame_ms / 1000.0)
    if not pauses:
        return {"num_pauses": 0, "mean_pause_sec": 0.0, "max_pause_sec": 0.0, "silence_ratio": 0.0 if vad_flags else 1.0}
    import statistics

    silence_ratio = sum(pauses) / max(1e-6, (len(vad_flags) * frame_ms / 1000.0))
    return {
        "num_pauses": len(pauses),
        "mean_pause_sec": float(statistics.mean(pauses)),
        "max_pause_sec": float(max(pauses)),
        "silence_ratio": float(min(1.0, silence_ratio)),
    }
