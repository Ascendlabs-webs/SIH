"""Speaker verification architecture (dev embedding; ECAPA-ready interface)."""
from __future__ import annotations

import hashlib

import numpy as np


class SpeakerVerifier:
    """Interface-compatible verifier.

    Dev implementation: L2-normalised mean-MFCC pseudo-embedding.
    Production: replace _embed() with an ECAPA-TDNN embedding (e.g.
    SpeechBrain ECAPA) without changing enroll()/verify()/similarity().
    """

    def __init__(self):
        self._voices: dict[str, np.ndarray] = {}

    def _embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        from app.features.extractor import AudioFeatureExtractor

        feats = AudioFeatureExtractor().extract(np.asarray(audio, dtype=np.float32), sample_rate)
        vec = AudioFeatureExtractor().to_vector(feats).astype(np.float64)
        n = float(np.linalg.norm(vec))
        if n < 1e-9:
            # deterministic fallback so enrol/verify never crash on silence
            h = hashlib.sha256(np.asarray(audio).tobytes()).digest()
            vec = np.frombuffer(h, dtype=np.uint8).astype(np.float64)[: len(vec)]
            n = float(np.linalg.norm(vec)) or 1.0
        return (vec / n).astype(np.float32)

    def enroll(self, speaker_id: str, audio: np.ndarray, sample_rate: int) -> dict:
        emb = self._embed(audio, sample_rate)
        self._voices[speaker_id] = emb
        return {"speaker_id": speaker_id, "enrolled": True, "dev_mode": True}

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float64)
        b = np.asarray(b, dtype=np.float64)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
        return float(np.dot(a, b) / denom)

    def verify(self, speaker_id: str, audio: np.ndarray, sample_rate: int, threshold: float = 0.70) -> dict:
        if speaker_id not in self._voices:
            return {"speaker_id": speaker_id, "verified": False, "score": 0.0, "reason": "not_enrolled"}
        emb = self._embed(audio, sample_rate)
        score = self.similarity(self._voices[speaker_id], emb)
        return {"speaker_id": speaker_id, "verified": bool(score >= threshold), "score": score, "dev_mode": True}
