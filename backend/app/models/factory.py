"""Detector factory: explicit DEMO vs REAL ML modes.

VAUTH_DETECTOR=demo         -> DemoVoiceDetector (deterministic heuristic, labelled).
VAUTH_DETECTOR=ml|aasist    -> AASIST, official ASVspoof2019-LA checkpoint (torch).
VAUTH_DETECTOR=spectra      -> Spectra-AASIST (lab260, ONNX).
VAUTH_DETECTOR=spectra3     -> Spectra-AASIST3 (lab260, ONNX).
VAUTH_DETECTOR=w2v2_aasist  -> W2V2-AASIST (SSL_Anti-spoofing LA, ONNX).

If an ML mode is requested but cannot load, we NEVER silently pretend DEMO
is ML: a DemoVoiceDetector is returned with a prominent _fallback_warning
surfaced via /api/status, /api/model/status and the dashboard banner.
"""
from __future__ import annotations

from app.config import get_settings
from app.models.base import BaseVoiceDetector
from app.models.demo_detector import DemoVoiceDetector


def _demo_with_warning(message: str) -> DemoVoiceDetector:
    det = DemoVoiceDetector()
    det._fallback_warning = message  # type: ignore[attr-defined]
    return det


# Registry of detector names -> detector classes. Introspectable WITHOUT
# loading any model weights (construction happens only in build_detector).
REGISTRY: dict[str, type] = {}


def _registry() -> dict[str, type]:
    global REGISTRY
    if not REGISTRY:
        from app.models.demo_detector import DemoVoiceDetector as Demo
        from app.models.ml_detector import MLVoiceDetector
        from app.models.onnx_detector import (AASISTDetector,
                                              SpectraAASIST3Detector,
                                              SpectraAASISTDetector,
                                              W2V2AASISTDetector)

        REGISTRY = {
            "demo": Demo,
            "ml": MLVoiceDetector,
            "aasist": AASISTDetector,
            "spectra": SpectraAASISTDetector,
            "spectra3": SpectraAASIST3Detector,
            "w2v2_aasist": W2V2AASISTDetector,
        }
    return REGISTRY


def build_detector(name: str) -> BaseVoiceDetector:
    """Construct a detector by canonical name; raises on failure (no fallback)."""
    if name == "demo":
        det = DemoVoiceDetector()
        det._fallback_warning = None  # type: ignore[attr-defined]
        return det
    registry = _registry()
    if name not in registry:
        raise ValueError(f"Unknown detector '{name}'. "
                         f"Use {'|'.join(sorted(registry))}.")
    det = registry[name]()
    det._fallback_warning = None  # type: ignore[attr-defined]
    return det


def get_detector(name: str | None = None) -> BaseVoiceDetector:
    want = (name or get_settings().detector or "demo").lower()
    if want == "demo":
        return build_detector("demo")
    try:
        return build_detector(want)
    except Exception as exc:
        return _demo_with_warning(
            f"VAUTH_DETECTOR={want} requested but the model failed to load ({exc}). "
            "Running DEMO detector instead — this is NOT real ML inference."
        )
