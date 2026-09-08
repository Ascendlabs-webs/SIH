"""Real-time WebSocket pipeline: /ws/audio (dashboard/mic/WebRTC) + /ws/twilio (8k mu-law).

/ws/audio protocol (JSON text frames; binary PCM frames also accepted):
  -> {"type": "config", "sample_rate": 16000, "encoding": "pcm16|f32|wav|mulaw8k", "context": {...}}
  -> {"type": "audio", "audio_base64": "<pcm16|f32|wav|mulaw bytes b64>", "sample_rate":..., "encoding":...}
     or raw binary frame = little-endian int16 (or float32 for encoding "f32")
     mono at configured sample_rate
  <- {"type": "analysis_result", ...AnalysisResult}
  <- {"type": "error", "detail": ...}
  -> {"type": "reset"}  (clears rolling state for this connection)

/ws/twilio protocol: Twilio Media Streams JSON frames (connected/media/stop).
"""
from __future__ import annotations

import base64
import json

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.audio.codecs import decode_mulaw_8k
from app.audio.preprocessor import chunk_audio
from app.audio.webrtc import float32_bytes_to_mono, int16_bytes_to_mono
from app.config import get_settings
from app.services.pipeline import AnalysisPipeline

router = APIRouter()


@router.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    settings = get_settings()
    pipeline = AnalysisPipeline()
    sample_rate = settings.target_sample_rate
    encoding = "pcm16"
    context: dict = {"call_type": "webrtc"}
    pcm_buffer = np.zeros(0, dtype=np.float32)

    async def flush_windows():
        nonlocal pcm_buffer
        win_len = int(settings.window_seconds * settings.target_sample_rate)
        while len(pcm_buffer) >= win_len:
            window = pcm_buffer[:win_len]
            pcm_buffer = pcm_buffer[win_len:]
            result = pipeline.process_window(window, settings.target_sample_rate, context)
            await ws.send_json({"type": "analysis_result", **result.model_dump()})

    def decode_binary(data: bytes) -> np.ndarray:
        if encoding == "mulaw8k":
            chunk = decode_mulaw_8k(data)
            from app.audio.preprocessor import resample as _rs

            return _rs(chunk, 8000, settings.target_sample_rate)
        if encoding == "f32":
            return float32_bytes_to_mono(data, sample_rate)
        return int16_bytes_to_mono(data, sample_rate)

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            if "bytes" in msg and msg["bytes"] is not None:
                data: bytes = msg["bytes"]
                if len(data) > settings.max_ws_bytes:
                    await ws.send_json({"type": "error", "detail": "Binary frame too large"})
                    continue
                try:
                    chunk = decode_binary(data)
                    pcm_buffer = np.concatenate([pcm_buffer, chunk]).astype(np.float32)
                    # cap buffer to avoid unbounded growth
                    max_buf = int(settings.max_audio_seconds * settings.target_sample_rate)
                    if len(pcm_buffer) > max_buf:
                        pcm_buffer = pcm_buffer[-max_buf:]
                    await flush_windows()
                except Exception as exc:
                    await ws.send_json({"type": "error", "detail": f"Malformed binary audio: {exc}"})
                continue

            text = msg.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                await ws.send_json({"type": "error", "detail": "Invalid JSON"})
                continue
            mtype = payload.get("type", "audio")

            if mtype == "config":
                try:
                    sample_rate = int(payload.get("sample_rate", settings.target_sample_rate))
                    encoding = str(payload.get("encoding", "pcm16"))
                    if encoding not in ("pcm16", "f32", "wav", "mulaw8k"):
                        raise ValueError(f"Unsupported encoding: {encoding}")
                    if not 1000 <= sample_rate <= 96000:
                        raise ValueError(f"Unsupported sample_rate: {sample_rate}")
                    if payload.get("context"):
                        context = dict(payload["context"])
                    pcm_buffer = np.zeros(0, dtype=np.float32)
                    pipeline.reset()
                    await ws.send_json({"type": "ready", "sample_rate": sample_rate, "encoding": encoding})
                except Exception as exc:
                    await ws.send_json({"type": "error", "detail": f"Bad config: {exc}"})
            elif mtype == "reset":
                pipeline.reset()
                pcm_buffer = np.zeros(0, dtype=np.float32)
                await ws.send_json({"type": "ready", "reset": True})
            elif mtype in ("audio", "chunk"):
                try:
                    b64 = payload.get("audio_base64", "")
                    if not b64:
                        raise ValueError("Missing audio_base64")
                    raw = base64.b64decode(b64, validate=False)
                    if len(raw) > settings.max_ws_bytes:
                        await ws.send_json({"type": "error", "detail": "Audio chunk too large"})
                        continue
                    enc = str(payload.get("encoding", encoding))
                    if enc not in ("pcm16", "f32", "wav", "mulaw8k"):
                        await ws.send_json({"type": "error", "detail": f"Unsupported encoding: {enc}"})
                        continue
                    try:
                        sr = int(payload.get("sample_rate", sample_rate))
                    except (TypeError, ValueError):
                        await ws.send_json({"type": "error", "detail": "Invalid sample_rate"})
                        continue
                    if payload.get("context"):
                        context = dict(payload["context"])
                    if enc == "wav":
                        from app.audio.preprocessor import decode_input

                        chunk, cs = decode_input(raw, sr, "wav")
                        if cs != settings.target_sample_rate:
                            from app.audio.preprocessor import resample as _rs

                            chunk = _rs(chunk, cs, settings.target_sample_rate)
                    elif enc == "mulaw8k":
                        chunk = decode_mulaw_8k(raw)
                        from app.audio.preprocessor import resample as _rs

                        chunk = _rs(chunk, 8000, settings.target_sample_rate)
                    elif enc == "f32":
                        chunk = float32_bytes_to_mono(raw, sr)
                    else:
                        chunk = int16_bytes_to_mono(raw, sr)
                    pcm_buffer = np.concatenate([pcm_buffer, chunk]).astype(np.float32)
                    max_buf = int(settings.max_audio_seconds * settings.target_sample_rate)
                    if len(pcm_buffer) > max_buf:
                        pcm_buffer = pcm_buffer[-max_buf:]
                    await flush_windows()
                except Exception as exc:
                    await ws.send_json({"type": "error", "detail": f"Malformed audio: {exc}"})
            elif mtype == "ping":
                await ws.send_json({"type": "pong"})
            else:
                await ws.send_json({"type": "error", "detail": f"Unknown message type: {mtype}"})
    except WebSocketDisconnect:
        return
    except RuntimeError:
        # TestClient/closed-socket teardown racing the receive loop.
        return


@router.websocket("/ws/twilio")
async def ws_twilio(ws: WebSocket):
    """Twilio Media Streams receiver: 8 kHz mu-law -> 16 kHz pipeline."""
    await ws.accept()
    settings = get_settings()
    pipeline = AnalysisPipeline()
    from app.audio.preprocessor import resample as _rs

    pcm_buffer = np.zeros(0, dtype=np.float32)
    context = {"call_type": "twilio", "caller_known": False}
    try:
        while True:
            text = await ws.receive_text()
            try:
                frame = json.loads(text)
            except Exception:
                continue
            event = frame.get("event")
            if event == "connected":
                await ws.send_json({"type": "ready", "source": "twilio"})
            elif event == "media":
                try:
                    payload_b64 = frame.get("media", {}).get("payload", "")
                    if not payload_b64:
                        continue
                    raw = base64.b64decode(payload_b64)
                    chunk8 = decode_mulaw_8k(raw)
                    chunk16 = _rs(chunk8, 8000, settings.target_sample_rate)
                    pcm_buffer = np.concatenate([pcm_buffer, chunk16]).astype(np.float32)
                    win_len = int(settings.window_seconds * settings.target_sample_rate)
                    while len(pcm_buffer) >= win_len:
                        window = pcm_buffer[:win_len]
                        pcm_buffer = pcm_buffer[win_len:]
                        result = pipeline.process_window(window, settings.target_sample_rate, context)
                        await ws.send_json({"type": "analysis_result", **result.model_dump()})
                except Exception:
                    continue
            elif event == "stop":
                break
    except WebSocketDisconnect:
        return
