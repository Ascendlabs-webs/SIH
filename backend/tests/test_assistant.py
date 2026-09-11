"""Assistant endpoint tests (grounded, no weights needed)."""
from __future__ import annotations


def test_assistant_answers_without_audio(client):
    client.post("/api/demo/reset")  # hermetic: fresh session, empty history
    r = client.post("/api/assistant/ask", json={"question": "What is my current risk?"})
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body and "context" in body
    assert "No audio" in body["answer"]


def test_assistant_model_question(client):
    body = client.post("/api/assistant/ask", json={"question": "Which model is running?"}).json()
    assert "DemoVoiceDetector" in body["answer"] or "AASIST" in body["answer"]


def test_assistant_howto_and_thresholds(client):
    assert "Synthetic" in client.post("/api/assistant/ask", json={"question": "How do I run the demo?"}).json()["answer"]
    assert "60%" in client.post("/api/assistant/ask", json={"question": "What are the thresholds?"}).json()["answer"]


def test_assistant_rejects_empty(client):
    assert client.post("/api/assistant/ask", json={"question": ""}).status_code == 422


def test_assistant_why_explains(client, genuine_audio):
    audio, sr = genuine_audio
    client.post("/api/analyze", json={"samples": [float(x) for x in audio[: sr * 3]], "sample_rate": sr})
    body = client.post("/api/assistant/ask", json={"question": "why it's not risky?"}).json()
    assert "60%" in body["answer"] or "low" in body["answer"].lower()


def test_assistant_reflects_live_risk(client, genuine_audio):
    audio, sr = genuine_audio
    client.post("/api/analyze", json={"samples": [float(x) for x in audio[: sr * 3]], "sample_rate": sr})
    body = client.post("/api/assistant/ask", json={"question": "status please"}).json()
    assert "%" in body["answer"]
    assert body["context"]["alert_level"] in ("GREEN", "YELLOW", "ORANGE", "RED")


def test_assistant_answers_project_question_from_kb(client):
    client.post("/api/demo/reset")  # hermetic: KB fallback needs empty history
    body = client.post("/api/assistant/ask", json={
        "question": "What audio format does the Vonage adapter expect?"}).json()
    assert "l16" in body["answer"].lower() or "pcm" in body["answer"].lower()
    body = client.post("/api/assistant/ask", json={
        "question": "How does the banking hold policy treat RED risk?"}).json()
    assert "PENDING_VERIFICATION" in body["answer"]


def test_assistant_prefers_caller_dashboard_state(client):
    body = client.post("/api/assistant/ask", json={
        "question": "What is my current risk?",
        "client_state": {"risk_score": 0.11, "alert_level": "GREEN", "classification": "REAL"},
    }).json()
    assert "11%" in body["answer"]
    assert "GREEN" in body["answer"]
