"""Timing helpers (real measured latency, never faked)."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def timed() -> Iterator[dict]:
    out = {"ms": 0.0}
    t0 = time.perf_counter()
    try:
        yield out
    finally:
        out["ms"] = (time.perf_counter() - t0) * 1000.0
