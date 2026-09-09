"""Banking simulator tests: policy mapping + backend-enforced transitions."""
from __future__ import annotations

import pytest

from app.integrations.banking.base import PolicyDeniedError
from app.integrations.banking.policy import decide
from app.integrations.banking.service import MemoryBankingProvider

GREEN = {"risk_score": 0.1, "alert_level": "GREEN",
         "requires_secondary_verification": False, "protection_state": "NORMAL"}
RED = {"risk_score": 0.92, "alert_level": "RED",
       "requires_secondary_verification": True, "protection_state": "BLOCKED"}


def test_policy_green_pending():
    d = decide("GREEN", False, "NORMAL", 500_000, True)
    assert d["status"] == "PENDING"


def test_policy_orange_sensitive_holds():
    d = decide("ORANGE", True, "SECONDARY_VERIFICATION_REQUIRED", 500_000, True)
    assert d["status"] == "PENDING_VERIFICATION"
    assert "otp" in d["required_actions"]


def test_policy_red_sensitive_holds_with_escalation():
    d = decide("RED", True, "BLOCKED", 500_000, True)
    assert d["status"] == "PENDING_VERIFICATION"
    assert "supervisor_approval" in d["required_actions"]


def test_policy_red_nonsensitive_does_not_hold():
    # RED + ordinary small action -> alert/warning, NOT a hold.
    d = decide("RED", False, "NORMAL", 500.0, False)
    assert d["status"] == "PENDING"
    assert "warning" in d["reason"].lower() or "monitor" in d["required_actions"]


def test_safe_flow_approve_deducts():
    bank = MemoryBankingProvider()
    tx = bank.create_transaction(account_id="VAUTH-10001", amount=500_000.0,
                                 description="t", vauth=GREEN, sensitive_action=True)
    assert tx["status"] == "PENDING"
    done = bank.approve_transaction(tx["id"])
    assert done["status"] == "APPROVED"
    assert bank.account_summary()["balance"] == 750_000.0


def test_hold_then_approve_rejected_then_fail_blocks():
    bank = MemoryBankingProvider()
    tx = bank.create_transaction(account_id="VAUTH-10001", amount=500_000.0,
                                 description="t", vauth=RED, sensitive_action=True)
    assert tx["status"] == "PENDING_VERIFICATION"
    # CRITICAL: direct approve while held must fail (no UI bypass).
    with pytest.raises(PolicyDeniedError):
        bank.approve_transaction(tx["id"])
    out = bank.verify_transaction(tx["id"], "otp", False)
    assert out["status"] == "BLOCKED"
    with pytest.raises(PolicyDeniedError):
        bank.approve_transaction(tx["id"])


def test_verify_success_approves():
    bank = MemoryBankingProvider()
    tx = bank.create_transaction(account_id="VAUTH-10001", amount=500_000.0,
                                 description="t", vauth=RED, sensitive_action=True)
    out = bank.verify_transaction(tx["id"], "otp", True)
    assert out["status"] == "APPROVED"
    assert bank.account_summary()["balance"] == 750_000.0


def test_api_account_and_snapshot(client):
    assert client.get("/api/banking/account").json()["customer"] == "Rahul Sharma"
    snap = client.get("/api/banking/vauth").json()
    assert {"risk_score", "alert_level", "requires_secondary_verification",
            "protection_state"} <= set(snap)


def test_api_approve_while_held_rejected_over_http(client):
    client.post("/api/demo/reset")
    tx = client.post("/api/banking/transactions",
                     json={"amount": 500_000, "sensitive_action": True}).json()
    assert tx["status"] == "PENDING"  # clean GREEN pipeline
    held = client.post(f"/api/banking/transactions/{tx['id']}/hold").json()
    assert held["status"] == "PENDING_VERIFICATION"
    # Malicious client tries to approve directly -> must fail with 409.
    r = client.post(f"/api/banking/transactions/{tx['id']}/approve")
    assert r.status_code == 409
    # Failed OTP challenge -> BLOCKED, still not approvable.
    assert client.post(f"/api/banking/transactions/{tx['id']}/verify",
                       json={"method": "otp", "success": False}).json()["status"] == "BLOCKED"
    assert client.post(f"/api/banking/transactions/{tx['id']}/approve").status_code == 409


def test_api_verify_success_approves_over_http(client):
    client.post("/api/demo/reset")
    tx = client.post("/api/banking/transactions",
                     json={"amount": 500_000, "sensitive_action": True}).json()
    client.post(f"/api/banking/transactions/{tx['id']}/hold")
    done = client.post(f"/api/banking/transactions/{tx['id']}/verify",
                       json={"method": "callback", "success": True}).json()
    assert done["status"] == "APPROVED"


def test_api_unknown_transaction_404(client):
    assert client.get("/api/banking/transactions/nope").status_code == 404
