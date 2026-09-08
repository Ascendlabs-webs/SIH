"""AASIST integration tests: loading, waveform I/O, ranges, pipeline wiring.

Requires torch + models/AASIST.pth; skipped otherwise (CI without weights).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[2]
CKPT = ROOT / "models" / "AASIST.pth"
needs_ckpt = pytest.mark.skipif(not CKPT.is_file(), reason="models/AASIST.pth absent")


def test_checkpoint_present_and_shaped():
    from app.models.aasist_net import Model as AASISTNet
    from app.models.ml_detector import AASIST_D_ARGS

    assert CKPT.is_file(), "Run py scripts/download_aasist.py"
    state = torch.load(str(CKPT), map_location="cpu")
    assert isinstance(state, dict)
    assert state["out_layer.weight"].shape == (2, 160)
    model = AASISTNet(AASIST_D_ARGS)
    model.load_state_dict(state, strict=True)  # architecture must match exactly
    n = sum(p.numel() for p in model.parameters())
    assert n == 297866, f"param count changed: {n}"


@needs_ckpt
def test_model_loading_strict():
    from app.models.ml_detector import MLVoiceDetector

    det = MLVoiceDetector()
    assert det.loaded is True
    assert det.model_name == "AASIST"
    assert det.num_params == 297866
    assert det.is_demo is False
    assert det.uses_waveform is True


@needs_ckpt
def test_valid_waveform_inference_range():
    from app.models.ml_detector import MLVoiceDetector
    from tests.conftest import make_tone

    det = MLVoiceDetector()
    audio = make_tone(flat=False, seconds=2.5)
    out = det.score_waveform(audio, 16000)
    assert out["model"] == "AASIST"
    assert 0.0 <= out["synthetic_probability"] <= 1.0
    assert 0.0 <= out["bonafide_probability"] <= 1.0
    assert out["synthetic_probability"] + out["bonafide_probability"] == pytest.approx(1.0)
    assert out["classification"] in ("REAL", "SYNTHETIC")
    assert np.isfinite(out["spoof_logit"]) and np.isfinite(out["bonafide_logit"])


@needs_ckpt
def test_25s_window_padding_compat():
    from app.models.ml_detector import MLVoiceDetector, pad_upstream, AASIST_SAMPLES

    det = MLVoiceDetector()
    short = np.random.default_rng(0).normal(0, 0.1, size=40000).astype(np.float32)
    assert pad_upstream(short).shape == (AASIST_SAMPLES,)
    out = det.score_waveform(short, 16000)  # 2.5 s window must not crash
    assert 0.0 <= out["synthetic_probability"] <= 1.0
    # 8 kHz input is resampled, not rejected
    out8 = det.score_waveform(short[::2], 8000)
    assert 0.0 <= out8["synthetic_probability"] <= 1.0


@needs_ckpt
def test_invalid_waveforms_rejected():
    from app.models.ml_detector import MLVoiceDetector

    det = MLVoiceDetector()
    with pytest.raises(ValueError):
        det.score_waveform(np.zeros(0, dtype=np.float32), 16000)
    with pytest.raises(ValueError):
        det.score_waveform(np.zeros(40000, dtype=np.float32), 16000)  # silence
    bad = np.random.default_rng(1).normal(0, 0.1, size=40000).astype(np.float32)
    bad[0] = np.nan
    with pytest.raises(ValueError):
        det.score_waveform(bad, 16000)


@needs_ckpt
def test_predict_vector_api_refuses():
    from app.models.ml_detector import MLVoiceDetector, ModelNotAvailableError

    det = MLVoiceDetector()
    with pytest.raises(ModelNotAvailableError):
        det.predict({"mfcc": [0.0] * 13})


@needs_ckpt
def test_pipeline_ml_integration():
    from app.services.pipeline import AnalysisPipeline
    from tests.conftest import make_tone

    pipe = AnalysisPipeline(detector_name="ml")
    assert pipe.detector.name == "ml"
    assert pipe.detector_warning is None
    audio = make_tone(flat=False, seconds=3.0)
    result = pipe.process_window(audio, 16000, {"call_type": "demo"}, store=False)
    assert result.detector == "ml"
    assert 0.0 <= result.risk_score <= 1.0
    assert result.features is not None  # signal-analysis layer still runs


def test_missing_checkpoint_raises_not_silent(monkeypatch):
    from app.models.ml_detector import MLVoiceDetector, ModelNotAvailableError

    monkeypatch.setenv("VAUTH_MODEL_PATH", "models/does-not-exist.pt")
    with pytest.raises(ModelNotAvailableError):
        MLVoiceDetector()


def test_ml_fallback_is_explicit(monkeypatch):
    """ml requested + no weights -> DEMO with a visible warning, never silent."""
    import app.models.factory as factory

    monkeypatch.setenv("VAUTH_MODEL_PATH", "models/does-not-exist.pt")
    det = factory.get_detector("ml")
    assert det.name == "demo"
    assert getattr(det, "_fallback_warning", None)


def test_model_status_endpoint(client):
    r = client.get("/api/model/status")
    assert r.status_code == 200
    body = r.json()
    for key in ("detector_mode", "active_detector", "is_demo", "mode_label",
                "model_loaded", "model_name", "model_path", "device"):
        assert key in body, key
