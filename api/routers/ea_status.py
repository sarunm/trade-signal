import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.ea_status import EAStatus
from schemas.ea_status import EAHeartbeatSchema, EAStatusResponse

EA_DISCONNECT_UI_THRESHOLD_SEC = int(os.getenv("EA_DISCONNECT_UI_THRESHOLD_SEC", 120))

router = APIRouter(prefix="/api", tags=["ea-status"])


@router.post("/ea-heartbeat", response_model=EAStatusResponse)
async def post_heartbeat(
    payload: EAHeartbeatSchema,
    session: AsyncSession = Depends(get_session),
):
    now = payload.timestamp or datetime.now(timezone.utc)
    existing = await session.get(EAStatus, payload.account_id)
    if existing is None:
        existing = EAStatus(account_id=payload.account_id, last_seen_at=now)
        session.add(existing)
    existing.last_seen_at = now
    if payload.version is not None:
        existing.version = payload.version
    if payload.symbol is not None:
        existing.symbol = payload.symbol
    await session.commit()
    await session.refresh(existing)
    return _to_response(existing, now)


@router.get("/ea-status", response_model=EAStatusResponse)
async def get_status(
    account_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(EAStatus, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ea_status not found")
    return _to_response(row, datetime.now(timezone.utc))


def _to_response(row: EAStatus, now: datetime) -> EAStatusResponse:
    last = row.last_seen_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (now - last).total_seconds())
    return EAStatusResponse(
        account_id=row.account_id,
        last_seen_at=last,
        version=row.version,
        symbol=row.symbol,
        seconds_since_last_seen=seconds,
        connected=seconds <= EA_DISCONNECT_UI_THRESHOLD_SEC,
    )
