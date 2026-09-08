"""MLVoiceDetector: official AASIST pretrained anti-spoof model (REAL ML mode).

Source (MIT licence, Copyright NAVER Corp.):
  checkpoint : https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
               file AASIST.pth, pinned commit e842653505c2832ac9f46bbf56173b0f54ef82a7
  network    : https://github.com/clovaai/aasist (models/AASIST.py),
               vendored unchanged as app/models/aasist_net.py
  config     : upstream config/AASIST.conf model_config
  paper      : Jung et al., ICASSP 2022, arXiv:2110.01200

Input contract (matches upstream eval exactly):
  float32 mono waveform at 16 kHz -> first 64600 samples; shorter inputs are
  tile-repeat padded (upstream data_utils.pad). VAuth 2.5 s windows (40000
  samples) are therefore valid model inputs after this deterministic padding.

Output semantics (verified against upstream main.py + evaluation.py):
  forward returns (last_hidden, logits[B, 2]) with CrossEntropy labels
  bonafide=1 / spoof=0, and the published score is ``logits[:, 1]`` where
  HIGHER means MORE BONA FIDE. The logits are NOT probabilities, so
  ``synthetic_probability = 1 - bonafide_logit`` would be wrong.
  Correct conversion: softmax over [spoof, bonafide], then
  synthetic_probability = P(spoof) = softmax(logits)[0].

MFCC/spectral/prosody extraction is NOT used by this detector; it keeps
running in AnalysisPipeline as VAuth's separate signal-analysis layer.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from app.models.base import BaseVoiceDetector

MODEL_NAME = "AASIST"
AASIST_SAMPLE_RATE = 16000
AASIST_SAMPLES = 64600
# Exact upstream config/AASIST.conf model_config (AASIST variant, not AASIST-L).
AASIST_D_ARGS = {
    "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
    "gat_dims": [64, 32],
    "pool_ratios": [0.5, 0.7, 0.5, 0.5],
    "temperatures": [2.0, 2.0, 100.0, 100.0],
    "first_conv": 128,
}
DEFAULT_MODEL_PATH = "models/AASIST.pth"


class ModelNotAvailableError(RuntimeError):
    pass


try:
    import torch

    _TORCH = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore
    _TORCH = False


def resolve_model_path(given: str | None) -> Path:
    """Resolve VAUTH_MODEL_PATH against cwd and the repo root (models/ lives there)."""
    candidates: list[Path] = []
    if given:
        candidates.append(Path(given))
    repo_root = Path(__file__).resolve().parents[3]  # backend/app/models -> repo root
    if given and not Path(given).is_absolute():
        candidates.append(repo_root / given)
    for cand in candidates:
        if cand.is_file():
            return cand
    return Path(given or DEFAULT_MODEL_PATH)


def pad_upstream(x: np.ndarray, max_len: int = AASIST_SAMPLES) -> np.ndarray:
    """Mirror upstream data_utils.pad: first max_len samples, tile-repeat if short."""
    x = np.asarray(x, dtype=np.float32).ravel()
    if x.shape[0] >= max_len:
        return x[:max_len]
    num_repeats = int(max_len / max(1, x.shape[0])) + 1
    return np.tile(x, (num_repeats,))[:max_len]


class MLVoiceDetector(BaseVoiceDetector):
    name = "ml"
    model_name = MODEL_NAME
    uses_waveform = True
    is_demo = False

    def __init__(self, model_path: str | None = None, device: str | None = None):
        if not _TORCH:
            raise ModelNotAvailableError("PyTorch is not installed; cannot use MLVoiceDetector")
        from app.models.aasist_net import Model as AASISTNet

        self.requested_path = model_path or os.environ.get("VAUTH_MODEL_PATH", DEFAULT_MODEL_PATH)
        self.model_path = resolve_model_path(self.requested_path)
        if not self.model_path.is_file():
            raise ModelNotAvailableError(
                f"AASIST checkpoint not found at '{self.requested_path}' "
                f"(resolved: '{self.model_path}'). Run `py scripts/download_aasist.py` "
                "or set VAUTH_MODEL_PATH to a valid checkpoint."
            )
        want = (device or os.environ.get("VAUTH_DEVICE", "cpu")).lower()
        if want == "cuda" and torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            if want == "cuda":
                raise ModelNotAvailableError("VAUTH_DEVICE=cuda requested but CUDA is not available")
            self.device = torch.device("cpu")
        try:
            self.model = AASISTNet(AASIST_D_ARGS)
            state = torch.load(str(self.model_path), map_location="cpu")
            if isinstance(state, dict) and "state_dict" in state:
                state = state["state_dict"]
            if isinstance(state, dict) and "model" in state and isinstance(state["model"], dict):
                state = state["model"]
            # Strict: any architecture mismatch must fail loudly, never silently.
            self.model.load_state_dict(state, strict=True)
        except ModelNotAvailableError:
            raise
        except Exception as exc:
            raise ModelNotAvailableError(
                f"Could not load AASIST checkpoint '{self.model_path}': {exc}"
            ) from exc
        self.model.to(self.device).eval()
        self.num_params = int(sum(p.numel() for p in self.model.parameters()))
        self.loaded = True

    @staticmethod
    def prepare_waveform(audio: np.ndarray, sample_rate: int = AASIST_SAMPLE_RATE) -> np.ndarray:
        arr = np.asarray(audio, dtype=np.float32).ravel()
        if arr.size == 0:
            raise ValueError("Empty waveform: AASIST needs audio samples")
        if not bool(np.all(np.isfinite(arr))):
            raise ValueError("Non-finite samples in waveform")
        if int(sample_rate) != AASIST_SAMPLE_RATE:
            from app.audio.preprocessor import resample as _rs

            arr = _rs(arr, int(sample_rate), AASIST_SAMPLE_RATE)
        if float(np.max(np.abs(arr))) < 1e-6:
            raise ValueError("Silent waveform carries no spoof evidence")
        return pad_upstream(arr)

    def score_waveform(self, audio: np.ndarray, sample_rate: int = AASIST_SAMPLE_RATE) -> dict:
        x = self.prepare_waveform(audio, sample_rate)
        with torch.no_grad():
            tensor = torch.from_numpy(x).float().unsqueeze(0).to(self.device)
            _, out = self.model(tensor)
            logits = out.float().cpu().numpy().ravel()
        if logits.shape != (2,):
            raise ModelNotAvailableError(f"Unexpected AASIST output shape {logits.shape}")
        shifted = logits - float(logits.max())
        exp = np.exp(shifted)
        probs = exp / float(exp.sum())
        p_spoof, p_bonafide = float(probs[0]), float(probs[1])
        result = self._format(p_spoof)
        result.update(
            {
                "model": MODEL_NAME,
                "spoof_logit": float(logits[0]),
                "bonafide_logit": float(logits[1]),
                "bonafide_probability": p_bonafide,
            }
        )
        return result

    def predict_waveform(self, audio: np.ndarray, sample_rate: int = AASIST_SAMPLE_RATE) -> dict:
        return self.score_waveform(audio, sample_rate)

    def predict_audio(self, audio: np.ndarray, sample_rate: int) -> dict:
        return self.score_waveform(np.asarray(audio, dtype=np.float32), int(sample_rate))

    def predict(self, features: dict) -> dict:  # noqa: ARG002
        raise ModelNotAvailableError(
            "MLVoiceDetector (AASIST) consumes raw waveforms, not feature vectors. "
            "Use predict_waveform(audio, sample_rate) or predict_audio(audio, sample_rate)."
        )
