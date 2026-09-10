"""Process-wide cache of loaded detector models (weights + sessions).

Each AnalysisPipeline keeps its OWN rolling-risk / protection / history
state, but the heavy neural nets are stateless at inference time, so all
pipelines share one loaded instance per checkpoint. Without this, every
WebSocket connection pays a multi-GB reload (and concurrent reloads can
exhaust RAM and kill the server process).
Thread-safe: creation is serialized with a lock; inference calls themselves
are read-only (torch.no_grad / onnxruntime Run are thread-safe for this use).
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_models: dict[str, object] = {}


def shared(key: str, loader):
    """Return the cached object for key, building it once via loader()."""
    obj = _models.get(key)
    if obj is not None:
        return obj
    with _lock:
        obj = _models.get(key)
        if obj is None:
            obj = loader()
            _models[key] = obj
        return obj


def cache_info() -> dict:
    with _lock:
        return {"cached_models": sorted(_models)}
