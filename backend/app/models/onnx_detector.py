"""ONNX-backed REAL ML detectors: Spectra-AASIST, Spectra-AASIST3, W2V2-AASIST.

Official sources (all: waveform in, 2 logits out, class-1 = bona fide,
higher = more bona fide — verified per model below):
  spectra      lab260/Spectra-AASIST, spectra-aasist.onnx (~316.0M params).
               SSL (xls-r-300m) + bridge + KAN-AASIST; forward(x)[:, 1] with
               bona fide threshold (see upstream model.py classify()).
  spectra3     lab260/Spectra-AASIST3, spectra-aasist3.onnx (~319.1M params).
               Same family/sc convention as Spectra-AASIST.
  w2v2_aasist  SpeechAntiSpoofingBenchmarks/W2V2-AASIST, w2v2-aasist.onnx
               (317.8M params). XLS-R 300M + AASIST back-end, Tak et al.
               Odyssey 2022; meta.yaml states score = class-1 bona fide logit.

The ONNX exports fix the time axis at 64600 samples, so VAuth windows use
the same deterministic first-64600/tile-repeat framing as the AASIST path.
Softmax conversion is identical to MLVoiceDetector: synthetic_probability =
P(spoof). onnxruntime (CPU) is already a project dependency; no transformers
or extra downloads are needed at runtime.
"""
from __future__ import annotations

import numpy as np

from app.models.base import BaseVoiceDetector
from app.models.ml_detector import (AASIST_SAMPLES, ModelNotAvailableError,
                                    pad_upstream)

try:
    import onnxruntime as ort

    _ORT = True
except Exception:  # pragma: no cover
    ort = None  # type: ignore
    _ORT = False

MODEL_FILES = {
    "spectra": "models/spectra-aasist.onnx",
    "spectra3": "models/spectra-aasist3.onnx",
    "w2v2_aasist": "models/w2v2-aasist.onnx",
}


class OnnxLogitDetector(BaseVoiceDetector):
    name = "onnx"
    model_name = "onnx"
    uses_waveform = True
    is_demo = False
    onnx_file: str = ""
    num_params: int = 0

    def __init__(self, model_path: str | None = None):
        if not _ORT:
            raise ModelNotAvailableError("onnxruntime is not installed")
        from app.models.ml_detector import resolve_model_path

        default = MODEL_FILES.get(self.name, "")
        self.requested_path = model_path or default
        self.model_path = resolve_model_path(self.requested_path or default)
        if not self.model_path.is_file():
            raise ModelNotAvailableError(
                f"ONNX checkpoint not found at '{self.requested_path}' "
                f"(resolved: '{self.model_path}')."
            )
        try:
            from app.models import cache as _cache

            opts = ort.SessionOptions()

            def _load():
                return ort.InferenceSession(
                    str(self.model_path), sess_options=opts,
                    providers=["CPUExecutionProvider"])

            self.session = _cache.shared(f"onnx:{self.model_path}", _load)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
        except Exception as exc:
            raise ModelNotAvailableError(
                f"Could not load ONNX model '{self.model_path}': {exc}") from exc
        self.device = "cpu"
        self.loaded = True

    @staticmethod
    def prepare_waveform(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        from app.models.ml_detector import MLVoiceDetector

        return MLVoiceDetector.prepare_waveform(audio, sample_rate)

    def score_waveform(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        from app.models.ml_detector import MLVoiceDetector

        x = MLVoiceDetector.prepare_waveform(audio, sample_rate)
        try:
            out = self.session.run(
                [self.output_name],
                {self.input_name: x[np.newaxis, :].astype(np.float32)})[0]
        except Exception as exc:
            raise ModelNotAvailableError(f"ONNX inference failed: {exc}") from exc
        logits = np.asarray(out, dtype=np.float64).ravel()
        if logits.shape != (2,):
            raise ModelNotAvailableError(f"Unexpected model output shape {logits.shape}")
        shifted = logits - float(logits.max())
        exp = np.exp(shifted)
        probs = exp / float(exp.sum())
        result = self._format(float(probs[0]))
        result.update({"model": self.model_name,
                       "spoof_logit": float(logits[0]),
                       "bonafide_logit": float(logits[1]),
                       "bonafide_probability": float(probs[1])})
        return result

    def predict_waveform(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        return self.score_waveform(audio, sample_rate)

    def predict_audio(self, audio: np.ndarray, sample_rate: int) -> dict:
        return self.score_waveform(np.asarray(audio, dtype=np.float32), int(sample_rate))

    def predict(self, features: dict) -> dict:  # noqa: ARG002
        raise ModelNotAvailableError(
            f"{self.model_name} consumes raw waveforms, not feature vectors. "
            "Use predict_waveform(audio, sample_rate).")


class SpectraAASISTDetector(OnnxLogitDetector):
    name = "spectra"
    model_name = "Spectra-AASIST"
    onnx_file = "models/spectra-aasist.onnx"
    num_params = 316014504


class SpectraAASIST3Detector(OnnxLogitDetector):
    name = "spectra3"
    model_name = "Spectra-AASIST3"
    onnx_file = "models/spectra-aasist3.onnx"
    num_params = 319051213


class W2V2AASISTDetector(OnnxLogitDetector):
    name = "w2v2_aasist"
    model_name = "W2V2-AASIST"
    onnx_file = "models/w2v2-aasist.onnx"
    num_params = 317837800


class AASISTDetector(OnnxLogitDetector):
    """Torch-path AASIST under the benchmark naming scheme (same weights/code
    as MLVoiceDetector; kept separate so benchmarks address every model by
    the same class interface)."""

    name = "aasist"
    model_name = "AASIST"
    num_params = 297866

    def __init__(self, model_path: str | None = None):
        from app.models.ml_detector import MLVoiceDetector

        self._torch = MLVoiceDetector(model_path=model_path)
        self.requested_path = self._torch.requested_path
        self.model_path = self._torch.model_path
        self.device = str(self._torch.device)
        self.loaded = True

    def score_waveform(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        return self._torch.score_waveform(audio, sample_rate)


__all__ = ["OnnxLogitDetector", "SpectraAASISTDetector", "SpectraAASIST3Detector",
           "W2V2AASISTDetector", "AASISTDetector", "MODEL_FILES"]
