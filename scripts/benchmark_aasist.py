"""Benchmark AASIST on this machine: latency + raw outputs on reference audio.

Records MEASURED numbers only. Reads data/demo/*.wav windows (2.5 s) through
MLVoiceDetector.score_waveform and prints per-window logits, probabilities,
and timing. Reference validation clips (*_ref.wav) are used when present.

Usage: py scripts/benchmark_aasist.py  (run from backend/ or repo root)
"""
from __future__ import annotations

import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'backend'))

import numpy as np  # noqa: E402

import soundfile as sf  # noqa: E402

from app.models.ml_detector import MLVoiceDetector  # noqa: E402


def bench(det, audio, sr, n_win=4, repeats=5):
    rows = []
    for k in range(n_win):
        win = audio[k * int(sr * 2.5):(k + 1) * int(sr * 2.5)]
        if len(win) < int(sr * 2.0):
            break
        # warm + timed repeats
        r = det.score_waveform(win, sr)
        ts = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            det.score_waveform(win, sr)
            ts.append((time.perf_counter() - t0) * 1000.0)
        rows.append((r['spoof_logit'], r['bonafide_logit'],
                     r['synthetic_probability'], min(ts), sum(ts) / len(ts)))
    return rows


def main():
    t0 = time.perf_counter()
    det = MLVoiceDetector()
    print('model=%s params=%d device=%s load=%.1fs' % (
        det.model_name, det.num_params, det.device, (time.perf_counter() - t0)))
    for name in ('demo_real.wav', 'demo_synthetic.wav',
                 'real_human_ref.wav', 'tts_spoof_ref.wav', 'arctic_ref.wav'):
        path = os.path.join(REPO, 'data', 'demo', name)
        if not os.path.exists(path):
            print('%-22s MISSING (skip)' % name)
            continue
        audio, sr = sf.read(path, dtype='float32')
        print('== %s (%.1fs @ %dHz)' % (name, len(audio) / sr, sr))
        for k, (ls, lb, ps, mn, mean) in enumerate(bench(det, audio, sr)):
            print('  win%d spoof_logit=%+.3f bonafide_logit=%+.3f synth_prob=%.4f '
                  'infer_min=%.1fms infer_mean=%.1fms' % (k, ls, lb, ps, mn, mean))


if __name__ == '__main__':
    main()
