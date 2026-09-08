"""Core analysis pipeline: preprocess -> features -> inference -> risk -> alert.

Raw audio is discarded after inference (STORE_RAW_AUDIO=false default).
Only scores / levels / metadata / feature summaries are retained.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.audio.preprocessor import preprocess_audio
from app.config import get_settings
from app.features.extractor import AudioFeatureExtractor
from app.models.factory import get_detector
from app.risk.alerts import AlertEngine
from app.risk.calibration import ScoreCalibrator
from app.risk.context import ContextRiskEngine
from app.risk.rolling import RollingRiskEngine
from app.schemas import AnalysisResult, FeatureSummary
from app.services.history import get_history
from app.services.protection import ProtectionEngine


class AnalysisPipeline:
    """Stateful per-session pipeline (holds its own rolling engine)."""

    def __init__(self, detector_name: str | None = None):
        settings = get_settings()
        self.settings = settings
        self.detector = get_detector(detector_name)
        self.detector_name = getattr(self.detector, "name", "demo")
        self.extractor = AudioFeatureExtractor()
        self.rolling = RollingRiskEngine(
            window_size=settings.rolling_window_size,
            green_t=settings.green_threshold,
            yellow_t=settings.yellow_threshold,
            orange_t=settings.orange_threshold,
        )
        self.context_engine = ContextRiskEngine()
        self.alerts = AlertEngine()
        self.protection = ProtectionEngine()
        # Calibration: raw model score -> calibrated probability. Identity by
        # default; the raw value is always preserved on the result.
        self.calibrator = ScoreCalibrator()
        # Explicit DEMO-vs-ML surfacing: factory attaches _fallback_warning
        # when ML was requested but unavailable (never silent).
        self.detector_warning: str | None = getattr(self.detector, "_fallback_warning", None)

    def process_window(
        self,
        audio: np.ndarray,
        sample_rate: int,
        context: dict | None = None,
        store: bool = True,
    ) -> AnalysisResult:
        t0 = time.perf_counter()
        ctx = context or {}
        t_pre = time.perf_counter()
        pre = preprocess_audio(np.asarray(audio, dtype=np.float32), int(sample_rate), self.settings.target_sample_rate)
        clean = pre["audio"]
        sr = pre["sample_rate"]
        preprocess_ms = (time.perf_counter() - t_pre) * 1000.0

        t_feat = time.perf_counter()
        feats = self.extractor.extract(clean, sr)
        features_ms = (time.perf_counter() - t_feat) * 1000.0

        t_inf = time.perf_counter()
        # Waveform detectors (AASIST) score the preprocessed 16 kHz window
        # directly; feature detectors use the MFCC/spectral/prosody vector.
        # Signal-analysis extraction above always runs regardless.
        if getattr(self.detector, "uses_waveform", False):
            det = self.detector.predict_waveform(clean, sr)
        else:
            det = self.detector.predict(feats)
        inference_ms = (time.perf_counter() - t_inf) * 1000.0
        raw_model_score = float(det["synthetic_probability"])
        model_score = float(self.calibrator.apply(raw_model_score))

        t_risk = time.perf_counter()
        roll = self.rolling.update(model_score)
        audio_risk = float(roll["risk_score"])
        ctx_out = self.context_engine.score(audio_risk, ctx)
        final_risk = float(ctx_out["final_risk"])
        level = self.rolling.level_for(final_risk)
        alert = self.alerts.decide(level, bool(ctx.get("sensitive_action", False)))
        classification = "SYNTHETIC" if final_risk >= 0.6 else "REAL"
        protection = self.protection.observe(level, bool(ctx.get("sensitive_action", False)))
        risk_ms = (time.perf_counter() - t_risk) * 1000.0
        latency_ms = (time.perf_counter() - t0) * 1000.0

        result = AnalysisResult(
            risk_score=round(final_risk, 4),
            alert_level=level,  # type: ignore[arg-type]
            classification=classification,  # type: ignore[arg-type]
            confidence=round(float(det.get("confidence", model_score)), 4),
            recommendation=alert["recommendation"],
            window_duration=round(float(pre["duration_sec"]), 3),
            latency_ms=round(latency_ms, 2),
            latency_breakdown={
                "preprocess_ms": round(preprocess_ms, 2),
                "features_ms": round(features_ms, 2),
                "inference_ms": round(inference_ms, 2),
                "risk_ms": round(risk_ms, 2),
            },
            model_raw_score=round(raw_model_score, 4),
            score_calibrated=bool(self.calibrator.fitted),
            audio_risk=round(audio_risk, 4),
            context_risk=round(float(ctx_out["context_boost"]), 4),
            requires_secondary_verification=bool(alert["requires_secondary_verification"]),
            protection_state=str(protection["state"]),
            protection_actions=list(protection["required_actions"]),
            sample_rate=int(sr),
            vad_active=bool(feats.get("vad_active", True)),
            detector=self.detector_name,
            features=FeatureSummary(
                mfcc_mean=[round(float(v), 3) for v in feats.get("mfcc", [])[:13]],
                spectral_centroid_mean=round(float(feats["spectral_centroid"]["mean"]), 2),
                spectral_bandwidth_mean=round(float(feats["spectral_bandwidth"]["mean"]), 2),
                spectral_rolloff_mean=round(float(feats["spectral_rolloff"]["mean"]), 2),
                spectral_flux_mean=round(float(feats["spectral_flux"]["mean"]), 4),
                zcr_mean=round(float(feats["zcr"]["mean"]), 4),
                rms_mean=round(float(feats["rms"]["mean"]), 4),
                f0_mean=round(float(feats.get("f0_mean", 0.0)), 2),
                f0_std=round(float(feats.get("f0_std", 0.0)), 2),
                silence_ratio=round(float(feats.get("silence_ratio", 0.0)), 3),
                vad_active_ratio=round(float(feats.get("vad_active_ratio", 0.0)), 3),
            ),
        )
        if store:
            get_history().add(result)
        return result

    def reset(self) -> None:
        self.rolling.reset()
        self.protection.reset()


# Global (REST/demo) pipeline singleton
_pipeline: AnalysisPipeline | None = None


def get_pipeline() -> AnalysisPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AnalysisPipeline()
    return _pipeline


def reset_pipeline() -> AnalysisPipeline:
    global _pipeline
    _pipeline = AnalysisPipeline()
    get_history().clear()
    return _pipeline
