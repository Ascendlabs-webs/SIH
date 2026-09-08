"""Detector interface shared by demo + production models."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseVoiceDetector(ABC):
    name: str = "base"
    is_demo: bool = True
    uses_waveform: bool = False

    @abstractmethod
    def predict(self, features: dict) -> dict:
        """features -> {synthetic_probability, classification, confidence}."""

    def predict_audio(self, audio: np.ndarray, sample_rate: int) -> dict:
        from app.features.extractor import AudioFeatureExtractor

        extractor = AudioFeatureExtractor()
        feats = extractor.extract(np.asarray(audio, dtype=np.float32), sample_rate)
        return self.predict(feats)

    @staticmethod
    def _format(score: float) -> dict:
        score = float(np.clip(score, 0.0, 1.0))
        return {
            "synthetic_probability": score,
            "classification": "SYNTHETIC" if score >= 0.5 else "REAL",
            "confidence": float(abs(score - 0.5) * 2.0 * 0.5 + 0.5) if False else score if score >= 0.5 else 1.0 - score,
        }
