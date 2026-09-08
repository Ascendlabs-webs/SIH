"""WebRTC adapter: browser audio -> the exact same analysis pipeline.

No second detector lives here. WebRTC (or plain browser AudioContext capture)
delivers Float32 PCM frames; this module converts them to 16 kHz mono float32
which flows into preprocess -> features -> detector -> risk like every other
source (uploads, mic WS frames, Twilio mu-law, demo files).

Browser side (see frontend/src/hooks/useMic.ts):
  getUserMedia -> AudioContext -> downsample to 16 kHz -> int16 or float32 LE
  -> binary WebSocket frames to /ws/audio (encoding "pcm16" or "f32").

A full SFU/media-server (e.g. aiortc) integration is future work; the frame
contract below is what it must produce, so swapping the transport later does
not touch the analyzer.
"""
from __future__ import annotations

import numpy as np

from app.audio.preprocessor import TARGET_SR, resample, to_mono


def float32_bytes_to_mono(data: bytes, sample_rate: int) -> np.ndarray:
    """Decode little-endian float32 browser PCM -> 16 kHz mono float32."""
    if len(data) % 4 != 0:
        raise ValueError("Float32 frame length must be a multiple of 4 bytes")
    audio = np.frombuffer(data, dtype=np.float32).astype(np.float32)
    if audio.size == 0:
        raise ValueError("Empty WebRTC audio frame")
    audio = np.clip(to_mono(audio), -1.0, 1.0)
    if int(sample_rate) != TARGET_SR:
        audio = resample(audio, int(sample_rate), TARGET_SR)
    return audio


def int16_bytes_to_mono(data: bytes, sample_rate: int) -> np.ndarray:
    """Decode little-endian int16 browser PCM -> 16 kHz mono float32."""
    from app.audio.codecs import decode_pcm16

    audio = decode_pcm16(data)
    if audio.size == 0:
        raise ValueError("Empty WebRTC audio frame")
    if int(sample_rate) != TARGET_SR:
        audio = resample(audio, int(sample_rate), TARGET_SR)
    return audio


WEBRTC_SETUP = {
    "transport": "WebSocket /ws/audio (binary frames)",
    "encodings": ["pcm16", "f32"],
    "target_sample_rate": TARGET_SR,
    "notes": (
        "Capture via getUserMedia + AudioContext, downsample to 16 kHz, send "
        "binary frames. Server buffers into 2.5 s windows and returns "
        '{"type":"analysis_result", ...} per window. No Twilio/credentials needed.'
    ),
}
