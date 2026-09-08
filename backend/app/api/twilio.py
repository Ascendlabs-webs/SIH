"""Twilio Media Streams adapter (optional; never required for local demo).

Architecture:
  Phone -> Twilio -> Media Streams (WebSocket, 8 kHz mu-law) -> /ws/twilio
  -> decode mu-law -> 16 kHz pipeline -> risk -> dashboard

Setup (documented in README + models/README):
  1. Expose this server publicly (e.g. ngrok).
  2. Set TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_PHONE_NUMBER env vars.
  3. Point the Twilio phone number's voice webhook at POST /api/twilio/voice,
     which returns TwiML with a <Stream> to wss://<host>/ws/twilio.
  4. Twilio sends JSON frames {event: connected/media/stop, media: {payload}}.

This MVP does NOT intercept ordinary cellular calls — only streams the user
explicitly routes via Twilio Media Streams.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app.config import get_settings

router = APIRouter()


@router.post("/twilio/voice")
def twilio_voice() -> Response:
    s = get_settings()
    host = "YOUR_PUBLIC_HOST"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Stream url='wss://{host}/ws/twilio' track='inbound_track' />"
        "</Response>"
    )
    return Response(content=twiml, media_type="text/xml")


@router.get("/twilio/config")
def twilio_config() -> dict:
    s = get_settings()
    return {
        "configured": bool(s.twilio_account_sid and s.twilio_auth_token),
        "stream_url": "wss://<public-host>/ws/twilio",
        "note": "Set TWILIO_* env vars and point the voice webhook at POST /api/twilio/voice. Local demo works without this.",
    }
