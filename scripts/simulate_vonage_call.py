"""SIMULATOR ONLY — not a real Vonage call.

Replays a local WAV file as Vonage Voice API WebSocket frames (initial
{"event": "websocket:connected"} text frame, then raw PCM16 16 kHz mono
binary frames ~20 ms each) against /ws/vonage, printing the analysis_result
messages VAuth returns. No Vonage credentials needed or used.

Usage:
  py scripts/simulate_vonage_call.py --file data/demo/demo_real_speech.wav
  py scripts/simulate_vonage_call.py --file data/demo/demo_synthetic_tts.wav --url ws://127.0.0.1:8000/ws/vonage
"""
from __future__ import annotations

import argparse
import asyncio
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
    ap = argparse.ArgumentParser(description='SIMULATED Vonage call (no credentials)')
    ap.add_argument('--file', required=True)
    ap.add_argument('--url', default='ws://127.0.0.1:8000/ws/vonage')
    ap.add_argument('--frame-ms', type=float, default=20.0)
    ap.add_argument('--realtime', action='store_true',
                    help='pace frames like a live call instead of as fast as possible')
    args = ap.parse_args()

    audio, sr = sf.read(args.file, dtype='float32', always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if int(sr) != 16000:
        audio = resample(audio, int(sr), 16000)
    pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
    step = int(16000 * args.frame_ms / 1000) * 2
    frames = [pcm[i:i + step] for i in range(0, len(pcm), step)]
    print(f'[SIMULATED Vonage call] {args.file}: {len(audio) / 16000:.1f}s -> '
          f'{len(frames)} PCM16 frames (realtime={args.realtime})')

    async with websockets.connect(args.url, max_size=4 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"event": "websocket:connected",
                                  "content-type": "audio/l16;rate=16000"}))
        print('server:', await asyncio.wait_for(ws.recv(), 30))
        results = 0
        clock = asyncio.get_event_loop().time()
        for fr in frames:
            await ws.send(fr)
            if args.realtime:
                clock += args.frame_ms / 1000.0
                delay = clock - asyncio.get_event_loop().time()
                if delay > 0:
                    await asyncio.sleep(delay)
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
        # final drain: inference (esp. large models) lags behind the burst
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    break
                body = json.loads(msg)
                if body.get('type') == 'analysis_result':
                    results += 1
                    print('window %d: risk=%.4f level=%s class=%s' % (
                        results, body['risk_score'], body['alert_level'],
                        body['classification']))
        except Exception:
            pass
        print(f'done: {results} analysis windows via SIMULATED Vonage stream '
              f'(sub-window tail is dropped on disconnect, same as mic path)')


if __name__ == '__main__':
    asyncio.run(main())
