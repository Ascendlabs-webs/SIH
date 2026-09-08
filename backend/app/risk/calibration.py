"""Score calibration layer: raw model score -> calibrated probability -> risk engine.

The raw AASIST P(spoof) and the calibrated probability are kept separate:
AnalysisResult.model_raw_score always carries the unmodified model output,
while the rolling risk engine consumes the calibrated value. With no
calibration file present (the default), the mapping is the identity, i.e.
behaviour is byte-for-byte the raw model output.

A calibration file (models/calibration.json) holds a Platt-scaling fit
produced by scripts/evaluate_model.py --calibrate-out on LABELLED validation
data. Never fit it on demo beeps or a handful of files and never ship an
experimental fit as production: see models/EVALUATION.md.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np


def resolve_calibration_path(given: str | None) -> Path:
    if given and Path(given).is_absolute():
        return Path(given)
    repo_root = Path(__file__).resolve().parents[3]
    if given:
        cand = Path(given)
        return cand if cand.is_file() else repo_root / given
    return repo_root / "models" / "calibration.json"


def eer_from_scores(y_true: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """EER + threshold over unique score thresholds (higher = more spoof)."""
    order = np.argsort(np.asarray(scores))
    s = np.asarray(scores, dtype=float)[order]
    y = np.asarray(y_true, dtype=int)[order]
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan"), float("nan")
    thrs = np.unique(s)
    fars = np.array([((s >= t) & (y == 0)).sum() / n_neg for t in thrs])
    frrs = np.array([((s < t) & (y == 1)).sum() / n_pos for t in thrs])
    i = int(np.argmin(np.abs(fars - frrs)))
    return float((fars[i] + frrs[i]) / 2.0), float(thrs[i])


def youden_threshold(y_true: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """Threshold maximising Youden J (TPR - FPR). Returns (threshold, J)."""
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(scores, dtype=float)
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5, 0.0
    best_j, best_t = -1.0, 0.5
    for t in np.unique(np.concatenate(([0.0], s, [1.0]))):
        p = (s >= t).astype(int)
        tpr = float(((p == 1) & (y == 1)).sum() / n_pos)
        fpr = float(((p == 1) & (y == 0)).sum() / n_neg)
        if tpr - fpr > best_j:
            best_j, best_t = tpr - fpr, float(t)
    return best_t, best_j


class ScoreCalibrator:
    """Platt scaling on P(spoof): calibrated = sigmoid(a * p + b)."""

    def __init__(self, path: str | None = None):
        env_path = os.environ.get("VAUTH_CALIBRATION_PATH")
        self.path = resolve_calibration_path(path or env_path)
        self.a: float | None = None
        self.b: float | None = None
        self.fitted = False
        self.meta: dict = {}
        try:
            if self.path.is_file():
                payload = json.loads(self.path.read_text())
                if payload.get("method") == "platt_logistic" and payload.get("fitted", True):
                    self.a = float(payload["a"])
                    self.b = float(payload["b"])
                    self.fitted = True
                    self.meta = {k: v for k, v in payload.items() if k not in ("a", "b")}
        except Exception:
            self.fitted = False

    def apply(self, p_spoof: float) -> float:
        p = float(np.clip(p_spoof, 0.0, 1.0))
        if not self.fitted or self.a is None or self.b is None:
            return p
        z = self.a * p + self.b
        return float(1.0 / (1.0 + math.exp(-max(-500.0, min(500.0, z)))))

    def describe(self) -> dict:
        return {"fitted": self.fitted, "path": str(self.path),
                "a": self.a, "b": self.b, "meta": self.meta}
