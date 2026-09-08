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
    name = "demo_synthetic.wav" if scenario in ("synthetic",) else "demo_real.wav"
    return DEMO_DIR / name


def run_demo(scenario: str, context: dict | None = None) -> dict:
    import soundfile as sf

    scenario = "synthetic" if scenario == "synthetic" else "real"
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
    return {"scenario": scenario, "windows": len(results), "results": results}
