# VAuth real anti-spoof models (REAL ML modes, opt-in)

`VAUTH_DETECTOR`: `demo` (default heuristic) | `ml`/`aasist` (AASIST, torch)
| `spectra` | `spectra3` (**recommended for local eval**) | `w2v2_aasist`.
See BENCHMARKS.md for the head-to-head on our data (Spectra-AASIST3:
AUC 1.000, EER 0.000) and EVALUATION.md for the AASIST validation log.

## AASIST (original torch path)

Status: integrated, runs locally, NOT production-validated on our data
(AUC 0.070 — do not use for local demos beyond back-compat).

`VAUTH_DETECTOR=ml` loads the official AASIST checkpoint into
`MLVoiceDetector` (waveform-in). `VAUTH_DETECTOR=demo` (default) keeps the
labelled heuristic. `/api/model/status` always reports which one is REALLY
running — DEMO is never presented as ML.

## Model source (official/public only, nothing retrained)

- Weights: https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
  file `AASIST.pth`, pinned commit `e842653505c2832ac9f46bbf56173b0f54ef82a7`
  (SHA256 `51d2d9cf…1a1c0`, byte-identical to the upstream release at
  https://github.com/clovaai/aasist `models/weights/AASIST.pth`).
- Network: upstream `models/AASIST.py`, vendored unchanged as
  `backend/app/models/aasist_net.py`. Config: upstream `config/AASIST.conf`
  (`nb_samp=64600`, AASIST variant — not AASIST-L).
- Paper: Jung et al., *AASIST: Audio Anti-Spoofing using Integrated
  Spectro-Temporal Graph Attention Networks*, ICASSP 2022, arXiv:2110.01200.
- Licence: MIT (NAVER Corp.), mirrored at `models/AASIST.LICENSE`.
- Published accuracy: 0.83% EER on ASVspoof2019 LA (in-domain). Cross-dataset
  is far weaker (e.g. InTheWild 43%, ASVspoof5 35% per the model card).

## Architecture

Raw waveform → sinc-conv front-end → RawNet2-style residual encoder →
heterogeneous spectro-temporal graph attention (GAT-S/GAT-T + master nodes) →
2-class output (spoof vs bona fide). 297,866 parameters.

## Input format

Float32 mono waveform at 16 kHz. Deterministic first-64600-sample window
(~4.04 s); shorter inputs are tile-repeat padded — exactly upstream
`data_utils.pad()` eval behaviour. VAuth 2.5 s windows (40 000 samples) are
padded to 64600 the same way.

## Output semantics (verified in upstream `main.py` + `evaluation.py`)

- Forward returns `(last_hidden, logits[B, 2])`, trained with CrossEntropy
  labels bonafide=1 / spoof=0; the published score is `logits[:, 1]`,
  HIGHER = MORE BONA FIDE. Logits are unbounded, so `1 - logit` is invalid.
- VAuth converts via softmax: `P(spoof) = softmax(logits)[0]`, and
  `synthetic_probability = P(spoof)`, `bonafide_probability = P(bonafide)`.
- VAuth `/ws` + REST also expose the raw `spoof_logit`/`bonafide_logit`
  inside the detector result for audit (see benchmark below).

## Installation

```powershell
py scripts/download_aasist.py   # official checkpoint -> models/AASIST.pth (git-ignored)
$env:VAUTH_DETECTOR = "ml"      # PowerShell; or export VAUTH_DETECTOR=ml
cd backend; py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Weights stay outside git (`models/*.pt` is git-ignored). If ML mode is set
but the checkpoint is missing/corrupt, the server falls back to DEMO with an
explicit warning surfaced in logs, `/api/model/status`, and the dashboard
banner — never silently.

## Measured local behaviour (this machine, CPU; `py scripts/benchmark_aasist.py`)

- Load: ~0.1 s. Inference: ~290–360 ms per 2.5 s window (torch 2.11, CPU).
- Torch pipeline is bit-identical to the repo's official `aasist.onnx`
  export (logits match to 1e-6 on the same input).
- Raw scores on local audio (honest, un cherry-picked):
  - `demo_real.wav` / `demo_synthetic.wav` (placeholder beeps): both ≈0.97–1.00
    spoof — these tones are out-of-distribution for the model; the beeps do
    NOT separate under AASIST.
  - mp3 news speech (real human): mixed 0.03–1.00 across windows.
  - edge-tts synthesis: mixed 0.03–1.00 across windows.
  - CMU Arctic studio speech (lossless bona fide): ≈0.93–0.97 spoof.

## Limitations (read before demoing with `ml`)

1. Good in-domain benchmark ≠ good local discriminator: on non-ASVspoof2019
   audio this checkpoint is unreliable (consistent with its published
   cross-dataset EERs). Local demo separation is NOT achieved — the default
   hackathon demo should stay on DEMO mode.
2. VAuth windows are 2.5 s; the model expects ~4 s. Tile-padding short
   windows changes scores versus continuous 4 s inputs (measured).
3. mp3/compressed or old-channel audio further degrades it.
4. No retraining, calibration, or score normalisation has been done yet —
   that is the real next step (fine-tune/calibrate on the target domain and
   report EER/min-tDCF before any production claim).
