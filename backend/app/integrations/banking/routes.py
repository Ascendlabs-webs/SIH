"""Banking demo API: the bank ENFORCES the VAuth security decision.

Every transaction creation snapshots the CURRENT VAuth state (risk score,
alert level, requires_secondary_verification, protection state) from the
live in-process pipeline — no duplicate risk logic lives here.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.integrations.banking.base import NotFoundError, PolicyDeniedError
from app.integrations.banking.schemas import (AccountResponse,
                                              CreateTransactionRequest,
                                              TransactionResponse,
                                              VerifyRequest)
from app.integrations.banking.service import get_bank, reset_bank
from app.services.history import get_history
from app.services.pipeline import get_pipeline

router = APIRouter()


def current_vauth() -> dict:
    pipe = get_pipeline()
    items = get_history().list(limit=1)
    if items:
        last = items[-1]
        risk = float(last.get("risk_score", 0.0))
        alert = str(last.get("alert_level", "GREEN"))
        requires = bool(last.get("requires_secondary_verification", False))
    else:
        risk, alert, requires = 0.0, "GREEN", False
    return {"risk_score": risk, "alert_level": alert,
            "requires_secondary_verification": requires,
            "protection_state": str(pipe.protection.snapshot().get("state", "NORMAL"))}


def _wrap(tx: dict) -> TransactionResponse:
    return TransactionResponse(**tx)


@router.get("/account", response_model=AccountResponse)
def account() -> AccountResponse:
    return AccountResponse(**get_bank().account_summary())


@router.post("/reset", response_model=AccountResponse)
def reset_ledger() -> AccountResponse:
    """Demo-only: restore the opening ledger (Rs.12,50,000, no transactions)."""
    return AccountResponse(**reset_bank().account_summary())


@router.get("/vauth", response_model=dict)
def vauth_snapshot() -> dict:
    """The exact VAuth decision the bank will enforce (for the demo UI)."""
    return current_vauth()


@router.post("/transactions", response_model=TransactionResponse)
def create_transaction(req: CreateTransactionRequest) -> TransactionResponse:
    try:
        tx = get_bank().create_transaction(
            account_id=req.account_id, amount=req.amount,
            description=req.description, vauth=current_vauth(),
            sensitive_action=req.sensitive_action)
    except (PolicyDeniedError, NotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _wrap(tx)


@router.get("/transactions/{tx_id}", response_model=TransactionResponse)
def get_transaction(tx_id: str) -> TransactionResponse:
    try:
        return _wrap(get_bank().get_transaction(tx_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/transactions/{tx_id}/hold", response_model=TransactionResponse)
def hold_transaction(tx_id: str) -> TransactionResponse:
    try:
        return _wrap(get_bank().hold_transaction(tx_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyDeniedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/transactions/{tx_id}/approve", response_model=TransactionResponse)
def approve_transaction(tx_id: str) -> TransactionResponse:
    """Backend-enforced: PENDING_VERIFICATION cannot be approved directly."""
    try:
        return _wrap(get_bank().approve_transaction(tx_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyDeniedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/transactions/{tx_id}/block", response_model=TransactionResponse)
def block_transaction(tx_id: str, reason: str = "") -> TransactionResponse:
    try:
        return _wrap(get_bank().block_transaction(tx_id, reason))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyDeniedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/transactions/{tx_id}/verify", response_model=TransactionResponse)
def verify_transaction(tx_id: str, req: VerifyRequest) -> TransactionResponse:
    """SIMULATED verification only (no real OTP/SMS/bank auth)."""
    try:
        return _wrap(get_bank().verify_transaction(tx_id, req.method, req.success))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyDeniedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
