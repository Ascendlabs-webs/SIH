"""Rolling risk: weighted average of recent window scores (no score jumping)."""
from __future__ import annotations

from collections import deque

import numpy as np


class RollingRiskEngine:
    def __init__(
        self,
        window_size: int = 5,
        weights: list[float] | None = None,
        green_t: float = 0.60,
        yellow_t: float = 0.75,
        orange_t: float = 0.90,
    ):
        self.window_size = max(1, int(window_size))
        if weights and len(weights) == self.window_size:
            w = np.array(weights, dtype=np.float64)
        else:
            # Recency-weighted: newest window counts most (linear ramp).
            w = np.arange(1, self.window_size + 1, dtype=np.float64)
        self.weights = w / w.sum()
        self.green_t = green_t
        self.yellow_t = yellow_t
        self.orange_t = orange_t
        self.scores: deque[float] = deque(maxlen=self.window_size)

    def update(self, model_score: float) -> dict:
        self.scores.append(float(np.clip(model_score, 0.0, 1.0)))
        return self.snapshot()

    def snapshot(self) -> dict:
        if not self.scores:
            return {"risk_score": 0.0, "alert_level": "GREEN", "num_windows": 0}
        vals = np.array(list(self.scores), dtype=np.float64)
        w = self.weights[-len(vals):]
        w = w / w.sum()
        risk = float(np.dot(vals, w))
        return {"risk_score": risk, "alert_level": self.level_for(risk), "num_windows": len(vals)}

    def level_for(self, risk: float) -> str:
        if risk > self.orange_t:
            return "RED"
        if risk > self.yellow_t:
            return "ORANGE"
        if risk >= self.green_t:
            return "YELLOW"
        return "GREEN"

    def reset(self) -> None:
        self.scores.clear()

    @property
    def history(self) -> list[float]:
        return list(self.scores)
