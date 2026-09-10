"""Vonage Voice API adapter (optional input adapter; disabled by default).

Architecture:
  Phone -> Vonage Voice API -> answer webhook (NCCO) -> wss://<host>/ws/vonage
  -> PCM16 16 kHz binary frames -> the EXISTING AnalysisPipeline -> risk ->
  dashboard/history.

This module only answers webhooks and reports status. Audio handling lives
in app/websocket/vonage_ws.py. No analysis, risk, or protection logic here.

VAuth only analyzes explicitly routed/authorized audio streams; it cannot
intercept ordinary cellular calls.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings

log = logging.getLogger("vauth")

router = APIRouter()

AUDIO_CONTENT_TYPE = "audio/l16;rate=16000"


def _adapter_state() -> dict:
    s = get_settings()
    enabled = bool(s.vonage_enabled)
    host = s.vonage_public_ws_host.strip().replace("https://", "").replace("http://", "").rstrip("/")
    return {"enabled": enabled, "host": host, "settings": s}


@router.get("/vonage/config")
def vonage_config() -> dict:
    """Safe setup/status info only — never secrets."""
    st = _adapter_state()
    s = st["settings"]
    return {
        "enabled": st["enabled"],
        "configured": bool(st["enabled"] and st["host"]),
        "stream_url": f"wss://{st['host']}/ws/vonage" if st["host"] else "",
        "audio_format": AUDIO_CONTENT_TYPE,
        "verify_jwt": bool(s.vonage_verify_jwt),
        "has_application_id": bool(s.vonage_application_id),
        "has_private_key": bool(s.vonage_private_key_path),
        "has_number": bool(s.vonage_number),
        "note": ("Set VONAGE_ENABLED=true, VONAGE_PUBLIC_WS_HOST and "
                 "VONAGE_WS_AUTH_TOKEN, then point the Vonage Voice Application "
                 "answer webhook at POST /api/vonage/answer. Disabled by default; "
                 "local demo works without Vonage."),
    }


@router.post("/vonage/answer")
async def vonage_answer(request: Request):
    """Vonage answer webhook -> NCCO connecting the call to /ws/vonage."""
    st = _adapter_state()
    if not st["enabled"]:
        log.warning("Vonage answer webhook hit while VONAGE_ENABLED=false")
        raise HTTPException(status_code=503,
                            detail="Vonage integration disabled (VONAGE_ENABLED=false).")
    if not st["host"]:
        log.error("Vonage enabled but VONAGE_PUBLIC_WS_HOST is missing")
        raise HTTPException(status_code=500,
                            detail="VONAGE_PUBLIC_WS_HOST is not configured; "
                                   "cannot generate a valid NCCO stream URL.")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and (body.get("from") or body.get("uuid")):
        log.info("Vonage inbound call: from=%s uuid=%s",
                 body.get("from"), body.get("uuid"))
    ncco = [
        {
            "action": "connect",
            "eventType": "synchronous",
            "eventUrl": [f"https://{st['host']}/api/vonage/event"],
            "endpoint": [
                {
                    "type": "websocket",
                    "uri": f"wss://{st['host']}/ws/vonage",
                    "content-type": AUDIO_CONTENT_TYPE,
                    "headers": {"x-vauth-source": "vonage"},
                }
            ],
        }
    ]
    return JSONResponse(ncco)


@router.post("/vonage/event")
async def vonage_event(request: Request):
    """Vonage call lifecycle notifications (started/answered/completed/failed).

    Records/logs lifecycle info only. No raw audio, no new database; analysis
    results remain visible via the existing /api/history mechanism.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict):
        log.info("Vonage event: status=%s uuid=%s from=%s",
                 body.get("status"), body.get("uuid"), body.get("from"))
    else:
        log.info("Vonage event: non-JSON payload ignored")
    return JSONResponse({})
