"""Fineract provider (FUTURE integration — not wired by default).

Next step when a real core-banking sandbox is wanted: run Apache Fineract
locally (Docker) and implement BankingProvider against its REST API
(clients, savings accounts, transfers, charges/holds). Suggested local
topology (from the integration brief):

  Ubuntu VM (VMware)
  └── Docker
      ├── fineract (core banking)
      ├── postgres/mysql (Fineract database)
      └── optional banking UI

VAuth stays where it is; this provider would call Fineract over HTTP and
translate Fineract transfer/hold states into the policy states used here
(PENDING / PENDING_VERIFICATION / APPROVED / BLOCKED / FAILED).

Until then the default provider is MemoryBankingProvider (service.py).
Set BANKING_PROVIDER=fineract only after implementing the methods below.
"""
from __future__ import annotations

from typing import Any

from app.integrations.banking.base import BankingProvider


class FineractNotConfiguredError(RuntimeError):
    pass


class FineractBankingProvider(BankingProvider):
    name = "fineract"

    def __init__(self, base_url: str = "", username: str = "",
                 password: str = "", tenant: str = "default") -> None:
        raise FineractNotConfiguredError(
            "Fineract provider is a documented stub. Run a local Fineract "
            "sandbox, then implement these methods against its REST API.")

    def create_transaction(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def get_transaction(self, tx_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def hold_transaction(self, tx_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def approve_transaction(self, tx_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def block_transaction(self, tx_id: str, reason: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def verify_transaction(self, tx_id: str, method: str, success: bool) -> dict[str, Any]:
        raise NotImplementedError

    def account_summary(self) -> dict[str, Any]:
        raise NotImplementedError
