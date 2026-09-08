"""Evaluate the configured VAuth ML detector on labelled audio directories.

Usage:
  py scripts/evaluate_model.py --real DIR --synthetic DIR --output report.json
  py scripts/evaluate_model.py --real DIR --synthetic DIR --output r.json --telephony
  py scripts/evaluate_model.py --real DIR --synthetic DIR --output r.json --calibrate-out models/calibration.json

Directory layout (flat or grouped for future per-language eval):
  DIR/*.wav                      -> group "default"
  DIR/<group>/*.wav              -> group "<group>" (e.g. en, hi, ta, te)

Each file: mono-ified, resampled to 16 kHz, split into --window-sec windows,
scored per window by MLVoiceDetector (raw waveform), aggregated per file
(--aggregate mean|max). --telephony additionally scores the 8 kHz mu-law
degraded copy (16k -> 8k -> mulaw -> decode -> 16k) and reports the delta.

Report (JSON): counts, accuracy/precision/recall/F1 @0.5, ROC-AUC, EER +
EER threshold, Youden-J threshold recommendation, confusion matrix, score
distributions, per-group metrics, telephony comparison, calibration fit
(Platt scaling; skipped honestly when too few samples).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'backend'))

import numpy as np

import soundfile as sf

from app.audio.preprocessor import chunk_audio, resample, telephony_degrade
from app.models.base import BaseVoiceDetector
from app.models.ml_detector import MLVoiceDetector
from app.risk.calibration import eer_from_scores as compute_eer
from app.risk.calibration import youden_threshold

DETECTORS = ('ml', 'aasist', 'spectra', 'spectra3', 'w2v2_aasist')


def build_detector(which: str) -> BaseVoiceDetector:
    if which == 'ml':
        return MLVoiceDetector()
    if which == 'aasist':
        from app.models.onnx_detector import AASISTDetector

        return AASISTDetector()
    if which == 'spectra':
        from app.models.onnx_detector import SpectraAASISTDetector

        return SpectraAASISTDetector()
    if which == 'spectra3':
        from app.models.onnx_detector import SpectraAASIST3Detector

        return SpectraAASIST3Detector()
    if which == 'w2v2_aasist':
        from app.models.onnx_detector import W2V2AASISTDetector

        return W2V2AASISTDetector()
    raise SystemExit(f'unknown --detector {which}; use {DETECTORS}')

TARGET_SR = 16000


def list_groups(root: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not os.path.isdir(root):
        raise SystemExit(f'not a directory: {root}')
    subs = sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
    wavs_top = sorted(f for f in os.listdir(root)
                      if f.lower().endswith('.wav'))
    if wavs_top and not subs:
        return [('default', os.path.join(root, f)) for f in wavs_top]
    if not subs:
        raise SystemExit(f'no .wav files or group subdirs in {root}')
    for g in subs:
        for f in sorted(os.listdir(os.path.join(root, g))):
            if f.lower().endswith('.wav'):
                out.append((g, os.path.join(root, g, f)))
    if not out:
        raise SystemExit(f'no .wav files under {root}')
    return out


def load_mono_16k(path: str) -> np.ndarray:
    audio, sr = sf.read(path, dtype='float32', always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1).astype(np.float32)
    if int(sr) != TARGET_SR:
        audio = resample(audio, int(sr), TARGET_SR)
    return np.clip(audio, -1.0, 1.0)


def file_score(det: BaseVoiceDetector, audio: np.ndarray,
               window_sec: float, aggregate: str) -> tuple[float, int]:
    wins = chunk_audio(audio, TARGET_SR, window_sec)
    scores = []
    for w in wins:
        try:
            scores.append(det.score_waveform(w, TARGET_SR)['synthetic_probability'])
        except ValueError:
            continue  # silent window: no evidence, skip honestly
    if not scores:
        return 0.0, 0
    arr = np.asarray(scores)
    return (float(arr.max()) if aggregate == 'max' else float(arr.mean())), len(scores)


def dist(scores: np.ndarray) -> dict:
    if len(scores) == 0:
        return {'n': 0}
    hist, edges = np.histogram(scores, bins=10, range=(0.0, 1.0))
    return {'n': int(len(scores)), 'mean': float(scores.mean()),
            'std': float(scores.std()), 'min': float(scores.min()),
            'max': float(scores.max()),
            'hist10': [int(h) for h in hist],
            'edges10': [round(float(e), 2) for e in edges]}


def metrics_block(y_true: np.ndarray, scores: np.ndarray, thr: float = 0.5) -> dict:
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_score, recall_score, roc_auc_score)

    pred = (scores >= thr).astype(int)
    eer, eer_thr = compute_eer(y_true, scores)
    best_t, best_j = youden_threshold(y_true, scores)
    n_pos, n_neg = int(y_true.sum()), int(len(y_true) - y_true.sum())
    auc = float(roc_auc_score(y_true, scores)) if n_pos and n_neg else float('nan')
    cm = confusion_matrix(y_true, pred, labels=[0, 1]).tolist()
    return {'n': int(len(scores)), 'threshold': thr,
            'accuracy': float(accuracy_score(y_true, pred)),
            'precision': float(precision_score(y_true, pred, zero_division=0)),
            'recall': float(recall_score(y_true, pred, zero_division=0)),
            'f1': float(f1_score(y_true, pred, zero_division=0)),
            'roc_auc': auc, 'eer': eer, 'eer_threshold': eer_thr,
            'youden_threshold': best_t, 'youden_j': best_j,
            'confusion_matrix': {'tn': cm[0][0], 'fp': cm[0][1],
                                 'fn': cm[1][0], 'tp': cm[1][1]},
            'genuine_scores': dist(scores[y_true == 0]),
            'synthetic_scores': dist(scores[y_true == 1])}


def fit_platt(scores: np.ndarray, y_true: np.ndarray) -> dict | None:
    n_pos, n_neg = int(y_true.sum()), int(len(y_true) - y_true.sum())
    if n_pos < 6 or n_neg < 6:
        return {'fitted': False,
                'reason': f'too few samples (genuine={n_neg}, synthetic={n_pos}); need >=6 each'}
    from sklearn.linear_model import LogisticRegression

    clf = LogisticRegression().fit(scores.reshape(-1, 1), y_true)
    return {'fitted': True, 'method': 'platt_logistic',
            'a': float(clf.coef_[0][0]), 'b': float(clf.intercept_[0])}


def main() -> None:
    ap = argparse.ArgumentParser(description='Evaluate VAuth ML detector')
    ap.add_argument('--real', required=True)
    ap.add_argument('--synthetic', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--telephony', action='store_true')
    ap.add_argument('--window-sec', type=float, default=2.5)
    ap.add_argument('--aggregate', choices=('mean', 'max'), default='mean')
    ap.add_argument('--detector', choices=DETECTORS, default='ml')
    ap.add_argument('--calibrate-out', default=None)
    args = ap.parse_args()

    det = build_detector(args.detector)
    print(f'model={det.model_name} device={det.device} telephony={args.telephony}')

    items: list[tuple[str, int, str]] = (
        [(g, 0, p) for g, p in list_groups(args.real)] +
        [(g, 1, p) for g, p in list_groups(args.synthetic)])
    rows = []
    for group, label, path in items:
        audio = load_mono_16k(path)
        variants = {'clean': audio}
        if args.telephony:
            variants['telephony'] = telephony_degrade(audio)
        for variant, wav in variants.items():
            s, nw = file_score(det, wav, args.window_sec, args.aggregate)
            rows.append({'group': group, 'label': label, 'file': path,
                         'variant': variant, 'score': s, 'windows': nw})
            print(f'[{variant:9s}] {os.path.basename(path):28s} score={s:.4f} win={nw}')

    report: dict = {'model': det.model_name, 'device': str(det.device),
                    'window_sec': args.window_sec, 'aggregate': args.aggregate,
                    'telephony_enabled': args.telephony, 'files': rows}
    for variant in ({'clean'} | ({'telephony'} if args.telephony else set())):
        sub = [r for r in rows if r['variant'] == variant]
        y = np.array([r['label'] for r in sub])
        s = np.array([r['score'] for r in sub])
        report[variant] = metrics_block(y, s)
        report[variant]['n_genuine'] = int((y == 0).sum())
        report[variant]['n_synthetic'] = int((y == 1).sum())
        groups: dict[str, dict] = {}
        for g in sorted(set(r['group'] for r in sub)):
            gs = [r for r in sub if r['group'] == g]
            gy = np.array([r['label'] for r in gs])
            gsc = np.array([r['score'] for r in gs])
            if len(set(gy.tolist())) == 2:
                groups[g] = metrics_block(gy, gsc)
            else:
                groups[g] = {'n': len(gs), 'note': 'single class in group'}
        report[variant]['groups'] = groups

    clean = [r for r in rows if r['variant'] == 'clean']
    cal = fit_platt(np.array([r['score'] for r in clean]),
                    np.array([r['label'] for r in clean]))
    report['calibration'] = cal
    if args.calibrate_out:
        if cal.get('fitted'):
            payload = {'method': cal['method'], 'a': cal['a'], 'b': cal['b'],
                       'model': det.model_name,
                       'fitted_on': {'n_genuine': report['clean']['n_genuine'],
                                     'n_synthetic': report['clean']['n_synthetic']},
                       'eer_threshold': report['clean']['eer_threshold'],
                       'youden_threshold': report['clean']['youden_threshold'],
                       'warning': 'Experimental: fitted on a small local set, NOT production validation.'}
            with open(args.calibrate_out, 'w') as f:
                json.dump(payload, f, indent=2)
            print('wrote calibration', args.calibrate_out)
        else:
            print('calibration NOT fitted:', cal.get('reason'))

    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)
    print('wrote', args.output)
    for variant in ('clean', 'telephony'):
        if variant in report and 'accuracy' in report[variant]:
            m = report[variant]
            print(f'[{variant}] acc={m["accuracy"]:.3f} f1={m["f1"]:.3f} '
                  f'auc={m["roc_auc"]:.3f} eer={m["eer"]:.3f}@thr={m["eer_threshold"]:.3f} '
                  f'youden_thr={m["youden_threshold"]:.3f}')


if __name__ == '__main__':
    main()
