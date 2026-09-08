"""Demo service: streams local demo wavs through the real pipeline in 2-3s windows."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.audio.preprocessor import chunk_audio, preprocess_audio
from app.config import get_settings
from app.services.pipeline import reset_pipeline

ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = ROOT / "data" / "demo"


def demo_path(scenario: str) -> Path:
    if scenario == "synthetic":
        # In REAL ML mode the attack sample must be real synthetic speech:
        # placeholder beeps are not speech and benchmark models do not treat
        # them as attacks. In DEMO mode the beeps drive the heuristic.
        if get_settings().detector != "demo":
            tts = DEMO_DIR / "demo_synthetic_tts.wav"
            if tts.exists():
                return tts
        return DEMO_DIR / "demo_synthetic.wav"
    if scenario == "real_speech":
        # Recorded human speech (CMU Arctic, research use): the genuine demo
        # that scores REAL under benchmark ML models too. Beeps are not speech.
        return DEMO_DIR / "demo_real_speech.wav"
    return DEMO_DIR / "demo_real.wav"


def run_demo(scenario: str, context: dict | None = None) -> dict:
    import soundfile as sf

    scenario = {"synthetic": "synthetic", "real_speech": "real_speech"}.get(scenario, "real")
    path = demo_path(scenario)
    if not path.exists():
        raise FileNotFoundError(
            f"Demo audio missing: {path}. Run `py scripts/generate_demo_audio.py` first."
        )
    settings = get_settings()
    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    pre = preprocess_audio(audio, int(sr), settings.target_sample_rate)
    clean = pre["audio"]
    windows = chunk_audio(clean, settings.target_sample_rate, settings.window_seconds)

    pipeline = reset_pipeline()
    results = []
    for w in windows:
        r = pipeline.process_window(w, settings.target_sample_rate, context or {"call_type": "demo"})
        results.append(r)
    return {"scenario": scenario, "windows": len(results), "results": results,
            "audio_source": path.name}
