"""Pydantic schemas for VAuth API + WebSocket."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AlertLevel = Literal["GREEN", "YELLOW", "ORANGE", "RED"]
Classification = Literal["REAL", "SYNTHETIC"]


class CallContext(BaseModel):
    caller_known: bool = False
    pending_transaction: bool = False
    sensitive_action: bool = False
    call_type: Literal["webrtc", "twilio", "upload", "demo", "mic"] = "demo"


class AnalyzeRequest(BaseModel):
    """JSON analysis request. Provide ONE of samples / audio_base64."""

    samples: Optional[List[float]] = Field(default=None, description="Mono float samples in [-1, 1]")
    audio_base64: Optional[str] = Field(default=None, description="Base64-encoded WAV bytes or raw int16 PCM")
    sample_rate: int = Field(default=16000, ge=1000, le=96000)
    encoding: Literal["wav", "pcm16", "mulaw8k"] = "wav"
    context: CallContext = Field(default_factory=CallContext)


class FeatureSummary(BaseModel):
    mfcc_mean: List[float] = []
    spectral_centroid_mean: float = 0.0
    spectral_bandwidth_mean: float = 0.0
    spectral_rolloff_mean: float = 0.0
    spectral_flux_mean: float = 0.0
    zcr_mean: float = 0.0
    rms_mean: float = 0.0
    f0_mean: float = 0.0
    f0_std: float = 0.0
    silence_ratio: float = 0.0
    vad_active_ratio: float = 0.0


class AnalysisResult(BaseModel):
    risk_score: float
    alert_level: AlertLevel
    classification: Classification
    confidence: float
    recommendation: str
    timestamp: str = Field(default_factory=utcnow_iso)
    window_duration: float = 2.5
    latency_ms: float = 0.0
    latency_breakdown: Dict[str, float] = Field(default_factory=dict)
    model_raw_score: float = 0.0
    score_calibrated: bool = False
    audio_risk: float = 0.0
    context_risk: float = 0.0
    requires_secondary_verification: bool = False
    protection_state: str = "NORMAL"
    protection_actions: List[str] = Field(default_factory=list)
    sample_rate: int = 16000
    vad_active: bool = True
    detector: str = "demo"
    features: Optional[FeatureSummary] = None


class HistoryResponse(BaseModel):
    count: int
    results: List[AnalysisResult]


class StatusResponse(BaseModel):
    app: str = "VAuth"
    version: str = "0.1.0"
    detector: str = "demo"
    detector_label: str = "DEMO MODEL — Replace with trained anti-spoof model for production evaluation"
    target_sample_rate: int = 16000
    window_seconds: float = 2.5
    store_raw_audio: bool = False
    rolling_window_size: int = 5
    history_count: int = 0


class DemoStartRequest(BaseModel):
    scenario: Literal["real", "synthetic", "genuine", "real_speech"] = "real"
    context: CallContext = Field(default_factory=CallContext)


class DemoStartResponse(BaseModel):
    scenario: str
    windows: int
    results: List[AnalysisResult]
    message: str
    audio_source: str = ""


class ProtectionActionRequest(BaseModel):
    action: Literal["request_otp", "request_callback", "mark_verified", "escalate", "reset"] = "request_otp"


class ProtectionStateResponse(BaseModel):
    state: str
    required_actions: List[str] = []
    pending_challenges: List[Dict[str, Any]] = []
    last_alert_level: str = "GREEN"
    transitioned: bool = False
    updated_at: str = ""
