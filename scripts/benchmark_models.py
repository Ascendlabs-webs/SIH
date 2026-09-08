"""Benchmark all VAuth ML detectors on the SAME data, SAME windows, SAME metrics.

Models: aasist (torch) | spectra | spectra3 | w2v2_aasist (ONNX CPU).
Dataset: data/eval/{real,synthetic} (or --real/--synthetic overrides).
Per model: load time, RAM delta, per-window inference latency, accuracy,
precision, recall, F1, ROC-AUC, EER, ROC curve points, score distributions,
clean + telephony. No thresholds tuned, no calibration — ranking only.

Usage: py scripts/benchmark_models.py [--out data/eval/benchmark_models.json]
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'backend'))
sys.path.insert(0, os.path.join(REPO, 'scripts'))

import numpy as np

import evaluate_model as E
from app.audio.preprocessor import chunk_audio, telephony_degrade

MODELS = ('aasist', 'spectra', 'spectra3', 'w2v2_aasist')


def rss_mb() -> float:
    import psutil

    return float(psutil.Process().memory_info().rss / 1e6)


def roc_points(y: np.ndarray, s: np.ndarray, n: int = 200) -> dict:
    thrs = np.unique(np.concatenate(([0.0], s, [1.0])))
    if len(thrs) > n:
        thrs = np.linspace(0.0, 1.0, n)
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    fpr, tpr = [], []
    for t in thrs:
        p = (s >= t).astype(int)
        tpr.append(float(((p == 1) & (y == 1)).sum() / max(1, n_pos)))
        fpr.append(float(((p == 1) & (y == 0)).sum() / max(1, n_neg)))
    return {'fpr': [round(v, 4) for v in fpr], 'tpr': [round(v, 4) for v in tpr]}


def bench_one(key: str, real: str, synthetic: str, window_sec: float) -> dict:
    gc.collect()
    rss0 = rss_mb()
    t0 = time.perf_counter()
    det = E.build_detector(key)
    load_s = time.perf_counter() - t0
    rss1 = rss_mb()
    out: dict = {'detector': key, 'model_name': det.model_name,
                 'num_params': int(getattr(det, 'num_params', 0) or 0),
                 'load_sec': round(load_s, 2), 'ram_delta_mb': round(rss1 - rss0, 1),
                 'rss_after_mb': round(rss1, 1)}
    items = ([(0, p) for _, p in E.list_groups(real)] +
             [(1, p) for _, p in E.list_groups(synthetic)])
    lat: list[float] = []
    rows = []
    for label, path in items:
        audio = E.load_mono_16k(path)
        for variant, wav in (('clean', audio), ('telephony', telephony_degrade(audio))):
            scores = []
            for w in chunk_audio(wav, 16000, window_sec):
                t1 = time.perf_counter()
                try:
                    s = det.score_waveform(w, 16000)['synthetic_probability']
                except ValueError:
                    continue
                if variant == 'clean':
                    lat.append((time.perf_counter() - t1) * 1000.0)
                scores.append(s)
            a = np.asarray(scores) if scores else np.array([0.0])
            rows.append({'label': label, 'file': os.path.basename(path),
                         'variant': variant, 'score': float(a.mean()),
                         'windows': len(scores)})
            print(f'  [{key:10s}] {variant:9s} {os.path.basename(path):32s} '
                  f'{rows[-1]["score"]:.4f}', flush=True)
    out['latency_ms'] = {'min': round(float(min(lat)), 1), 'mean': round(float(sum(lat) / len(lat)), 1),
                         'n_windows': len(lat)}
    for variant in ('clean', 'telephony'):
        sub = [r for r in rows if r['variant'] == variant]
        y = np.array([r['label'] for r in sub])
        s = np.array([r['score'] for r in sub])
        m = E.metrics_block(y, s)
        m['roc_curve'] = roc_points(y, s)
        m['n_genuine'] = int((y == 0).sum())
        m['n_synthetic'] = int((y == 1).sum())
        out[variant] = m
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--real', default=os.path.join(REPO, 'data', 'eval', 'real'))
    ap.add_argument('--synthetic', default=os.path.join(REPO, 'data', 'eval', 'synthetic'))
    ap.add_argument('--window-sec', type=float, default=2.5)
    ap.add_argument('--out', default=os.path.join(REPO, 'data', 'eval', 'benchmark_models.json'))
    ap.add_argument('--models', nargs='*', default=list(MODELS))
    args = ap.parse_args()

    try:
        import torch
        vram = {'cuda_available': bool(torch.cuda.is_available()),
                'note': 'all detectors run on CPU; VRAM unused'}
    except Exception:
        vram = {'cuda_available': False, 'note': 'torch unavailable'}
    report = {'window_sec': args.window_sec, 'vram': vram, 'models': {}}
    for key in args.models:
        print(f'== {key} ==', flush=True)
        report['models'][key] = bench_one(key, args.real, args.synthetic, args.window_sec)
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2)
    print('wrote', args.out)
    print('| model | AUC | EER | F1 | prec | rec | infer mean | RAM dMB |')
    print('|---|---|---|---|---|---|---|---|')
    for key in args.models:
        m = report['models'][key]['clean']
        l = report['models'][key]['latency_ms']
        print(f"| {key} | {m['roc_auc']:.3f} | {m['eer']:.3f} | {m['f1']:.3f} | "
              f"{m['precision']:.3f} | {m['recall']:.3f} | {l['mean']:.0f} ms | "
              f"{report['models'][key]['ram_delta_mb']:.0f} MB |")


if __name__ == '__main__':
    main()
