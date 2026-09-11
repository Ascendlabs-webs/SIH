"""REST routes for VAuth MVP."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.audio.preprocessor import chunk_audio, decode_input, preprocess_audio
from app.schemas import (
    AnalysisResult,
    AnalyzeRequest,
    DemoStartRequest,
    DemoStartResponse,
    HistoryResponse,
    ProtectionActionRequest,
    ProtectionStateResponse,
    StatusResponse,
)
from app.services.demo import demo_path
from app.services.history import get_history
from app.services.pipeline import get_pipeline, reset_pipeline
from app.utils.audio_io import decode_base64_audio, samples_to_array

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    s = get_settings()
    return StatusResponse(
        detector=s.detector if s.detector in ("demo", "ml") else "demo",
        target_sample_rate=s.target_sample_rate,
        window_seconds=s.window_seconds,
        store_raw_audio=s.store_raw_audio,
        rolling_window_size=s.rolling_window_size,
        history_count=len(get_history()),
    )


@router.post("/analyze", response_model=AnalysisResult)
def analyze(req: AnalyzeRequest) -> AnalysisResult:
    s = get_settings()
    try:
        if req.samples is not None:
            if len(req.samples) > int(s.max_audio_seconds * req.sample_rate):
                raise HTTPException(status_code=413, detail="Audio too long")
            audio = samples_to_array(req.samples)
            sr = int(req.sample_rate)
        elif req.audio_base64:
            raw_len = len(req.audio_base64) * 3 // 4
            if raw_len > s.max_upload_bytes:
                raise HTTPException(status_code=413, detail="Audio payload too large")
            audio, sr = decode_base64_audio(req.audio_base64, int(req.sample_rate), req.encoding)
        else:
            raise HTTPException(status_code=422, detail="Provide samples or audio_base64")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Malformed audio: {exc}") from exc
    if audio.size == 0:
        raise HTTPException(status_code=400, detail="Empty audio")
    if audio.size > int(s.max_audio_seconds * max(sr, 1)):
        raise HTTPException(status_code=413, detail="Audio too long")
    # Analyse first window only for single-shot calls (document window_duration).
    pre = preprocess_audio(audio, sr, s.target_sample_rate)
    clean = pre["audio"]
    windows = chunk_audio(clean, s.target_sample_rate, s.window_seconds)
    if not windows:
        raise HTTPException(status_code=400, detail="Audio too short for one analysis window")
    # Fresh pipeline per upload: an uploaded file is an independent sample,
    # so leftover rolling history from earlier sessions must not dilute it.
    # (Result is still stored to global history.)
    from app.services.pipeline import AnalysisPipeline

    return AnalysisPipeline().process_window(windows[0], s.target_sample_rate, req.context.model_dump())


@router.post("/analyze-file", response_model=AnalysisResult)
async def analyze_file(
    file: UploadFile = File(...),
    caller_known: bool = False,
    pending_transaction: bool = False,
    sensitive_action: bool = False,
    call_type: str = "upload",
) -> AnalysisResult:
    s = get_settings()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(data) > s.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    name = (file.filename or "").lower()
    try:
        if name.endswith(".wav") or data[:4] == b"RIFF":
            audio, sr = decode_input(data, s.target_sample_rate, "wav")
        else:
            # assume raw int16 PCM at target rate
            audio, sr = decode_input(data, s.target_sample_rate, "pcm16")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Malformed audio: {exc}") from exc
    pre = preprocess_audio(audio, sr, s.target_sample_rate)
    windows = chunk_audio(pre["audio"], s.target_sample_rate, s.window_seconds)
    if not windows:
        raise HTTPException(status_code=400, detail="Audio too short")
    ctx = {"caller_known": caller_known, "pending_transaction": pending_transaction,
           "sensitive_action": sensitive_action, "call_type": call_type}
    from app.services.pipeline import AnalysisPipeline

    return AnalysisPipeline().process_window(windows[0], s.target_sample_rate, ctx)


@router.post("/demo/start", response_model=DemoStartResponse)
def demo_start(req: DemoStartRequest) -> DemoStartResponse:
    from app.services.demo import run_demo

    scenario = {"synthetic": "synthetic", "real_speech": "real_speech"}.get(req.scenario, "real")
    try:
        out = run_demo(scenario, req.context.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    label = {"synthetic": "Synthetic voice demo", "real_speech": "Recorded human speech demo"}.get(scenario, "Genuine voice demo")
    det_name = getattr(get_pipeline().detector, "model_name", "demo")
    return DemoStartResponse(
        scenario=scenario,
        windows=out["windows"],
        results=out["results"],
        message=f"{label}: processed {out['windows']} windows through the real pipeline "
                f"({det_name}, source: {out.get('audio_source', '')}).",
        audio_source=out.get("audio_source", ""),
    )


@router.post("/demo/stop")
def demo_stop() -> dict:
    reset_pipeline()
    return {"stopped": True}


@router.post("/demo/reset")
def demo_reset() -> dict:
    """Alias for /demo/stop (session reset)."""
    reset_pipeline()
    return {"reset": True}


@router.get("/protection/state", response_model=ProtectionStateResponse)
def protection_state() -> ProtectionStateResponse:
    snap = get_pipeline().protection.snapshot()
    return ProtectionStateResponse(**snap)


@router.post("/protection/action", response_model=ProtectionStateResponse)
def protection_action(req: ProtectionActionRequest) -> ProtectionStateResponse:
    try:
        snap = get_pipeline().protection.act(req.action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProtectionStateResponse(**snap)


@router.get("/demo/audio")
def demo_audio(scenario: str = "real"):
    scenario = {"synthetic": "synthetic", "real_speech": "real_speech"}.get(scenario, "real")
    path = demo_path(scenario)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Demo audio not generated yet. Run scripts/generate_demo_audio.py")
    return FileResponse(str(path), media_type="audio/wav", filename=path.name)


@router.get("/history", response_model=HistoryResponse)
def history(limit: int = 100) -> HistoryResponse:
    items = get_history().list(limit=min(max(1, limit), 200))
    return HistoryResponse(count=len(items), results=items)  # type: ignore[arg-type]


@router.get("/webrtc/config")
def webrtc_config() -> dict:
    from app.audio.webrtc import WEBRTC_SETUP

    return dict(WEBRTC_SETUP)


class AssistantAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    # Optional caller-side reading (risk/alert from the asker's own dashboard).
    # When present it takes precedence over global history, which may contain
    # windows from other sessions.
    client_state: Optional[Dict[str, Any]] = None


@router.post("/assistant/ask")
def assistant_ask(req: AssistantAskRequest) -> dict:
    from app.assistant.engine import answer

    return answer(req.question, req.client_state)


@router.get("/model/status")
def model_status() -> dict:
    """Startup/model status: which detector is REALLY running (DEMO vs REAL ML)."""
    s = get_settings()
    pipe = get_pipeline()
    det = pipe.detector
    name = getattr(det, "name", "demo")
    is_demo = bool(getattr(det, "is_demo", True))
    return {
        "detector_mode": s.detector,  # requested via VAUTH_DETECTOR
        "active_detector": name,
        "is_demo": is_demo,
        "mode_label": "DEMO" if is_demo else "REAL ML",
        "model_loaded": bool(not is_demo and getattr(det, "loaded", False)),
        "model_name": getattr(det, "model_name", "DemoVoiceDetector"),
        "model_path": str(getattr(det, "model_path", "")),
        "device": str(getattr(det, "device", "cpu")),
        "num_params": int(getattr(det, "num_params", 0) or 0),
        "warning": getattr(pipe, "detector_warning", None),
        "calibration": pipe.calibrator.describe(),
    }
