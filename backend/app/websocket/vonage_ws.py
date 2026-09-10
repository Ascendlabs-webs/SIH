"""Vonage Voice API WebSocket receiver: PCM16 16 kHz -> SAME AnalysisPipeline.

Vonage protocol (per official Voice API WebSocket docs):
  - binary frames: raw 16-bit signed little-endian PCM at the NCCO rate
    (we request audio/l16;rate=16000), ~20 ms slices.
  - text frames: JSON events, e.g. {"event": "websocket:connected",
    "content-type": "audio/l16;rate=16000"}, DTMF, cleared/notify.

Adapter duties only: accept, validate, convert to the internal float32
representation, buffer per-connection 2.5 s windows, call
AnalysisPipeline.process_window(), return existing AnalysisResult objects.
"""
from __future__ import annotations

import json
import logging

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.audio.codecs import decode_pcm16
from app.config import get_settings
from app.services.pipeline import AnalysisPipeline

log = logging.getLogger("vauth")
router = APIRouter()


def _auth_ok(ws: WebSocket) -> bool:
    """Explicit Vonage auth policy (never silent).

    - VONAGE_ENABLED=false            -> accept (local dev / simulator use).
    - enabled + verify + token set    -> require matching Bearer token, where
      the operator puts the same token in the NCCO websocket `headers`
      (Vonage custom-auth scheme) or VONAGE_WS_AUTH_TOKEN handling.
    - enabled + verify + NO token     -> refuse clearly (fail, don't downgrade).
    - enabled + verify=false          -> accept with a loud warning (explicit).
    """
    s = get_settings()
    if not s.vonage_enabled:
        return True
    if s.vonage_verify_jwt:
        if not s.vonage_ws_auth_token:
            log.error("Vonage enabled with VONAGE_VERIFY_JWT=true but no "
                      "VONAGE_WS_AUTH_TOKEN: refusing WebSocket connection.")
            return False
        auth = ws.headers.get("authorization", "")
        if auth != f"Bearer {s.vonage_ws_auth_token}":
            log.warning("Vonage WebSocket rejected: missing/invalid Bearer token.")
            return False
        return True
    log.warning("Vonage WebSocket accepted WITHOUT verification "
                "(VONAGE_VERIFY_JWT=false is explicitly configured).")
    return True


@router.websocket("/ws/vonage")
async def ws_vonage(ws: WebSocket):
    await ws.accept()
    if not _auth_ok(ws):
        await ws.close(code=4401, reason="Vonage verification failed")
        return
    settings = get_settings()
    pipeline = AnalysisPipeline()
    pcm_buffer = np.zeros(0, dtype=np.float32)
    context = {"call_type": "vonage", "caller_known": False,
               "pending_transaction": False}
    call_id = "unknown"

    async def flush_windows():
        nonlocal pcm_buffer
        win_len = int(settings.window_seconds * settings.target_sample_rate)
        while len(pcm_buffer) >= win_len:
            window = pcm_buffer[:win_len]
            pcm_buffer = pcm_buffer[win_len:]
            result = pipeline.process_window(window, settings.target_sample_rate, context)
            await ws.send_json({"type": "analysis_result", **result.model_dump()})

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            data = msg.get("bytes")
            if data is not None:
                if len(data) == 0 or len(data) % 2 != 0:
                    log.warning("Vonage call %s: malformed binary frame (%d bytes); ignored.",
                                call_id, len(data))
                    continue
                if len(data) > settings.max_ws_bytes:
                    log.warning("Vonage call %s: oversized frame; ignored.", call_id)
                    continue
                try:
                    chunk = decode_pcm16(data)  # 16-bit LE PCM @16 kHz per NCCO
                except Exception as exc:
                    log.warning("Vonage call %s: undecodable frame (%s); ignored.", call_id, exc)
                    continue
                pcm_buffer = np.concatenate([pcm_buffer, chunk]).astype(np.float32)
                max_buf = int(settings.max_audio_seconds * settings.target_sample_rate)
                if len(pcm_buffer) > max_buf:
                    pcm_buffer = pcm_buffer[-max_buf:]
                await flush_windows()
                continue
            text = msg.get("text")
            if not text:
                continue
            try:
                frame = json.loads(text)
            except Exception:
                log.warning("Vonage call %s: malformed JSON text frame; ignored.", call_id)
                continue
            if not isinstance(frame, dict):
                log.warning("Vonage call %s: unexpected non-object frame; ignored.", call_id)
                continue
            event = frame.get("event", "")
            if event == "websocket:connected":
                call_id = str(frame.get("uuid", frame.get("call_uuid", "unknown")))
                log.info("Vonage stream connected: call=%s format=%s",
                         call_id, frame.get("content-type", "audio/l16;rate=16000"))
                await ws.send_json({"type": "ready", "source": "vonage"})
            elif event == "websocket:dtmf":
                log.info("Vonage call %s: DTMF digit=%s duration=%s", call_id,
                         frame.get("digit"), frame.get("duration"))
            elif event in ("websocket:cleared", "websocket:notify"):
                log.info("Vonage call %s: event %s", call_id, event)
            elif event:
                log.info("Vonage call %s: unexpected event %r; ignored.", call_id, event)
            else:
                log.warning("Vonage call %s: text frame without event; ignored.", call_id)
    except WebSocketDisconnect:
        return
    except RuntimeError:
        return
