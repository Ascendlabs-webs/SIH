# VAuth — AI-Powered Real-Time Detection of Voice-Cloning Impersonation

Defensive voice-forensics MVP: audio stream → preprocessing → features → anti-spoof
detection → rolling risk → alerts → SOC dashboard. Ships with a clearly labelled
**DEMO detector**; a real ASVspoof/WaveFake-trained model plugs into the same
interface (see `models/README.md`).

> **Scope (read first).** VAuth **cannot** intercept ordinary Jio/Airtel/BSNL
> cellular calls. It only processes **authorized** audio: file uploads, browser
> microphone, WebRTC streams, Twilio Media Streams, or authorized VoIP/recordings.

## Architecture

```
upload / mic / WebRTC / Twilio (8 kHz μ-law)
  → decode → mono → resample 16 kHz → normalize → noise gate → VAD
  → 2.5 s windows → MFCC/spectral/prosody features → detector (demo|ml)
  → rolling risk → context adjustment → alert engine
  → REST + WebSocket → React SOC dashboard
```

| Path | Description |
|---|---|
| `backend/app/audio/` | Codecs (WAV/PCM16/μ-law 8 kHz), preprocessing, VAD, chunking |
| `backend/app/features/` | librosa features: MFCC, centroid, bandwidth, rolloff, flux, ZCR, RMS, mel stats, F0, pauses, jitter/shimmer (optional parselmouth/pyworld, heuristic fallback) |
| `backend/app/models/` | `BaseVoiceDetector` + `DemoVoiceDetector` (labelled) + `MLVoiceDetector` (PyTorch, checkpoint-gated) |
| `backend/app/speaker/` | `SpeakerVerifier` enroll/verify/similarity (dev embedding, ECAPA-ready) |
| `backend/app/risk/` | Rolling weighted risk, bounded context engine, alert engine |
| `backend/app/services/` | `AnalysisPipeline` (per-session), demo runner, history store (scores only) |
| `backend/app/api/` | REST routes; `backend/app/websocket/` WS routes |
| `frontend/src/` | SOC dashboard (React+TS+Vite+Recharts) |

## Features

- 2–3 s chunked analysis (default 2.5 s), 8 kHz μ-law → 16 kHz pipeline
- 0–1 synthetic-voice risk + GREEN/YELLOW/ORANGE/RED alerts + recommendations
- Rolling weighted risk, contextual adjustment (bounded), sensitive-action protection panel
- Real-time dashboard: gauge, risk timeline, signal analysis, event log, latency/VAD metrics
- REST API + WebSocket streaming + mic capture + file upload + one-click demos
- Privacy: raw audio discarded by default (`STORE_RAW_AUDIO=false`)

## Installation

Prereqs: Python 3.10+ (3.11 recommended), Node 18+, ffmpeg **not** required.

```powershell
# backend
cd backend
py -m pip install -r requirements.txt

# demo audio (required once)
py ..\scripts\generate_demo_audio.py

# frontend
cd ..\frontend
npm install
```

## Running locally

```powershell
# terminal 1 — backend (from backend/)
cd backend
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend (from frontend/)
cd frontend
npm run dev
```

Open http://localhost:5173 · API docs http://127.0.0.1:8000/docs

## Demo instructions

1. `py scripts/generate_demo_audio.py` (creates `data/demo/demo_real.wav`, `demo_synthetic.wav`)
2. Start backend + frontend.
3. Click **Start Genuine Voice Demo** → risk stays low/GREEN.
4. Click **Start Synthetic Voice Demo** → risk climbs to ORANGE/RED.
5. Optional: **Use Microphone** (browser permission) or **Upload WAV**.

All demo screens carry: *DEMO MODEL — Replace with trained anti-spoof model for production evaluation*.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/`, `/health`, `/api/status` | Root, liveness, config/detector/history count |
| POST | `/api/analyze` | JSON `{samples[] \| audio_base64, sample_rate, encoding, context}` → `AnalysisResult` |
| POST | `/api/analyze-file` | Multipart WAV/PCM16 upload → `AnalysisResult` |
| POST | `/api/demo/start` | `{scenario: real\|synthetic}` → full window timeline |
| POST | `/api/demo/stop` | Reset pipeline + history |
| POST | `/api/demo/reset` | Alias for `/demo/stop` (session reset) |
| GET | `/api/protection/state` | Prevention state machine snapshot (NORMAL/WARNING/SECONDARY_VERIFICATION_REQUIRED/VERIFIED/ESCALATED/BLOCKED) |
| POST | `/api/protection/action` | `{action: request_otp\|request_callback\|mark_verified\|escalate\|reset}` → new state (simulated, no real banking) |
| GET | `/api/webrtc/config` | Browser-capture contract (encodings `pcm16`/`f32` @ 16 kHz → `/ws/audio`) |
| GET | `/api/history?limit=` | Recent results (no raw audio) |
| GET | `/api/demo/audio?scenario=` | Download demo WAV |
| POST | `/api/twilio/voice` | TwiML `<Stream>` webhook |
| GET | `/api/twilio/config` | Twilio setup state |

Example result:
```json
{"risk_score": 0.87, "alert_level": "ORANGE", "classification": "SYNTHETIC",
 "confidence": 0.87, "recommendation": "Perform secondary verification",
 "timestamp": "...", "window_duration": 2.5, "latency_ms": 47.9,
 "latency_breakdown": {"preprocess_ms": 2.1, "features_ms": 45.6, "inference_ms": 0.0, "risk_ms": 0.1},
 "audio_risk": 0.81, "context_risk": 0.06,
 "protection_state": "SECONDARY_VERIFICATION_REQUIRED",
 "protection_actions": ["otp", "callback", "additional_identity_verification"]}
```

## WebSocket protocol

- `ws:///ws/audio` — dashboard/mic/WebRTC path. Send `{"type":"config",...}`, then binary PCM frames (`pcm16` int16 or `f32` float32) or `{"type":"audio","audio_base64":...}`; receive `{"type":"analysis_result", ...}` per 2.5 s window. `{"type":"reset"}` clears session state.
- `ws:///ws/twilio` — Twilio Media Streams receiver (8 kHz μ-law JSON frames → same pipeline).

## Model integration (REAL ML modes, opt-in)

VAuth ships explicit modes; `/api/model/status` and the dashboard header
always show which one is REALLY running (`MODEL:` / `MODE: DEMO|REAL ML`).

| `VAUTH_DETECTOR` | model | backend |
|---|---|---|
| `demo` (default) | DemoVoiceDetector (labelled heuristic) | — |
| `ml` | AASIST, official ASVspoof2019-LA checkpoint (back-compat alias) | torch |
| `aasist` | AASIST, same weights/code as `ml` | torch |
| `spectra` | Spectra-AASIST (lab260) | ONNX CPU |
| `spectra3` | Spectra-AASIST3 (lab260, **recommended for local eval**) | ONNX CPU |
| `w2v2_aasist` | W2V2-AASIST, SSL_Anti-spoofing LA (Tak et al. Odyssey 2022) | ONNX CPU |

- Source: official AASIST (Jung et al., ICASSP 2022, arXiv:2110.01200),
  checkpoint `AASIST.pth` from https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
  (pinned commit, MIT licence, byte-identical to clovaai/aasist release weights).
- Input: preprocessed 16 kHz mono waveform window (2.5 s → deterministically
  padded to the model's 64600-sample frame, exactly like upstream eval).
- Output: 2 logits `[spoof, bonafide]`, HIGHER bona fide logit = more genuine
  (verified in upstream code); VAuth converts via softmax to
  `synthetic_probability = P(spoof)`. MFCC/spectral/prosody extraction keeps
  running as the separate signal-analysis layer.
- Enable: `py scripts/download_aasist.py`, then `VAUTH_DETECTOR=ml`
  (with `VAUTH_MODEL_PATH=models/AASIST.pth`, `VAUTH_DEVICE=cpu`).
  Missing checkpoint in ML mode → explicit DEMO fallback with a visible
  warning (logs + API + dashboard), never silent.
- Measured here: ~0.1 s load, ~290–360 ms/window CPU inference; torch
  pipeline bit-matches the official `aasist.onnx` export.
- Honest limitation: the generic AASIST checkpoint does NOT separate our
  local audio (AUC 0.070, inverted). A 4-model benchmark on our own eval set
  (`py scripts/benchmark_models.py`, evidence in
  `data/eval/benchmark_models.json`, write-up in `models/BENCHMARKS.md`)
  found **Spectra-AASIST3** substantially strongest (AUC 1.000, EER 0.000,
  telephony-stable; ~1.5 s CPU inference, ~1.3 GB RAM) — use
  `VAUTH_DETECTOR=spectra3` for local REAL ML evaluation. Small-set results
  are encouraging, not production validation; production needs domain
  fine-tuning with reported EER/min-tDCF. Do NOT present local separation
  as scientific validation.

## Twilio setup

1. Expose backend publicly (ngrok), set `TWILIO_*` env vars.
2. Point the number's voice webhook at `POST /api/twilio/voice`.
3. Calls stream μ-law to `/ws/twilio` → same pipeline → dashboard.
4. Local demo needs **no** Twilio credentials. Never routes ordinary cellular audio.

## WebRTC / microphone setup

Dashboard mic button captures 16 kHz PCM via `AudioContext` → binary WS frames.
For custom WebRTC apps, forward the remote track's PCM to `/ws/audio` with a
`config` frame first (see `frontend/src/hooks/useMic.ts`).

## Privacy architecture

`raw audio → features → inference → discarded`. Stored: timestamps, scores,
levels, metadata, feature summaries. `STORE_RAW_AUDIO` defaults to `false`;
uploads are held in memory only. Authorized sources only.

## Limitations

- Demo detector is a **heuristic**, not a validated anti-spoof model — expect
  false positives/negatives; do not use for real security decisions.
- No pretrained weights ship with the repo (supply-chain safety).
- Energy VAD + heuristic jitter/shimmer degrade in heavy noise.
- Speaker verification is a stub interface (mean-MFCC embedding).

## Production roadmap

MVP (exists now — all verified by `pytest` + live endpoint tests):
- preprocessing (WAV/PCM16/8 kHz μ-law → 16 kHz mono, normalize, noise gate, VAD)
- features (MFCC, spectral, mel, F0, pauses, jitter/shimmer heuristic)
- demo detector (deterministic, DEMO-labelled) + replaceable ML interface
- rolling/contextual risk, alert engine, backend prevention state machine
- real-time SOC dashboard, REST, WebSocket, mic capture, file upload
- genuine/synthetic demos, Twilio Media Streams receiver, WebRTC frame adapter

Future (NOT built — roadmap only):
1. Train/evaluate AASIST/wav2vec2-based detector on ASVspoof 2021 + WaveFake (report EER/min-tDCF).
2. Replace dev speaker embedding with ECAPA-TDNN; add score fusion + calibration.
3. Add auth/rate-limiting, persistent audit log, PROM metrics, CI, signed model artifacts.
4. Harden Twilio signature validation, TLS termination, PII redaction.

## Tests

```powershell
cd backend
py -m pytest -q
```
