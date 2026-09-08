"""Benchmark detector registry tests (heavy ONNX loads kept to a minimum)."""
from __future__ import annotations

import numpy as np
import pytest


def _onnx_present(name: str) -> bool:
    from pathlib import Path

    return Path(f"models/{name}.onnx").is_file()


requires_model = pytest.mark.requires_model


def test_detector_names_registered():
    """Detector names are registered (metadata only — no weights loaded)."""
    import app.models.factory as factory

    registry = factory._registry()
    assert set(registry) == {"demo", "ml", "aasist", "spectra", "spectra3", "w2v2_aasist"}
    assert registry["demo"].__name__ == "DemoVoiceDetector"
    assert registry["ml"].__name__ == "MLVoiceDetector"
    assert registry["aasist"].__name__ == "AASISTDetector"
    assert registry["spectra"].__name__ == "SpectraAASISTDetector"
    assert registry["spectra3"].__name__ == "SpectraAASIST3Detector"
    assert registry["w2v2_aasist"].__name__ == "W2V2AASISTDetector"
    # plain demo selection still works with zero weights involved
    assert factory.build_detector("demo").name == "demo"


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


@requires_model
def test_aasist_detector_matches_ml():
    from pathlib import Path

    from app.models.ml_detector import MLVoiceDetector
    from app.models.onnx_detector import AASISTDetector
    from tests.conftest import make_tone

    if not Path("models/AASIST.pth").is_file():
        pytest.skip("AASIST checkpoint unavailable; run scripts/download_aasist.py")

    audio = make_tone(flat=False, seconds=2.5)
    a = MLVoiceDetector().score_waveform(audio, 16000)
    b = AASISTDetector().score_waveform(audio, 16000)
    assert a["synthetic_probability"] == b["synthetic_probability"]
    assert b["model"] == "AASIST"


@requires_model
def test_spectra_smoke_inference():
    from pathlib import Path

    from app.models.onnx_detector import SpectraAASISTDetector
    from tests.conftest import make_tone

    if not _onnx_present("spectra-aasist"):
        pytest.skip("spectra-aasist.onnx unavailable")
    det = SpectraAASISTDetector()
    out = det.score_waveform(make_tone(flat=False, seconds=2.5), 16000)
    assert 0.0 <= out["synthetic_probability"] <= 1.0
    assert out["model"] == "Spectra-AASIST"


@requires_model
def test_pipeline_selects_spectra3():
    from pathlib import Path

    from app.services.pipeline import AnalysisPipeline
    from tests.conftest import make_tone

    if not Path("models/spectra-aasist3.onnx").is_file():
        pytest.skip("spectra-aasist3.onnx unavailable")
    pipe = AnalysisPipeline(detector_name="spectra3")
    assert pipe.detector.name == "spectra3"
    r = pipe.process_window(make_tone(flat=False, seconds=3.0), 16000,
                            {"call_type": "demo"}, store=False)
    assert r.detector == "spectra3"
    assert r.features is not None
