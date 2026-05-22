from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.fib_level import FibLevel
from schemas.fib_level import FibLevelInSchema, FibLevelResponse

router = APIRouter(prefix="/api", tags=["fib-levels"])


@router.post("/fib-levels", status_code=201, response_model=FibLevelResponse)
async def receive_fib_levels(
    payload: FibLevelInSchema,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FibLevel).where(
            FibLevel.symbol == payload.symbol,
            FibLevel.period == payload.period,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.prev_high = payload.prev_high
        row.prev_low = payload.prev_low
        row.prev_close = payload.prev_close
        row.pp = payload.pp
        row.resistance = payload.resistance
        row.support = payload.support
        row.computed_at = payload.computed_at
    else:
        row = FibLevel(
            symbol=payload.symbol,
            period=payload.period,
            prev_high=payload.prev_high,
            prev_low=payload.prev_low,
            prev_close=payload.prev_close,
            pp=payload.pp,
            resistance=payload.resistance,
            support=payload.support,
            computed_at=payload.computed_at,
        )
        session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/fib-levels", response_model=list[FibLevelResponse])
async def get_fib_levels(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(FibLevel))
    return result.scalars().all()
