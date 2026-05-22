from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_snapshot import AccountSnapshot
from models.trade import Trade
from schemas.trader_profile import CandidateRule, TraderProfileResponse, TraderProfileSummary

WIN_RATE_MIN_TRADES = 3
CANDIDATE_THRESHOLD = 15


async def _current_account_id(session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(AccountSnapshot.account_id)
        .where(AccountSnapshot.account_id.isnot(None))
        .order_by(AccountSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _account_filters(account_id: Optional[int]) -> list:
    if account_id is None:
        return []
    return [Trade.account_id == account_id]


async def _dominant_tag(session: AsyncSession, column, filters: list) -> Optional[str]:
    result = await session.execute(
        select(column, func.count().label("count"))
        .where(*filters, Trade.close_price.isnot(None), column.isnot(None))
        .group_by(column)
        .order_by(func.count().desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def build_trader_profile(session: AsyncSession) -> TraderProfileResponse:
    account_id = await _current_account_id(session)
    filters = _account_filters(account_id)

    dominant_setup = await _dominant_tag(session, Trade.setup_pattern, filters)
    dominant_bias = await _dominant_tag(session, Trade.trade_bias, filters)
    dominant_entry = await _dominant_tag(session, Trade.entry_candle, filters)
    dominant_fib = await _dominant_tag(session, Trade.near_fib_level, filters)

    totals = await session.execute(
        select(
            func.count().label("total"),
            func.sum(case((Trade.is_rescue.is_(True), 1), else_=0)).label("rescue_count"),
            func.sum(case((Trade.setup_pattern.isnot(None), 1), else_=0)).label("tagged_count"),
        ).where(*filters)
    )
    row = totals.first()
    total = row.total or 0
    rescue_rate = float(row.rescue_count or 0) / max(total, 1)
    total_tagged = int(row.tagged_count or 0)

    candidate_result = await session.execute(
        select(
            Trade.setup_pattern,
            Trade.trade_bias,
            func.count().label("count"),
            func.sum(case((Trade.profit > 0, 1), else_=0)).label("wins"),
        )
        .where(*filters, Trade.close_price.isnot(None), Trade.setup_pattern.isnot(None))
        .group_by(Trade.setup_pattern, Trade.trade_bias)
        .order_by(func.count().desc())
    )
    candidates = [
        CandidateRule(
            setup_pattern=row.setup_pattern,
            trade_bias=row.trade_bias,
            count=row.count,
            win_rate=float(row.wins) / row.count if row.count >= WIN_RATE_MIN_TRADES else None,
            threshold=CANDIDATE_THRESHOLD,
        )
        for row in candidate_result.all()
    ]

    return TraderProfileResponse(
        summary=TraderProfileSummary(
            dominant_setup=dominant_setup,
            dominant_bias=dominant_bias,
            dominant_entry=dominant_entry,
            dominant_fib=dominant_fib,
            rescue_rate=rescue_rate,
            total_tagged=total_tagged,
        ),
        candidates=candidates,
    )
