# VAuth model benchmark — same data, same windows, same metrics

Date: 2026-09-08. Machine: Windows, CPU inference, RTX 3050 6GB present but
unused (onnxruntime build has CPU provider only). No thresholds tuned, no
calibration — ranking metrics only. Full machine-readable evidence:
`data/eval/benchmark_models.json` (per-file scores, ROC points, latencies).

## Dataset (ours, not published numbers)

`data/eval/`: 8 genuine CMU Arctic recordings + 16 edge-TTS readings of the
SAME 8 transcripts (2 voices). File score = mean of 2.5 s window
P(spoof). Telephony variant = 8 kHz μ-law round-trip, identical scoring.

## Models (all official, waveform-in, class-1 = bona fide, verified per repo)

| key | model | source | params | input |
|---|---|---|---|---|
| aasist | AASIST | SpeechAntiSpoofingBenchmarks/AASIST (`AASIST.pth`, torch) | 297,866 | 64600 @16k |
| spectra | Spectra-AASIST | lab260/Spectra-AASIST (`spectra-aasist.onnx`) | 316.0M | 64600 @16k |
| spectra3 | Spectra-AASIST3 | lab260/Spectra-AASIST3 (`spectra-aasist3.onnx`) | 319.1M | 64600 @16k |
| w2v2_aasist | W2V2-AASIST | SpeechAntiSpoofingBenchmarks/W2V2-AASIST (`w2v2-aasist.onnx`) | 317.8M | 64600 @16k |

Licences: AASIST MIT; Spectra/W2V2 repos carry their own files — check each
repo before redistributing weights (weights are git-ignored, never committed).

## Results on OUR data (clean)

| model | AUC | EER | F1 | prec | rec | infer mean | load | RAM Δ |
|---|---|---|---|---|---|---|---|---|
| spectra3 | 1.000 | 0.000 | 1.000 | 1557 ms | 11.7 s | +1338 MB |
| spectra | 0.953 | 0.125 | 0.865 | 678 ms | 4.7 s | +1305 MB |
| w2v2_aasist | 0.117 | 0.875 | 0.588 | 780 ms | 4.3 s | +1286 MB |
| aasist | 0.070 | 0.875 | 0.452 | 416 ms | 0.4 s | +21 MB |

Telephony: spectra3 acc 0.958 / AUC 1.000 / EER 0.000; spectra acc 0.750 /
AUC 0.969 / EER 0.125; w2v2 acc 0.583 / AUC 0.164; aasist acc 0.500 /
AUC 0.156.

## Recommendation

**Spectra-AASIST3** is substantially the strongest classifier on our data
(perfect file-level separation, telephony-stable) — recommend it as the REAL
ML default for local evaluation: `VAUTH_DETECTOR=spectra3`. Cost: ~1.5 s CPU
inference per window and ~1.3 GB RAM. The generic AASIST checkpoint is
unusable on this data (AUC 0.070, inverted ranking) and should no longer be
presented as the ML path beyond back-compat (`ml` alias retained).

Caveats (do not overclaim): 24 files, 1 genuine speaker, 1 TTS engine,
English only. Perfect scores on a tiny set are encouraging, not validation.

## 2.5 s streaming compatibility (winner)

Tested `AnalysisPipeline(detector_name="spectra3")` on 2.5 s windows:
works end-to-end (det=spectra3, risk → alerts → protection). Internal window
is fixed 64600; VAuth tile-pads 40000→64600. Padding sensitivity probe
(arctic_a0001 genuine 0.0000 continuous vs 0.1651 padded; TTS clone 0.9837 vs
0.9876): same verdicts, shifted scores. Verdict: **YES, streaming-compatible**,
with one operational note — steady-state latency is ~1.2–1.6 s per window on
CPU (plus ~2.4 s one-off feature cold start), so the dashboard lags ~1 window
behind real time; acceptable for demo, needs GPU/quantisation for live use.

## Reproduce

```powershell
py scripts/benchmark_models.py                                   # all four, clean+telephony
py scripts/benchmark_models.py --models spectra3                # winner only
py scripts/evaluate_model.py --detector spectra3 --real data/eval/real --synthetic data/eval/synthetic --output r.json
$env:VAUTH_DETECTOR="spectra3"; cd backend; py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
