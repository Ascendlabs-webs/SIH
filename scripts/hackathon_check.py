"""Hackathon scenario check: genuine recording vs AI-cloned SAME statement.

Runs both clips through the identical VAuth path (decode -> mono -> 16 kHz ->
normalize -> noise gate -> VAD -> 2.5 s windows -> AASIST waveform score +
demo-detector features -> rolling risk -> alerts) and writes a
machine-readable JSON comparison.

Usage:
  py scripts/hackathon_check.py --real teammate.wav --synthetic clone.wav \
      --statement "the spoken sentence" --output data/eval/hackathon_report.json

No scores are manipulated: raw AASIST logits/probabilities are reported
per window alongside the demo-detector and rolling-risk outputs.
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

from app.audio.preprocessor import chunk_audio, preprocess_audio
from app.features.extractor import AudioFeatureExtractor
from app.models.demo_detector import DemoVoiceDetector
from app.models.ml_detector import MLVoiceDetector, ModelNotAvailableError
from app.risk.alerts import AlertEngine
from app.risk.context import ContextRiskEngine
from app.risk.rolling import RollingRiskEngine

SR = 16000
CTX = {"caller_known": False, "pending_transaction": True,
       "sensitive_action": True, "call_type": "upload"}


def analyse(path: str, ml: MLVoiceDetector | None) -> dict:
    audio, sr = sf.read(path, dtype='float32', always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    pre = preprocess_audio(audio, int(sr), SR)
    clean = pre['audio']
    wins = chunk_audio(clean, SR, 2.5)
    ext = AudioFeatureExtractor()
    demo = DemoVoiceDetector()
    rolling = RollingRiskEngine()
    alerts = AlertEngine()
    ctxeng = ContextRiskEngine()
    windows = []
    for w in wins:
        feats = ext.extract(w, SR)
        d = demo.predict(feats)
        entry: dict = {'demo_prob': round(float(d['synthetic_probability']), 4)}
        if ml is not None:
            try:
                m = ml.score_waveform(w, SR)
                entry.update({'aasist_spoof_logit': round(m['spoof_logit'], 3),
                              'aasist_bonafide_logit': round(m['bonafide_logit'], 3),
                              'aasist_prob': round(m['synthetic_probability'], 4)})
                prob = m['synthetic_probability']
            except ValueError:
                prob = None
        else:
            prob = None
        base = d['synthetic_probability'] if prob is None else prob
        roll = rolling.update(base)
        fin = ctxeng.score(roll['risk_score'], CTX)['final_risk']
        level = rolling.level_for(fin)
        entry.update({'rolling': round(roll['risk_score'], 4),
                      'final_risk': round(fin, 4), 'alert_level': level,
                      'recommendation': alerts.decide(level, True)['recommendation']})
        windows.append(entry)
    return {'file': path, 'duration_sec': round(pre['duration_sec'], 2),
            'vad_active_ratio': round(float(pre['vad']['active_ratio']), 3),
            'windows': windows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--real', required=True)
    ap.add_argument('--synthetic', required=True)
    ap.add_argument('--statement', default='')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    try:
        ml = MLVoiceDetector()
        ml_info = {'available': True, 'model': ml.model_name,
                   'device': str(ml.device)}
    except ModelNotAvailableError as exc:
        ml = None
        ml_info = {'available': False, 'error': str(exc)}

    report = {'statement': args.statement, 'context': CTX,
              'ml': ml_info,
              'genuine': analyse(args.real, ml),
              'cloned': analyse(args.synthetic, ml),
              'note': ('Same pipeline, same preprocessing, no score manipulation. '
                       'Raw AASIST outputs reported per window.')}

    def avg(side, key):
        vals = [w[key] for w in report[side]['windows'] if key in w]
        return round(float(sum(vals) / len(vals)), 4) if vals else None

    report['verdict'] = {
        'genuine_mean_aasist': avg('genuine', 'aasist_prob'),
        'cloned_mean_aasist': avg('cloned', 'aasist_prob'),
        'genuine_mean_demo': avg('genuine', 'demo_prob'),
        'cloned_mean_demo': avg('cloned', 'demo_prob'),
        'genuine_final_alert': report['genuine']['windows'][-1]['alert_level'] if report['genuine']['windows'] else None,
        'cloned_final_alert': report['cloned']['windows'][-1]['alert_level'] if report['cloned']['windows'] else None,
    }
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)
    print('wrote', args.output)
    print(json.dumps(report['verdict'], indent=2))


if __name__ == '__main__':
    main()
