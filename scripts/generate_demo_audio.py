"""Generate deterministic demo audio (no network, no secrets).

demo_real.wav:      natural-sounding speech-like signal — vibrato pitch glide,
                    syllable-rate amplitude modulation, pauses, breath noise.
                    -> DemoVoiceDetector should score LOW.
demo_synthetic.wav: flat robotic buzz — fixed F0, fixed amplitude, no pauses,
                    no noise, hard-clipped harmonics.
                    -> DemoVoiceDetector should score HIGH.

Both are 16 kHz mono WAV, ~10 s (4 x 2.5 s windows).
These are PLACEHOLDER test signals, not real speech. The demo heuristic is NOT
a validated anti-spoof model.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 16000
DUR = 10.0

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo"


def _write(name: str, audio: np.ndarray) -> Path:
    import soundfile as sf

    OUT.mkdir(parents=True, exist_ok=True)
    audio = np.clip(audio, -0.95, 0.95).astype(np.float32)
    path = OUT / name
    sf.write(str(path), audio, SR)
    print(f"wrote {path} ({len(audio)/SR:.1f}s @ {SR}Hz)")
    return path


def genuine(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(int(SR * DUR)) / SR
    # Syllable-rate amplitude envelope (3-5 Hz) + pauses every ~2 s
    f0 = 118 + 28 * np.sin(2 * np.pi * 0.9 * t) + 8 * np.sin(2 * np.pi * 2.7 * t + 1.0)
    vibrato = 1.0 + 0.02 * np.sin(2 * np.pi * 5.5 * t)
    phase = 2 * np.pi * np.cumsum(f0 * vibrato) / SR
    # Glottal-ish harmonic stack with breath noise
    sig = (
        0.55 * np.sin(phase)
        + 0.22 * np.sin(2 * phase)
        + 0.12 * np.sin(3 * phase + 0.7)
        + 0.05 * np.sin(4 * phase + 1.9)
    )
    syll = 0.55 + 0.45 * np.sin(2 * np.pi * 3.4 * t + 0.5)
    syll = np.clip(syll, 0.05, 1.0)
    sig = sig * syll
    # Pauses: 0.35 s silence every ~2 s
    for start in (1.6, 3.9, 6.2, 8.4):
        i0, i1 = int(start * SR), int((start + 0.35) * SR)
        sig[i0:i1] *= np.linspace(1, 0, i1 - i0) ** 2 if False else 0.02
    noise = rng.normal(0, 0.018, size=sig.shape)
    sig = sig * 0.6 + noise
    return (sig / max(1e-9, np.max(np.abs(sig))) * 0.85).astype(np.float32)


def synthetic() -> np.ndarray:
    t = np.arange(int(SR * DUR)) / SR
    f0 = np.full_like(t, 165.0)  # dead-flat pitch
    phase = 2 * np.pi * np.cumsum(f0) / SR
    # Perfectly periodic square-ish buzz, fixed amplitude, zero pauses/noise
    sig = np.sign(np.sin(phase)) * 0.45 + 0.25 * np.sin(phase) + 0.12 * np.sin(2 * phase)
    sig = np.tanh(sig * 1.6) * 0.7  # hard, uniform saturation
    return (sig / max(1e-9, np.max(np.abs(sig))) * 0.85).astype(np.float32)


def main() -> None:
    rng = np.random.default_rng(7)
    _write("demo_real.wav", genuine(rng))
    _write("demo_synthetic.wav", synthetic())


if __name__ == "__main__":
    main()
