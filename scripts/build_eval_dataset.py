"""Build a small, legal, reproducible local eval set: same-statement pairs.

Genuine : CMU Arctic bdl recordings (Carnegie Mellon, research use;
          prompts are public-domain Gutenberg text).
Synthetic: edge-TTS readings of the SAME transcripts (our own generations).

Layout:
  data/eval/real/<uttid>.wav
  data/eval/synthetic/<uttid>__<voice>.wav
  data/eval/MANIFEST.json

Usage: py scripts/build_eval_dataset.py [--n 8] [--out data/eval]
Skips files that already exist (idempotent).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import urllib.request

BASE = 'http://www.festvox.org/cmu_arctic/cmu_arctic/cmu_us_bdl_arctic'
VOICES = ('en-US-AriaNeural', 'en-US-GuyNeural')


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(url, timeout=60).read()


def transcripts(n: int) -> list[tuple[str, str]]:
    import re
    raw = fetch(BASE + '/etc/txt.done.data').decode()
    pairs = re.findall(r'\(\s*(\S+)\s+"([^"]+)"\s*\)', raw)
    return [(u, t) for u, t in pairs if len(t.split()) >= 6][:n]


async def tts(text: str, voice: str, path: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice).save(path + '.mp3')
    # decode mp3 -> 16 kHz mono wav with PyAV (no ffmpeg binary needed)
    import io
    import numpy as np
    import soundfile as sf
    import av
    chunks = []
    with av.open(io.BytesIO(open(path + '.mp3', 'rb').read())) as c:
        stream = next(s for s in c.streams if s.type == 'audio')
        rs = av.AudioResampler(format='s16', layout='mono', rate=16000)
        for frame in c.decode(stream):
            for rf in rs.resample(frame):
                chunks.append(rf.to_ndarray())
    pcm = np.concatenate(chunks, axis=-1).astype(np.float32) / 32768.0
    sf.write(path, np.asarray(pcm).ravel().astype(np.float32), 16000)
    os.remove(path + '.mp3')


async def main_async(n: int, out: str) -> None:
    real_d = os.path.join(out, 'real')
    syn_d = os.path.join(out, 'synthetic')
    os.makedirs(real_d, exist_ok=True)
    os.makedirs(syn_d, exist_ok=True)
    manifest = {'genuine_source': 'CMU Arctic cmu_us_bdl_arctic (research use)',
                'synthetic_source': 'edge-tts generations of the same transcripts',
                'pairs': []}
    for uttid, text in transcripts(n):
        rp = os.path.join(real_d, uttid + '.wav')
        if not os.path.exists(rp):
            open(rp, 'wb').write(fetch(f'{BASE}/wav/{uttid}.wav'))
            print('real', uttid)
        for voice in VOICES:
            sp = os.path.join(syn_d, f'{uttid}__{voice}.wav')
            if not os.path.exists(sp):
                await tts(text, voice, sp)
                print('synthetic', uttid, voice)
        manifest['pairs'].append({'uttid': uttid, 'text': text})
    with open(os.path.join(out, 'MANIFEST.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    print('wrote', os.path.join(out, 'MANIFEST.json'))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=8)
    ap.add_argument('--out', default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'eval'))
    args = ap.parse_args()
    asyncio.run(main_async(args.n, args.out))


if __name__ == '__main__':
    main()
