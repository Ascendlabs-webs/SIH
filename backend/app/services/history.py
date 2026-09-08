"""In-memory history store (timestamps + scores only, never raw audio)."""
from __future__ import annotations

import threading
from collections import deque
from typing import List

from app.config import get_settings
from app.schemas import AnalysisResult


class HistoryStore:
    def __init__(self, limit: int = 200):
        self._lock = threading.Lock()
        self._items: deque[dict] = deque(maxlen=limit)

    def add(self, result: AnalysisResult) -> None:
        with self._lock:
            self._items.append(result.model_dump())

    def list(self, limit: int = 100) -> List[dict]:
        with self._lock:
            items = list(self._items)[-limit:]
        return items

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


_history = HistoryStore(limit=get_settings().history_limit)


def get_history() -> HistoryStore:
    return _history
