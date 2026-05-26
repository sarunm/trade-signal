from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_snapshot import AccountSnapshot
from models.trade import OrderState, Trade


async def _current_account_id(session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(AccountSnapshot.account_id)
        .where(AccountSnapshot.account_id.isnot(None))
        .order_by(AccountSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_user_avg_profit(
    session: AsyncSession,
    days: int = 30,
    min_sample: int = 10,
) -> Optional[Decimal]:
    account_id = await _current_account_id(session)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(func.count(Trade.id), func.avg(Trade.profit)).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.close_time.isnot(None),
        Trade.close_time >= cutoff,
        Trade.profit.isnot(None),
        Trade.profit > 0,
    )
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)

    count, avg = (await session.execute(stmt)).one()
    if count is None or count < min_sample or avg is None:
        return None
    return Decimal(avg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
