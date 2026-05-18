from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.account_snapshot import AccountSnapshot
from schemas.account import AccountResponse

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/account", response_model=AccountResponse)
async def get_account(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AccountSnapshot).order_by(AccountSnapshot.timestamp.desc()).limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No account snapshot available")
    return snapshot
