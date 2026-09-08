"""DemoVoiceDetector: deterministic heuristic for pipeline demonstration ONLY.

NOT scientifically validated. Labels: DEMO MODE in UI/API.
Designed so demo_real.wav (natural vibrato + pauses + noise) scores LOW
and demo_synthetic.wav (flat robotic tone, no pauses) scores HIGH.

Signals used (all from real feature extraction):
  - pitch flatness   exp(-f0_std / 20)
  - energy flatness  exp(-rms_std * 18)
  - flux flatness    exp(-flux_std * scale)
  - silence absence  1 - min(silence_ratio * 3, 1)
Weighted sum -> 0..1. Deterministic, no randomness.
"""
from __future__ import annotations

import math

import numpy as np

from app.models.base import BaseVoiceDetector


class DemoVoiceDetector(BaseVoiceDetector):
    name = "demo"
    model_name = "DemoVoiceDetector"
    is_demo = True
    uses_waveform = False
    label = "DEMO MODEL — Replace with trained anti-spoof model for production evaluation"

    def predict(self, features: dict) -> dict:
        f0_std = float(features.get("f0_std", 0.0) or 0.0)
        rms_std = float((features.get("rms") or {}).get("std", 0.0) or 0.0)
        flux_std = float((features.get("spectral_flux") or {}).get("std", 0.0) or 0.0)
        silence_ratio = float(features.get("silence_ratio", 0.0) or 0.0)
        voiced_ratio = float(features.get("voiced_ratio", 0.0) or 0.0)
        zcr_std = float((features.get("zcr") or {}).get("std", 0.0) or 0.0)
        f0_mean = float(features.get("f0_mean", 0.0) or 0.0)

        pitch_flat = math.exp(-f0_std / 22.0)
        energy_flat = math.exp(-rms_std * 16.0)
        # flux std typical range ~0.5-8; scale so natural speech (~2-5) -> low flatness
        flux_flat = math.exp(-flux_std / 1.6)
        silence_low = 1.0 - min(silence_ratio * 3.0, 1.0)
        zcr_flat = math.exp(-zcr_std * 22.0)

        score = (
            0.38 * pitch_flat
            + 0.20 * energy_flat
            + 0.17 * flux_flat
            + 0.15 * silence_low
            + 0.10 * zcr_flat
        )

        # Unvoiced / silent windows carry no spoof evidence -> pull toward low risk
        if voiced_ratio < 0.08 or f0_mean <= 0:
            score = score * 0.45

        # Gentle contrast stretch so demos separate clearly but stay in [0,1]
        score = float(np.clip((score - 0.30) / 0.55, 0.02, 0.97))
        return self._format(score)
