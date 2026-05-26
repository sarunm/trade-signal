import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pattern import PaperTraderRule, Pattern
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade

logger = logging.getLogger(__name__)

BASELINE_ENABLED = os.getenv("BASELINE_ENABLED", "1") == "1"
BASELINE_RULE_MODE = os.getenv("BASELINE_RULE_MODE", "basket_5k")
BASELINE_PATTERN_STATUS = "baseline"
BASELINE_SPAWN_STRATEGY = "random_session_start"
BASELINE_DIRECTION_STRATEGY = os.getenv("BASELINE_DIRECTION_STRATEGY", "alternating")
BASELINE_VOLUME = Decimal(os.getenv("BASELINE_VOLUME", "0.10"))
BASELINE_VIRTUAL_BUDGET = Decimal(os.getenv("BASELINE_VIRTUAL_BUDGET", "5000"))


def _set_if_attr(obj, **kwargs) -> None:
    for k, v in kwargs.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


async def _find_baseline_pattern(session: AsyncSession) -> Optional[Pattern]:
    result = await session.execute(
        select(Pattern).where(Pattern.status == BASELINE_PATTERN_STATUS)
    )
    return result.scalars().first()


async def _find_baseline_rule(session: AsyncSession) -> Optional[PaperTraderRule]:
    pattern = await _find_baseline_pattern(session)
    if pattern is None:
        return None
    result = await session.execute(
        select(PaperTraderRule).where(
            PaperTraderRule.status == "active",
            PaperTraderRule.pattern_id == pattern.id,
        )
    )
    return result.scalars().first()


async def _last_baseline_trade(
    session: AsyncSession, rule: PaperTraderRule
) -> Optional[Trade]:
    rule_id_str = str(rule.id)
    result = await session.execute(
        select(Trade)
        .where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
        )
        .order_by(Trade.open_time.desc().nullslast())
        .limit(50)
    )
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") == rule_id_str:
            return trade
    return None


async def next_direction(
    session: AsyncSession, rule: PaperTraderRule
) -> Direction:
    if BASELINE_DIRECTION_STRATEGY == "longonly":
        return Direction.buy
    if BASELINE_DIRECTION_STRATEGY == "shortonly":
        return Direction.sell
    if BASELINE_DIRECTION_STRATEGY == "random":
        import random

        return random.choice([Direction.buy, Direction.sell])
    last = await _last_baseline_trade(session, rule)
    if last is None or last.direction == Direction.sell:
        return Direction.buy
    return Direction.sell


async def ensure_baseline_rule(session: AsyncSession) -> PaperTraderRule:
    pattern = await _find_baseline_pattern(session)
    if pattern is None:
        pattern = Pattern(
            indicator_slugs=[],
            timeframe="H1",
            win_rate=0.0,
            sample_count=0,
            status=BASELINE_PATTERN_STATUS,
        )
        session.add(pattern)
        await session.flush()

    rule = await _find_baseline_rule(session)
    if rule is None:
        rule = PaperTraderRule(
            pattern_id=pattern.id,
            status="active",
            mode=BASELINE_RULE_MODE,
            virtual_balance_start=BASELINE_VIRTUAL_BUDGET,
            virtual_balance_current=BASELINE_VIRTUAL_BUDGET,
        )
        _set_if_attr(rule, is_baseline=True, spawn_strategy=BASELINE_SPAWN_STRATEGY)
        session.add(rule)
        await session.flush()

    await session.commit()
    return rule


async def _has_open_baseline(session: AsyncSession, rule: PaperTraderRule) -> bool:
    rule_id_str = str(rule.id)
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_(None),
        )
    )
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") == rule_id_str:
            return True
    return False


async def _latest_h1_close(
    session: AsyncSession, symbol: str = "GOLD#"
) -> Optional[Decimal]:
    result = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == Timeframe.H1)
        .order_by(PriceBar.time.desc())
        .limit(1)
    )
    bar = result.scalars().first()
    return bar.close if bar else None


async def open_baseline_trade(
    session: AsyncSession,
    account_id: Optional[int],
    now: Optional[datetime] = None,
) -> Optional[Trade]:
    if not BASELINE_ENABLED:
        return None
    now = now or datetime.now(timezone.utc)
    rule = await ensure_baseline_rule(session)
    if await _has_open_baseline(session, rule):
        logger.info("baseline_runner: existing open baseline trade — skipping")
        return None

    last_close = await _latest_h1_close(session)
    if last_close is None:
        logger.warning("baseline_runner: no price bars; skipping")
        return None

    direction = await next_direction(session, rule)
    trade = Trade(
        ticket=int(now.timestamp() * 1000) % 1_000_000_000_000,
        symbol="GOLD#",
        direction=direction,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=now,
        fill_time=now,
        open_price=last_close,
        volume=BASELINE_VOLUME,
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={
            "paper_trader_rule_id": str(rule.id),
            "is_baseline": True,
        },
        account_id=account_id,
    )
    session.add(trade)
    rule.total_trades = (rule.total_trades or 0) + 1
    await session.commit()
    logger.info(
        "baseline_runner: opened %s baseline trade #%s @ %s",
        direction.value, trade.ticket, last_close,
    )
    return trade
