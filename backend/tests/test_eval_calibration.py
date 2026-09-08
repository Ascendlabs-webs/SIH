"""Calibration layer + eval-math tests (no checkpoint needed)."""
from __future__ import annotations

import json

import numpy as np

from app.risk.calibration import (ScoreCalibrator, eer_from_scores,
                                  youden_threshold)


def test_eer_separable():
    y = np.array([0] * 10 + [1] * 10)
    s = np.array([0.1] * 10 + [0.9] * 10, dtype=float)
    eer, thr = eer_from_scores(y, s)
    assert eer == 0.0
    assert 0.1 <= thr <= 0.9


def test_eer_single_class_nan():
    eer, _ = eer_from_scores(np.zeros(5, dtype=int), np.linspace(0, 1, 5))
    assert np.isnan(eer)


def test_youden_separable():
    y = np.array([0] * 10 + [1] * 10)
    s = np.array([0.2] * 10 + [0.8] * 10, dtype=float)
    thr, j = youden_threshold(y, s)
    assert j == 1.0
    assert 0.2 <= thr <= 0.8


def test_calibrator_identity_by_default():
    cal = ScoreCalibrator(path="models/does-not-exist.json")
    assert cal.fitted is False
    assert cal.apply(0.73) == 0.73
    assert cal.apply(0.0) == 0.0


def test_calibrator_platt_math(tmp_path):
    payload = {"method": "platt_logistic", "a": 5.0, "b": -2.5, "fitted": True}
    p = tmp_path / "cal.json"
    p.write_text(json.dumps(payload))
    cal = ScoreCalibrator(path=str(p))
    assert cal.fitted is True
    import math
    assert cal.apply(0.5) == 0.5  # 5*0.5-2.5 = 0
    assert cal.apply(1.0) > 0.9
    assert 0.0 <= cal.apply(0.0) <= 1.0
    assert math.isclose(cal.apply(0.9), 1 / (1 + math.exp(-(5 * 0.9 - 2.5))))


def test_calibrator_bad_file_identity(tmp_path):
    p = tmp_path / "cal.json"
    p.write_text("{not json")
    cal = ScoreCalibrator(path=str(p))
    assert cal.fitted is False
    assert cal.apply(0.4) == 0.4


def test_telephony_degrade_shape_and_determinism():
    from app.audio.preprocessor import telephony_degrade

    rng = np.random.default_rng(0)
    audio = rng.normal(0, 0.2, size=16000 * 3).astype(np.float32)
    a = telephony_degrade(audio)
    b = telephony_degrade(audio)
    assert len(a) == len(audio)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, audio)  # degradation actually changes audio
    assert np.all(np.isfinite(a))


def test_pipeline_reports_raw_and_calibrated_flag(client, genuine_audio):
    audio, sr = genuine_audio
    r = client.post("/api/analyze",
                    json={"samples": [float(x) for x in audio[: sr * 3]],
                          "sample_rate": sr})
    assert r.status_code == 200
    body = r.json()
    assert "model_raw_score" in body
    assert body["score_calibrated"] is False  # no calibration.json shipped
    assert 0.0 <= body["model_raw_score"] <= 1.0


def test_model_status_reports_calibration(client):
    body = client.get("/api/model/status").json()
    assert "calibration" in body
    assert body["calibration"]["fitted"] is False
