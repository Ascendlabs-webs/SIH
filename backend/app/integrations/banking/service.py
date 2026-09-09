"""In-memory demo banking provider (default). No real money, no external calls.

Demo ledger: one customer (Rahul Sharma, VAUTH-10001, Rs.12,50,000).
Approval is ENFORCED here, not in the UI: approve_transaction() raises
PolicyDeniedError for anything but PENDING, so a client cannot bypass a
PENDING_VERIFICATION hold by calling approve directly.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.integrations.banking.base import (BankingProvider, NotFoundError,
                                           PolicyDeniedError)
from app.integrations.banking.policy import decide

BANK = "VAuth Demo Bank"
CUSTOMER = "Rahul Sharma"
ACCOUNT_ID = "VAUTH-10001"
OPENING_BALANCE = 1_250_000.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryBankingProvider(BankingProvider):
    name = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tx: dict[str, dict[str, Any]] = {}
        self.balance = OPENING_BALANCE

    def account_summary(self) -> dict[str, Any]:
        with self._lock:
            return {"bank": BANK, "customer": CUSTOMER,
                    "account_id": ACCOUNT_ID, "balance": round(self.balance, 2),
                    "simulated": True}

    def create_transaction(self, *, account_id: str, amount: float,
                           description: str, vauth: dict[str, Any],
                           sensitive_action: bool) -> dict[str, Any]:
        if account_id != ACCOUNT_ID:
            raise NotFoundError(f"Unknown account {account_id}")
        if amount <= 0:
            raise PolicyDeniedError("Amount must be positive")
        with self._lock:
            if amount > self.balance:
                tx = self._record(account_id, amount, description, sensitive_action,
                                  vauth, "FAILED", "Insufficient funds.", [])
                return tx
            decision = decide(str(vauth.get("alert_level", "GREEN")),
                              bool(vauth.get("requires_secondary_verification", False)),
                              str(vauth.get("protection_state", "NORMAL")),
                              float(amount), bool(sensitive_action))
            tx = self._record(account_id, amount, description, sensitive_action,
                              vauth, decision["status"], decision["reason"],
                              decision["required_actions"])
            return tx

    def get_transaction(self, tx_id: str) -> dict[str, Any]:
        with self._lock:
            if tx_id not in self._tx:
                raise NotFoundError(f"Unknown transaction {tx_id}")
            return dict(self._tx[tx_id])

    def hold_transaction(self, tx_id: str) -> dict[str, Any]:
        with self._lock:
            tx = self._get_locked(tx_id)
            if tx["status"] != "PENDING":
                raise PolicyDeniedError(f"Cannot hold from {tx['status']}")
            tx["status"] = "PENDING_VERIFICATION"
            tx["reason"] = "Manually held pending secondary verification."
            tx["updated_at"] = _now()
            return dict(tx)

    def approve_transaction(self, tx_id: str) -> dict[str, Any]:
        with self._lock:
            tx = self._get_locked(tx_id)
            if tx["status"] == "PENDING_VERIFICATION":
                raise PolicyDeniedError(
                    "Transaction is PENDING_VERIFICATION: approve is rejected "
                    "until a successful verification. Bypass attempt recorded.")
            if tx["status"] != "PENDING":
                raise PolicyDeniedError(f"Cannot approve from {tx['status']}")
            if tx["amount"] > self.balance:
                tx["status"] = "FAILED"
                tx["reason"] = "Insufficient funds at approval."
                tx["updated_at"] = _now()
                return dict(tx)
            self.balance = round(self.balance - tx["amount"], 2)
            tx["status"] = "APPROVED"
            tx["reason"] = "Approved."
            tx["balance_after"] = self.balance
            tx["updated_at"] = _now()
            return dict(tx)

    def block_transaction(self, tx_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            tx = self._get_locked(tx_id)
            if tx["status"] in ("APPROVED", "BLOCKED", "FAILED"):
                raise PolicyDeniedError(f"Cannot block from {tx['status']}")
            tx["status"] = "BLOCKED"
            tx["reason"] = reason or "Blocked."
            tx["updated_at"] = _now()
            return dict(tx)

    def verify_transaction(self, tx_id: str, method: str,
                           success: bool) -> dict[str, Any]:
        with self._lock:
            tx = self._get_locked(tx_id)
            if tx["status"] != "PENDING_VERIFICATION":
                raise PolicyDeniedError(
                    f"Verification only applies to PENDING_VERIFICATION (now {tx['status']})")
            tx["verification"].append({"method": method, "success": bool(success),
                                       "at": _now(), "simulated": True})
            if success:
                if tx["amount"] > self.balance:
                    tx["status"] = "FAILED"
                    tx["reason"] = "Verified but insufficient funds."
                else:
                    self.balance = round(self.balance - tx["amount"], 2)
                    tx["status"] = "APPROVED"
                    tx["reason"] = f"Verified via simulated {method}; approved."
                    tx["balance_after"] = self.balance
            else:
                tx["status"] = "BLOCKED"
                tx["reason"] = (f"Simulated {method} verification FAILED; "
                                "transaction blocked.")
            tx["updated_at"] = _now()
            return dict(tx)

    # -- internals ---------------------------------------------------------
    def _get_locked(self, tx_id: str) -> dict[str, Any]:
        if tx_id not in self._tx:
            raise NotFoundError(f"Unknown transaction {tx_id}")
        return self._tx[tx_id]

    def _record(self, account_id: str, amount: float, description: str,
                sensitive_action: bool, vauth: dict[str, Any], status: str,
                reason: str, required: list[str]) -> dict[str, Any]:
        tx_id = uuid.uuid4().hex[:12]
        tx = {"id": tx_id, "account_id": account_id, "amount": float(amount),
              "description": description, "status": status,
              "sensitive_action": bool(sensitive_action),
              "vauth": {"risk_score": float(vauth.get("risk_score", 0.0)),
                        "alert_level": str(vauth.get("alert_level", "GREEN")),
                        "requires_secondary_verification": bool(
                            vauth.get("requires_secondary_verification", False)),
                        "protection_state": str(vauth.get("protection_state", "NORMAL"))},
              "required_actions": list(required), "verification": [],
              "reason": reason, "balance_after": None,
              "created_at": _now(), "updated_at": _now()}
        self._tx[tx_id] = tx
        return dict(tx)


_bank: MemoryBankingProvider | None = None


def get_bank() -> MemoryBankingProvider:
    global _bank
    if _bank is None:
        _bank = MemoryBankingProvider()
    return _bank


def reset_bank() -> MemoryBankingProvider:
    """Restore the opening demo ledger (demo-only reset)."""
    global _bank
    _bank = MemoryBankingProvider()
    return _bank
