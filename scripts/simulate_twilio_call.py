"""Simulate an inbound Twilio Media Streams call against /ws/twilio.

Sends the exact frame sequence Twilio would send (connected -> 20 ms 8 kHz
mu-law media frames -> stop) for a local WAV file, and prints the
analysis_result messages VAuth returns. Use when no paid Twilio account
is available (trial accounts cannot open Media Streams).

Usage:
  py scripts/simulate_twilio_call.py --file data/demo/demo_real_speech.wav
  py scripts/simulate_twilio_call.py --file data/demo/demo_synthetic_tts.wav --url ws://127.0.0.1:8000/ws/twilio
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'backend'))

import numpy as np

import soundfile as sf
import websockets

from app.audio.preprocessor import resample


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True)
    ap.add_argument('--url', default='ws://127.0.0.1:8000/ws/twilio')
    ap.add_argument('--frame-ms', type=float, default=20.0)
    ap.add_argument('--realtime', action='store_true',
                    help='pace frames like a live call (one frame every --frame-ms)')
    args = ap.parse_args()

    from app.audio.codecs import encode_mulaw_8k

    audio, sr = sf.read(args.file, dtype='float32', always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio8 = resample(audio, int(sr), 8000) if int(sr) != 8000 else audio
    wire = encode_mulaw_8k(audio8)
    step = int(8000 * args.frame_ms / 1000)
    frames = [wire[i:i + step] for i in range(0, len(wire), step)]
    print(f'loaded {args.file}: {len(audio) / int(sr):.1f}s -> {len(frames)} Twilio-style frames')

    async with websockets.connect(args.url, max_size=4 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0"}))
        print('server:', await ws.recv())
        results = 0
        t_next = asyncio.get_event_loop().time()
        for fr in frames:
            await ws.send(json.dumps({"event": "media", "streamSid": "DEMO",
                                      "media": {"payload": base64.b64encode(fr).decode()}}))
            if args.realtime:
                # mimic a live call: one frame every frame-ms milliseconds
                t_next += args.frame_ms / 1000.0
                delay = t_next - asyncio.get_event_loop().time()
                if delay > 0:
                    await asyncio.sleep(delay)
            # drain any completed windows without blocking
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                except asyncio.TimeoutError:
                    break
                body = json.loads(msg)
                if body.get('type') == 'analysis_result':
                    results += 1
                    print('window %d: risk=%.4f level=%s class=%s' % (
                        results, body['risk_score'], body['alert_level'],
                        body['classification']))
        await ws.send(json.dumps({"event": "stop"}))
        # final drain (server closes after stop)
        try:
            while True:
                try:
                    body = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                except asyncio.TimeoutError:
                    break
                if body.get('type') == 'analysis_result':
                    results += 1
                    print('window %d: risk=%.4f level=%s class=%s' % (
                        results, body['risk_score'], body['alert_level'],
                        body['classification']))
        except Exception:
            pass
        print(f'done: {results} analysis windows via simulated Twilio stream')


if __name__ == '__main__':
    asyncio.run(main())
