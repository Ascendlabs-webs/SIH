"""Health / status endpoint tests."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["app"] == "VAuth"


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["target_sample_rate"] == 16000
    assert body["detector"] in ("demo", "ml")
    assert "DEMO MODEL" in body["detector_label"]
