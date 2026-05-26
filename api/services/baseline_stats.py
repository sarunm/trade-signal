import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pattern import PaperTraderRule, Pattern
from models.trade import PaperMode, Trade
from services.baseline_runner import BASELINE_PATTERN_STATUS

logger = logging.getLogger(__name__)

BASELINE_WINRATE_WINDOW_DAYS = int(os.getenv("BASELINE_WINRATE_WINDOW_DAYS", "30"))


async def _baseline_rule_id(session: AsyncSession) -> Optional[str]:
    pattern = (
        await session.execute(
            select(Pattern).where(Pattern.status == BASELINE_PATTERN_STATUS)
        )
    ).scalars().first()
    if pattern is None:
        return None
    rule = (
        await session.execute(
            select(PaperTraderRule).where(
                PaperTraderRule.pattern_id == pattern.id,
                PaperTraderRule.status == "active",
            )
        )
    ).scalars().first()
    return str(rule.id) if rule else None


async def get_baseline_winrate(
    session: AsyncSession, days: Optional[int] = None
) -> float:
    days = days or BASELINE_WINRATE_WINDOW_DAYS
    rule_id = await _baseline_rule_id(session)
    if rule_id is None:
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
        )
    )
    total = 0
    wins = 0
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") != rule_id:
            continue
        total += 1
        if trade.profit is not None and trade.profit > 0:
            wins += 1
    return wins / total if total else 0.0
