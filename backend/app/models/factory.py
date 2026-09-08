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


def build_detector(name: str) -> BaseVoiceDetector:
    """Construct a detector by canonical name; raises on failure (no fallback)."""
    if name == "demo":
        det = DemoVoiceDetector()
        det._fallback_warning = None  # type: ignore[attr-defined]
        return det
    if name in ("ml", "aasist"):
        from app.models.ml_detector import MLVoiceDetector
        from app.models.onnx_detector import AASISTDetector

        cls = MLVoiceDetector if name == "ml" else AASISTDetector
        det = cls()
        det._fallback_warning = None  # type: ignore[attr-defined]
        return det
    if name == "spectra":
        from app.models.onnx_detector import SpectraAASISTDetector

        det = SpectraAASISTDetector()
        det._fallback_warning = None  # type: ignore[attr-defined]
        return det
    if name == "spectra3":
        from app.models.onnx_detector import SpectraAASIST3Detector

        det = SpectraAASIST3Detector()
        det._fallback_warning = None  # type: ignore[attr-defined]
        return det
    if name == "w2v2_aasist":
        from app.models.onnx_detector import W2V2AASISTDetector

        det = W2V2AASISTDetector()
        det._fallback_warning = None  # type: ignore[attr-defined]
        return det
    raise ValueError(f"Unknown detector '{name}'. "
                     "Use demo|ml|aasist|spectra|spectra3|w2v2_aasist.")


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
