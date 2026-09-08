"""Real acoustic feature extraction (librosa + numpy, optional parselmouth/pyworld).

AudioFeatureExtractor.extract(audio, sample_rate) -> dict with scalar summaries
plus a normalised feature vector via .to_vector(features).

Never crashes when optional packages are missing: jitter/shimmer fall back to
deterministic F0/amplitude-variation heuristics and are flagged as estimates.
"""
from __future__ import annotations

import numpy as np

from app.audio.vad import frame_energy_vad, pause_statistics

FEATURE_ORDER = [
    "mfcc_00", "mfcc_01", "mfcc_02", "mfcc_03", "mfcc_04", "mfcc_05", "mfcc_06",
    "mfcc_07", "mfcc_08", "mfcc_09", "mfcc_10", "mfcc_11", "mfcc_12",
    "mfcc_std_00", "mfcc_std_01", "mfcc_std_02", "mfcc_std_03", "mfcc_std_04",
    "mfcc_std_05", "mfcc_std_06", "mfcc_std_07", "mfcc_std_08", "mfcc_std_09",
    "mfcc_std_10", "mfcc_std_11", "mfcc_std_12",
    "spectral_centroid_mean", "spectral_centroid_std",
    "spectral_bandwidth_mean", "spectral_bandwidth_std",
    "spectral_rolloff_mean", "spectral_rolloff_std",
    "spectral_flux_mean", "spectral_flux_std",
    "zcr_mean", "zcr_std", "rms_mean", "rms_std",
    "mel_mean", "mel_std", "mel_max",
    "f0_mean", "f0_std", "voiced_ratio",
    "silence_ratio", "num_pauses", "mean_pause_sec",
    "jitter", "shimmer",
]


def _safe_mean(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    return float(x.mean()) if x.size else 0.0


def _safe_std(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    return float(x.std()) if x.size else 0.0


def _estimate_f0(audio: np.ndarray, sr: int) -> np.ndarray:
    """Frame-level F0 (Hz) with 0 for unvoiced. Tries librosa.yin, falls back to autocorrelation."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < sr // 4:
        return np.zeros(8, dtype=np.float32)
    try:
        import librosa

        f0 = librosa.yin(
            audio,
            fmin=50,
            fmax=500,
            sr=sr,
            frame_length=1024,
            hop_length=256,
        ).astype(np.float32)
        f0[~np.isfinite(f0)] = 0.0
        # yin returns values even for silence; gate by energy
        rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
        rms = rms / (rms.max() + 1e-9)
        if len(rms) == len(f0):
            f0[rms < 0.05] = 0.0
        return f0
    except Exception:
        pass
    # Fallback autocorrelation pitch tracker (coarse but dependency-free)
    hop = 256
    win = 1024
    out = []
    for start in range(0, max(1, len(audio) - win), hop):
        frame = audio[start : start + win] * np.hanning(win)
        if np.sqrt(np.mean(frame ** 2)) < 0.02:
            out.append(0.0)
            continue
        corr = np.correlate(frame, frame, mode="full")[win - 1 :]
        lo, hi = int(sr / 500), int(sr / 50)
        hi = min(hi, len(corr) - 1)
        if hi <= lo:
            out.append(0.0)
            continue
        seg = corr[lo:hi]
        peak = int(np.argmax(seg)) + lo
        out.append(float(sr / max(1, peak)) if corr[peak] > 0 else 0.0)
    if not out:
        return np.zeros(8, dtype=np.float32)
    return np.asarray(out, dtype=np.float32)


def _jitter_shimmer(audio: np.ndarray, sr: int, f0: np.ndarray) -> tuple[float, float, str]:
    """Return (jitter, shimmer, method). Prefers parselmouth/pyworld, else heuristic."""
    # Try praat-parselmouth (writes a transient temp WAV, unlinked immediately
    # after use; no raw audio is retained — see privacy docs in README).
    try:
        import parselmouth  # type: ignore

        import soundfile as sf  # noqa
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = tmp.name
        try:
            import soundfile as sf2

            sf2.write(path, audio.astype(np.float32), sr)
            snd = parselmouth.Sound(path)
            pp = snd.to_point_process()
            jitter = float(parselmouth.praat.call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
            shimmer = float(parselmouth.praat.call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6))
            if np.isfinite(jitter) and np.isfinite(shimmer):
                return float(jitter), float(shimmer), "parselmouth"
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    except Exception:
        pass
    # Try pyworld
    try:
        import pyworld as pw  # type: ignore

        x = audio.astype(np.float64)
        _f0, _t = pw.dio(x, sr)
        jitter = float(np.std(_f0[_f0 > 0]) / (np.mean(_f0[_f0 > 0]) + 1e-9)) if np.any(_f0 > 0) else 0.0
        amp_env = np.abs(x)
        shimmer = float(np.std(amp_env) / (np.mean(amp_env) + 1e-9) * 0.1)
        return float(np.clip(jitter, 0, 1)), float(np.clip(shimmer, 0, 1)), "pyworld"
    except Exception:
        pass
    # Deterministic heuristic fallback (clearly labelled estimate)
    voiced = f0[f0 > 0]
    if len(voiced) >= 3:
        diffs = np.abs(np.diff(voiced))
        jitter = float(np.mean(diffs) / (np.mean(voiced) + 1e-9))
    else:
        jitter = 0.0
    env_win = max(1, sr // 100)
    if len(audio) > env_win:
        env = np.convolve(np.abs(audio), np.ones(env_win) / env_win, mode="same")
        jitter_env = np.abs(np.diff(env))
        shimmer = float(np.mean(jitter_env) / (np.mean(env) + 1e-9))
    else:
        shimmer = 0.0
    return float(np.clip(jitter, 0, 1)), float(np.clip(shimmer, 0, 1)), "heuristic"


class AudioFeatureExtractor:
    """Stateless extractor: extract() -> feature dict; to_vector() -> normalised vector."""

    def __init__(self, n_mfcc: int = 13, sample_rate: int = 16000):
        self.n_mfcc = n_mfcc
        self.sample_rate = sample_rate

    def extract(self, audio: np.ndarray, sample_rate: int | None = None) -> dict:
        import librosa

        sr = int(sample_rate or self.sample_rate)
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0:
            raise ValueError("Empty audio buffer")

        y = audio
        # --- MFCC ---
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=self.n_mfcc)
        mfcc_mean = np.mean(mfcc, axis=1)
        mfcc_std = np.std(mfcc, axis=1)

        # --- Spectral ---
        cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        roll = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        rms = librosa.feature.rms(y=y)[0]
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64)
        mel_db = librosa.power_to_db(mel + 1e-10)

        # spectral flux = mean positive frame-to-frame magnitude change
        stft = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
        flux = np.sqrt(np.mean(np.diff(stft, axis=1) ** 2, axis=0)) if stft.shape[1] > 1 else np.zeros(1)

        # --- Prosody / pitch ---
        f0 = _estimate_f0(y, sr)
        voiced = f0[f0 > 0]
        f0_mean = float(np.mean(voiced)) if len(voiced) else 0.0
        f0_std = float(np.std(voiced)) if len(voiced) else 0.0
        voiced_ratio = float(len(voiced) / max(1, len(f0)))

        # --- Pauses / VAD ---
        vad = frame_energy_vad(y, sample_rate=sr)
        pauses = pause_statistics(vad["flags"])

        # --- Jitter / shimmer (optional backed) ---
        jitter, shimmer, method = _jitter_shimmer(y, sr, f0)

        feats: dict = {
            "mfcc": [float(v) for v in mfcc_mean],
            "mfcc_std": [float(v) for v in mfcc_std],
            "spectral_centroid": {"mean": _safe_mean(cent), "std": _safe_std(cent)},
            "spectral_bandwidth": {"mean": _safe_mean(bw), "std": _safe_std(bw)},
            "spectral_rolloff": {"mean": _safe_mean(roll), "std": _safe_std(roll)},
            "spectral_flux": {"mean": _safe_mean(flux), "std": _safe_std(flux)},
            "zcr": {"mean": _safe_mean(zcr), "std": _safe_std(zcr)},
            "rms": {"mean": _safe_mean(rms), "std": _safe_std(rms)},
            "mel": {
                "mean": float(np.mean(mel_db)),
                "std": float(np.std(mel_db)),
                "max": float(np.max(mel_db)),
            },
            "f0_mean": float(f0_mean),
            "f0_std": float(f0_std),
            "voiced_ratio": float(voiced_ratio),
            "silence_ratio": float(pauses["silence_ratio"]),
            "num_pauses": int(pauses["num_pauses"]),
            "mean_pause_sec": float(pauses["mean_pause_sec"]),
            "vad_active_ratio": float(vad["active_ratio"]),
            "vad_active": bool(vad["active"]),
            "jitter": float(jitter),
            "shimmer": float(shimmer),
            "jitter_method": method,
            "duration_sec": float(len(y) / sr),
            "sample_rate": int(sr),
        }
        return feats

    def to_vector(self, feats: dict) -> np.ndarray:
        """Deterministic normalised vector in FEATURE_ORDER (~48 dims)."""
        mfcc = list(feats.get("mfcc", [0.0] * 13))[:13]
        mfcc += [0.0] * (13 - len(mfcc))
        mfcc_s = list(feats.get("mfcc_std", [0.0] * 13))[:13]
        mfcc_s += [0.0] * (13 - len(mfcc_s))

        def g(key: str, sub: str = "mean") -> float:
            v = feats.get(key, {})
            if isinstance(v, dict):
                return float(v.get(sub, 0.0))
            return float(v or 0.0)

        raw = np.array(
            mfcc + mfcc_s + [
                g("spectral_centroid"), g("spectral_centroid", "std"),
                g("spectral_bandwidth"), g("spectral_bandwidth", "std"),
                g("spectral_rolloff"), g("spectral_rolloff", "std"),
                g("spectral_flux"), g("spectral_flux", "std"),
                g("zcr"), g("zcr", "std"), g("rms"), g("rms", "std"),
                feats.get("mel", {}).get("mean", 0.0) if isinstance(feats.get("mel"), dict) else 0.0,
                feats.get("mel", {}).get("std", 0.0) if isinstance(feats.get("mel"), dict) else 0.0,
                feats.get("mel", {}).get("max", 0.0) if isinstance(feats.get("mel"), dict) else 0.0,
                float(feats.get("f0_mean", 0.0)), float(feats.get("f0_std", 0.0)),
                float(feats.get("voiced_ratio", 0.0)),
                float(feats.get("silence_ratio", 0.0)), float(feats.get("num_pauses", 0)),
                float(feats.get("mean_pause_sec", 0.0)),
                float(feats.get("jitter", 0.0)), float(feats.get("shimmer", 0.0)),
            ],
            dtype=np.float64,
        )
        # Per-vector standardisation-lite: tanh squash after robust scaling
        # with fixed constants so vectors are comparable across calls.
        scale = np.array(
            [50.0] * 26 + [2000, 1500, 1500, 1000, 3000, 2000, 5, 5, 0.3, 0.2, 0.5, 0.3,
                           30, 15, 40, 200, 150, 1, 1, 8, 2, 0.5, 0.5],
            dtype=np.float64,
        )
        return np.tanh(raw / (scale + 1e-9)).astype(np.float32)

    @property
    def vector_dim(self) -> int:
        return len(FEATURE_ORDER)
