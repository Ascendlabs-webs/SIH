"""VAuth assistant: grounded Q&A over live backend state (no external LLM).

Answers questions about the CURRENT session — risk, alert level, protection
state, active model, history — plus how-to guidance for the demo. All facts
come from the live pipeline/history/model status; nothing is hallucinated
from training data. Runs anywhere (including Render free tier).
"""
from __future__ import annotations

import re


def _snapshot() -> dict:
    from app.services.history import get_history
    from app.services.pipeline import get_pipeline

    pipe = get_pipeline()
    det = pipe.detector
    items = get_history().list(limit=1)
    last = items[-1] if items else {}
    prot = pipe.protection.snapshot()
    return {
        "risk": float(last.get("risk_score", 0.0)) if last else 0.0,
        "alert": str(last.get("alert_level", "NONE")) if last else "NONE",
        "classification": str(last.get("classification", "—")) if last else "—",
        "has_result": bool(last),
        "timestamp": str(last.get("timestamp", "")) if last else "",
        "protection": str(prot.get("state", "NORMAL")),
        "required": list(prot.get("required_actions", [])),
        "model": str(getattr(det, "model_name", getattr(det, "name", "demo"))),
        "is_demo": bool(getattr(det, "is_demo", True)),
        "warning": getattr(pipe, "detector_warning", None),
    }


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def answer(question: str, client_state: dict | None = None) -> dict:
    q = (question or "").lower()
    s = _snapshot()
    if client_state and isinstance(client_state.get("risk_score"), (int, float)):
        # Prefer the caller's own dashboard reading: the global history may
        # contain windows from other sessions, which would contradict the UI.
        s = {**s,
             "risk": float(client_state["risk_score"]),
             "alert": str(client_state.get("alert_level", s["alert"])),
             "classification": str(client_state.get("classification", s["classification"])),
             "has_result": True}
    ctx = {"risk_score": s["risk"], "alert_level": s["alert"],
           "protection_state": s["protection"], "model": s["model"],
           "is_demo": s["is_demo"]}

    def has(*words: str) -> bool:
        return any(re.search(rf"\b{w}s?\b", q) for w in words)

    if has("risk", "score", "status", "result", "safe", "danger", "meter"):
        if not s["has_result"]:
            text = ("No audio has been analyzed yet in this session. Run Real Speech, "
                    "Synthetic, use the microphone, or upload a WAV — I will read the "
                    "live risk here.")
        else:
            text = (f"Current risk is {_pct(s['risk'])} ({s['alert']}, {s['classification']}). "
                    f"Protection state: {s['protection']}.")
            if s["protection"] in ("SECONDARY_VERIFICATION_REQUIRED", "BLOCKED"):
                text += " Treat the caller as unverified until a challenge succeeds."
            elif s["alert"] in ("ORANGE", "RED"):
                text += " Elevated but not holding: keep monitoring for more windows."
        return {"answer": text, "context": ctx}

    if has("how", "demo", "start", "use", "run", "help", "microphone", "upload", "twilio", "call"):
        text = ("Try: 1) Real Speech Demo (recorded human, should stay GREEN), "
                "2) Synthetic Demo (attack sample, should go RED), "
                "3) Simulate Live Call (your mic as the caller), "
                "4) Upload any WAV, 5) Demo Bank for the money flow.")
        return {"answer": text, "context": ctx}

    if has("action", "recommend", "next", "should", "verify", "otp", "block"):
        if s["protection"] in ("SECONDARY_VERIFICATION_REQUIRED", "BLOCKED"):
            acts = ", ".join(s["required"]) or "OTP / callback"
            text = (f"Protection is {s['protection']}. Next step: complete a challenge "
                    f"({acts}) on the dashboard or bank page; a failed challenge blocks, "
                    f"a passed one releases.")
        elif s["protection"] == "VERIFIED":
            text = "Already VERIFIED — the held action is released."
        else:
            text = ("No verification is currently required (state "
                    f"{s['protection']}). If risk rises, use Request OTP / Callback.")
        return {"answer": text, "context": ctx}

    if has("model", "aasist", "spectra", "detector", "ml", "demo", "ai"):
        mode = "DEMO heuristic" if s["is_demo"] else f"REAL ML ({s['model']})"
        text = f"Active detector: {s['model']} — {mode}."
        if s["warning"]:
            text += f" Warning: {s['warning']}"
        elif not s["is_demo"]:
            text += (" Research benchmark checkpoint, not production validation — "
                     "see models/BENCHMARKS.md.")
        else:
            text += (" Deterministic placeholder for pipeline demos; swap in a trained "
                     "anti-spoof model for real evaluation.")
        return {"answer": text, "context": ctx}

    if has("bank", "transaction", "transfer", "money", "payment", "otp"):
        text = ("Open the Demo Bank page (header link). Create the ₹5,00,000 transfer: "
                "GREEN risk approves it; ORANGE/RED holds it as PENDING_VERIFICATION, "
                "where direct Approve is rejected by the backend until a simulated "
                "OTP/callback/supervisor challenge passes. Simulated money only.")
        return {"answer": text, "context": ctx}

    if has("why", "explain", "explanation", "reason", "cause", "how come"):
        if not s["has_result"]:
            text = ("Nothing has been scored yet, so there is no risk to explain. "
                    "Run any demo and ask me again.")
        elif s["alert"] == "GREEN":
            text = (f"Risk is low ({_pct(s['risk'])}) because the analyzed windows scored "
                    f"below the 60% YELLOW line — the voice looks genuine ({s['classification']}). "
                    f"Protection stays {s['protection']}. It would turn risky if several "
                    f"windows in a row scored synthetic-looking (flat robotic traits) and "
                    f"pushed the rolling average past 60%, 75%, 90%.")
        else:
            text = (f"Risk is elevated ({_pct(s['risk'])}, {s['alert']}) because recent "
                    f"windows scored synthetic-looking, lifting the rolling average past "
                    f"the alert thresholds. Context added "
                    f"{s['protection']} state: {s['protection']}. "
                    f"Complete secondary verification to clear it.")
        return {"answer": text, "context": ctx}

    if has("threshold", "green", "yellow", "red", "orange", "level"):
        text = ("Risk bands: GREEN below 60%, YELLOW 60–75%, ORANGE 75–90%, RED above "
                "90% (configurable via VAUTH_GREEN_T / VAUTH_YELLOW_T / VAUTH_ORANGE_T).")
        return {"answer": text, "context": ctx}

    if has("privacy", "store", "record", "data"):
        text = ("Raw audio is never stored (STORE_RAW_AUDIO=false). Only scores, "
                "levels, timestamps and feature summaries are kept, from authorized "
                "sources only (uploads, mic, WebRTC, Twilio streams).")
        return {"answer": text, "context": ctx}

    if has("hi", "hello", "hey"):
        text = ("Hello — I am the VAuth assistant. Ask me about current risk, what to "
                "do next, the active model, or how to run any demo.")
        return {"answer": text, "context": ctx}

    text = ("I can answer about live risk, recommended actions, the active model, "
            "thresholds, privacy, the bank demo, or how to run things. "
            f"Right now: risk {_pct(s['risk'])} ({s['alert']}), protection {s['protection']}.")
    return {"answer": text, "context": ctx}
