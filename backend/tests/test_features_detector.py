"""Feature extraction + demo detector tests."""
from __future__ import annotations

import numpy as np

from app.features.extractor import AudioFeatureExtractor
from app.models.demo_detector import DemoVoiceDetector


def test_feature_extraction(genuine_audio):
    audio, sr = genuine_audio
    ext = AudioFeatureExtractor()
    feats = ext.extract(audio, sr)
    for key in ("mfcc", "spectral_centroid", "spectral_flux", "f0_mean", "f0_std", "jitter", "shimmer"):
        assert key in feats, key
    assert len(feats["mfcc"]) == 13
    assert feats["duration_sec"] > 2.0
    vec = ext.to_vector(feats)
    assert vec.shape[0] == ext.vector_dim
    assert np.all(np.isfinite(vec))


def test_demo_detector_separates():
    ext = AudioFeatureExtractor()
    det = DemoVoiceDetector()
    from tests.conftest import make_tone

    genuine = make_tone(flat=False)
    synth = make_tone(flat=True)
    g = det.predict(ext.extract(genuine, 16000))
    s = det.predict(ext.extract(synth, 16000))
    assert 0.0 <= g["synthetic_probability"] <= 1.0
    assert 0.0 <= s["synthetic_probability"] <= 1.0
    assert g["synthetic_probability"] < 0.5, g
    assert s["synthetic_probability"] > 0.6, s
    # determinism
    g2 = det.predict(ext.extract(genuine, 16000))
    assert g2["synthetic_probability"] == g["synthetic_probability"]


def test_detector_audio_shortcut(synthetic_audio):
    audio, sr = synthetic_audio
    det = DemoVoiceDetector()
    out = det.predict_audio(audio, sr)
    assert out["classification"] in ("REAL", "SYNTHETIC")
