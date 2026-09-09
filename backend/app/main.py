"""VAuth FastAPI entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.twilio import router as twilio_router
from app.config import get_settings
from app.integrations.banking.routes import router as banking_router
from app.websocket.audio_ws import router as ws_router

settings = get_settings()
log = logging.getLogger("vauth")


def _warmup_sync() -> None:
    """Trigger librosa/numba cold compile once so the first real request is fast."""
    import numpy as np

    from app.features.extractor import AudioFeatureExtractor

    sr = 16000
    t = np.arange(sr) / sr
    tone = (0.3 * np.sin(2 * np.pi * 160 * t)).astype(np.float32)
    AudioFeatureExtractor().extract(tone, sr)


async def _warmup() -> None:
    try:
        await asyncio.to_thread(_warmup_sync)
        log.info("Feature pipeline warmed up")
    except Exception as exc:
        log.warning("Warmup failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload the configured detector so the mode (DEMO vs REAL ML) and any
    # ML-unavailable warning are settled once at startup, not per request.
    from app.services.pipeline import get_pipeline

    pipe = get_pipeline()
    det = pipe.detector
    warn = getattr(pipe, "detector_warning", None)
    if warn:
        log.warning("DETECTOR FALLBACK: %s", warn)
    else:
        log.info(
            "Detector ready: name=%s model=%s device=%s",
            getattr(det, "name", "?"),
            getattr(det, "model_name", getattr(det, "name", "?")),
            getattr(det, "device", "n/a"),
        )
    asyncio.create_task(_warmup())
    yield

app = FastAPI(title="VAuth", version=settings.version, description="AI-powered real-time voice cloning impersonation detection (defensive).", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(twilio_router, prefix="/api")
app.include_router(banking_router, prefix="/api/banking")
app.include_router(ws_router)


@app.get("/")
def root() -> dict:
    return {
        "app": "VAuth",
        "version": settings.version,
        "message": "Voice authenticity API. See /docs, /health, /api/status.",
        "demo_label": "DEMO MODEL — Replace with trained anti-spoof model for production evaluation",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "VAuth", "version": settings.version}


@app.get("/bank", include_in_schema=False)
def bank_ui():
    """Separate simulated-banking UI (demo only, no real money)."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    page = Path(__file__).resolve().parent / "integrations" / "banking" / "static" / "bank.html"
    return FileResponse(str(page), media_type="text/html")
