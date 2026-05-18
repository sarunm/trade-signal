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
            FibLevel.timeframe == payload.timeframe,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.swing_high = payload.swing_high
        row.swing_low = payload.swing_low
        row.direction = payload.direction
        row.levels = payload.levels
        row.extensions = payload.extensions
        row.computed_at = payload.computed_at
    else:
        row = FibLevel(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            swing_high=payload.swing_high,
            swing_low=payload.swing_low,
            direction=payload.direction,
            levels=payload.levels,
            extensions=payload.extensions,
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
