"""Banking API schemas (simulated, demo-only)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class VAuthSnapshot(BaseModel):
    risk_score: float = 0.0
    alert_level: str = "GREEN"
    requires_secondary_verification: bool = False
    protection_state: str = "NORMAL"


class CreateTransactionRequest(BaseModel):
    amount: float = Field(..., gt=0, le=10_000_000)
    description: str = Field(default="Transfer", max_length=200)
    sensitive_action: bool = True
    account_id: str = "VAUTH-10001"


class VerifyRequest(BaseModel):
    method: Literal["otp", "callback", "supervisor"] = "otp"
    success: bool = True


class TransactionResponse(BaseModel):
    id: str
    account_id: str
    amount: float
    description: str
    status: str
    sensitive_action: bool
    vauth: VAuthSnapshot
    required_actions: List[str] = []
    verification: List[Dict[str, Any]] = []
    reason: str = ""
    balance_after: Optional[float] = None
    created_at: str = ""
    updated_at: str = ""


class AccountResponse(BaseModel):
    bank: str = "VAuth Demo Bank"
    customer: str = "Rahul Sharma"
    account_id: str = "VAUTH-10001"
    balance: float = 1_250_000.0
    simulated: bool = True
