"""Banking provider interface + shared errors.

VAuth produces the SECURITY DECISION; providers ENFORCE it. VAuth never
touches banking state directly — all enforcement flows through this API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PolicyDeniedError(RuntimeError):
    """Raised when a state transition violates the security policy (HTTP 409)."""


class NotFoundError(RuntimeError):
    """Unknown transaction id (HTTP 404)."""


class BankingProvider(ABC):
    name: str = "base"

    @abstractmethod
    def create_transaction(self, *, account_id: str, amount: float,
                           description: str, vauth: dict[str, Any],
                           sensitive_action: bool) -> dict[str, Any]:
        """Create a transaction, applying the VAuth policy at creation."""

    @abstractmethod
    def get_transaction(self, tx_id: str) -> dict[str, Any]:
        """Return the transaction record."""

    @abstractmethod
    def hold_transaction(self, tx_id: str) -> dict[str, Any]:
        """Move PENDING -> PENDING_VERIFICATION (manual hold)."""

    @abstractmethod
    def approve_transaction(self, tx_id: str) -> dict[str, Any]:
        """Approve. MUST fail unless the policy allows it (never from
        PENDING_VERIFICATION without a successful verification)."""

    @abstractmethod
    def block_transaction(self, tx_id: str, reason: str = "") -> dict[str, Any]:
        """Move to BLOCKED (from PENDING or PENDING_VERIFICATION)."""

    @abstractmethod
    def verify_transaction(self, tx_id: str, method: str,
                           success: bool) -> dict[str, Any]:
        """Record a SIMULATED verification challenge outcome."""

    @abstractmethod
    def account_summary(self) -> dict[str, Any]:
        """Demo customer / account snapshot."""
