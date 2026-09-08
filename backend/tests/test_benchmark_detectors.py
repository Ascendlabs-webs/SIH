"""Benchmark detector registry tests (heavy ONNX loads kept to a minimum)."""
from __future__ import annotations

import numpy as np
import pytest


def test_detector_names_registered():
    import app.models.factory as factory

    assert factory.build_detector("demo").name == "demo"
    for name, cls in (("ml", "MLVoiceDetector"), ("aasist", "AASISTDetector")):
        assert type(factory.build_detector(name)).__name__ == cls


def test_onnx_class_metadata_without_loading():
    from app.models.onnx_detector import (SpectraAASIST3Detector,
                                          SpectraAASISTDetector,
                                          W2V2AASISTDetector)

    assert (SpectraAASISTDetector.model_name, SpectraAASISTDetector.num_params) == ("Spectra-AASIST", 316014504)
    assert (SpectraAASIST3Detector.model_name, SpectraAASIST3Detector.num_params) == ("Spectra-AASIST3", 319051213)
    assert (W2V2AASISTDetector.model_name, W2V2AASISTDetector.num_params) == ("W2V2-AASIST", 317837800)
    for cls in (SpectraAASISTDetector, SpectraAASIST3Detector, W2V2AASISTDetector):
        assert cls.uses_waveform is True and cls.is_demo is False


def test_onnx_missing_file_raises_loudly():
    from app.models.ml_detector import ModelNotAvailableError
    from app.models.onnx_detector import SpectraAASISTDetector

    with pytest.raises(ModelNotAvailableError):
        SpectraAASISTDetector(model_path="models/does-not-exist.onnx")


def test_unknown_detector_falls_back_with_warning():
    import app.models.factory as factory

    det = factory.get_detector("nope_not_a_model")
    assert det.name == "demo"
    assert getattr(det, "_fallback_warning", None)


def test_aasist_detector_matches_ml():
    from app.models.ml_detector import MLVoiceDetector
    from app.models.onnx_detector import AASISTDetector
    from tests.conftest import make_tone

    audio = make_tone(flat=False, seconds=2.5)
    a = MLVoiceDetector().score_waveform(audio, 16000)
    b = AASISTDetector().score_waveform(audio, 16000)
    assert a["synthetic_probability"] == b["synthetic_probability"]
    assert b["model"] == "AASIST"


def test_spectra_smoke_inference():
    from pathlib import Path

    from app.models.onnx_detector import SpectraAASISTDetector
    from tests.conftest import make_tone

    if not Path("models/spectra-aasist.onnx").is_file():
        pytest.skip("spectra weights absent")
    det = SpectraAASISTDetector()
    out = det.score_waveform(make_tone(flat=False, seconds=2.5), 16000)
    assert 0.0 <= out["synthetic_probability"] <= 1.0
    assert out["model"] == "Spectra-AASIST"


def test_pipeline_selects_spectra3():
    from pathlib import Path

    from app.services.pipeline import AnalysisPipeline
    from tests.conftest import make_tone

    if not Path("models/spectra-aasist3.onnx").is_file():
        pytest.skip("spectra3 weights absent")
    pipe = AnalysisPipeline(detector_name="spectra3")
    assert pipe.detector.name == "spectra3"
    r = pipe.process_window(make_tone(flat=False, seconds=3.0), 16000,
                            {"call_type": "demo"}, store=False)
    assert r.detector == "spectra3"
    assert r.features is not None
