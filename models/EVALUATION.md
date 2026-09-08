# VAuth model evaluation (AASIST) — honest local validation

Date: 2026-09-07. Machine: Windows, CPU, torch 2.11. No retraining performed.
Nothing here is production validation.

## 1. Dataset used (legal, reproducible)

`py scripts/build_eval_dataset.py --n 8` creates `data/eval/`:

- Genuine (8 files): CMU Arctic `cmu_us_bdl_arctic` recordings
  (Carnegie Mellon, research use; prompts are public-domain Gutenberg text).
- Synthetic (16 files): edge-TTS readings of the SAME 8 transcripts,
  2 voices (`en-US-AriaNeural`, `en-US-GuyNeural`) — our own generations.
- Same-statement genuine-vs-synthetic pairs; `data/eval/MANIFEST.json`.
- NOT used: demo beeps (not speech), random mp3s (licence/compression unknowns).

Reproduce: `py scripts/build_eval_dataset.py && py scripts/evaluate_model.py
--real data/eval/real --synthetic data/eval/synthetic --output report.json [--telephony]`.

## 2. Preprocessing & test protocol

Each file: mono → 16 kHz → VAuth 2.5 s non-overlapping windows →
`MLVoiceDetector.score_waveform` per window (first-64600/tile-repeat, exactly
upstream eval framing) → file score = mean of window P(spoof). Silent windows
rejected explicitly. Telephony variant: 16 kHz → 8 kHz → μ-law → decode →
16 kHz (`app.audio.preprocessor.telephony_degrade`), then identical scoring.

## 3. Model

Official AASIST, ASVspoof2019-LA checkpoint (MIT), 297,866 params, CPU.
VAuth converts logits via softmax: `synthetic_probability = P(spoof)`.
Torch path is bit-identical to the repo's official `aasist.onnx` export.

## 4. Metrics (8 genuine / 16 synthetic, threshold 0.5)

| condition | acc | F1 | ROC-AUC | EER | EER thr | Youden thr | CM (tn fp fn tp) |
|---|---|---|---|---|---|---|---|
| clean | 0.292 | 0.452 | 0.070 | 0.875 @ 0.878 | 0.878 | 1.000 (degenerate) | 0 8 9 7 |
| telephony | 0.500 | 0.667 | 0.156 | 0.750 @ 0.989 | 0.989 | 1.000 (degenerate) | 0 8 4 12 |

Score distributions (clean): genuine mean 0.958 (min 0.823, max 1.000);
synthetic mean 0.410 (min 0.031, max 1.000). AUC 0.070 means the ranking is
essentially inverted on this set: 2003 studio recordings score MORE
spoof-like than modern edge-TTS, which lacks the 2019-era vocoder artefacts
the model learned. This matches the checkpoint's published cross-dataset
weakness (e.g. InTheWild EER 43%) — the 0.83% figure is strictly
ASVspoof2019-LA in-domain.

## 5. Threshold selection

The data-driven operating points are degenerate (EER threshold 0.878 at
EER 87.5%; Youden optimum at threshold 1.000, i.e. "label everything
genuine"), so NO calibrated thresholds are adopted. VAuth keeps its existing
operational defaults GREEN<0.60 / YELLOW<0.75 / ORANGE<0.90 / RED (configurable
via VAUTH_GREEN_T/VAUTH_YELLOW_T/VAUTH_ORANGE_T) explicitly as
non-scientific defaults. Real thresholds require in-domain labelled data.

## 6. Calibration decision (deliberately NOT shipped)

A Platt fit on these 24 files yields slope a=-1.85 (a sign flip learned from
a tiny set). Shipping `models/calibration.json` from this would be score
manipulation, so no calibration file is shipped: the backend
`ScoreCalibrator` runs as identity (`score_calibrated: false`,
`model_raw_score` always preserved). The layer, the `--calibrate-out` writer,
and the plumbing are implemented and tested for future use with proper data.

## 7. Telephony robustness

Mean |Δscore| clean→telephony 0.175 (max 0.496): telephony processing moves
scores substantially. Accuracy 0.292→0.500 / EER 0.875→0.750 looks like an
"improvement" only because degradation compresses everything toward
mid-range while all 8 genuine files remain false positives in both
conditions. Verdict: NOT robust; telephony behaviour is unvalidated.

## 8. Hackathon scenario (same statement, same pipeline)

`py scripts/hackathon_check.py --real data/eval/real/arctic_a0001.wav
--synthetic data/eval/synthetic/arctic_a0001__en-US-AriaNeural.wav ...`
→ `data/eval/hackathon_report.json`: genuine mean AASIST 0.998 (final RED)
vs clone 0.547 (final YELLOW). The generic checkpoint ranks this genuine
sample MORE spoof-like than its TTS clone. Reported as a failure of the
generic checkpoint on local audio, with raw logits preserved per window.

## 9. Indic languages (FUTURE architecture, no data evaluated)

`evaluate_model.py` already supports grouped layouts
(`--real DIR/<lang>/*.wav`, e.g. `hi/ ta/ te/`) with per-group metrics in the
report. No Hindi/Tamil/Telugu audio has been collected or evaluated, so no
robustness is claimed. Path when data exists: record same-statement
genuine/clone pairs per language → grouped eval → per-group thresholds.

## 10. Limitations

Small set (24 files, 1 genuine speaker, 1 TTS engine, English only);
file-level mean aggregation hides window variance; no score normalisation,
no fine-tuning, no confidence intervals. A production claim needs in-domain
labelled trials with reported EER/min-tDCF.
