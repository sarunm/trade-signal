import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.pattern import PaperTraderRule
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services.behavioral_mirror import compute_user_avg_profit

XAUUSD_CONTRACT_SIZE = Decimal("100")
TRAIL_RETRACE_PCT = Decimal(os.getenv("BEHAVIORAL_TRAIL_RETRACE_PCT", "0.20"))
BEHAVIORAL_MIRROR_DAYS = int(os.getenv("BEHAVIORAL_MIRROR_DAYS", "30"))
BEHAVIORAL_MIRROR_MIN_SAMPLE = int(os.getenv("BEHAVIORAL_MIRROR_MIN_SAMPLE", "10"))


async def close_paper_trades_on_tick(
    session: AsyncSession,
    tick: MarketTickSchema,
) -> int:
    result = await session.execute(
        select(Trade).where(
            Trade.symbol == tick.symbol,
            Trade.is_paper == True,
            Trade.paper_mode == PaperMode.independent,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.close_price.is_(None),
        )
    )
    open_papers = result.scalars().all()
    if not open_papers:
        return 0

    rule_ids = {t.paper_trader_rule_id for t in open_papers if t.paper_trader_rule_id}
    rules_by_id: dict = {}
    if rule_ids:
        rule_rows = (
            await session.execute(
                select(PaperTraderRule).where(PaperTraderRule.id.in_(rule_ids))
            )
        ).scalars().all()
        rules_by_id = {r.id: r for r in rule_rows}

    user_avg: Optional[Decimal] = None
    user_avg_loaded = False
    closed = 0
    for trade in open_papers:
        exit_price, exit_reason = _exit_for_tick(trade, tick)
        if exit_price is None:
            rule = rules_by_id.get(trade.paper_trader_rule_id)
            if rule is None or rule.trail_strategy != "user_avg_trail":
                continue
            if not user_avg_loaded:
                user_avg = await compute_user_avg_profit(
                    session,
                    days=BEHAVIORAL_MIRROR_DAYS,
                    min_sample=BEHAVIORAL_MIRROR_MIN_SAMPLE,
                )
                user_avg_loaded = True
            if user_avg is None:
                continue
            trail_price = _side_price(trade, tick)
            if trail_price is None:
                continue
            unrealized = _paper_profit(trade, trail_price)
            if unrealized is None:
                continue
            armed = (trade.recovery_plan or {}).get("trail")
            if armed is None:
                if unrealized >= user_avg:
                    _arm_trail(trade, unrealized, trail_price)
                continue
            peak_profit = Decimal(armed["peak_profit"])
            if unrealized > peak_profit:
                _update_peak(trade, unrealized, trail_price)
                continue
            if unrealized <= peak_profit * (Decimal("1") - TRAIL_RETRACE_PCT):
                exit_price = trail_price
                exit_reason = "user_avg_trail"
            else:
                continue

        trade.close_price = exit_price
        trade.close_time = tick.timestamp
        trade.profit = _paper_profit(trade, exit_price)
        trade.paper_exit_reason = exit_reason
        if exit_reason == "user_avg_trail":
            trade.shadow_profit = await _shadow_projection(session, trade, tick)
        closed += 1

    if closed or any((t.recovery_plan or {}).get("trail") for t in open_papers):
        await session.flush()
        await session.commit()
    return closed


def _exit_for_tick(
    trade: Trade,
    tick: MarketTickSchema,
) -> tuple[Optional[Decimal], Optional[str]]:
    if trade.direction == Direction.buy:
        if trade.sl is not None and tick.bid <= trade.sl:
            return trade.sl, "sl"
        if trade.tp is not None and tick.bid >= trade.tp:
            return trade.tp, "tp"
    elif trade.direction == Direction.sell:
        if trade.sl is not None and tick.ask >= trade.sl:
            return trade.sl, "sl"
        if trade.tp is not None and tick.ask <= trade.tp:
            return trade.tp, "tp"
    return None, None


def _side_price(trade: Trade, tick: MarketTickSchema) -> Optional[Decimal]:
    if trade.direction == Direction.buy:
        return tick.bid
    if trade.direction == Direction.sell:
        return tick.ask
    return None


def _arm_trail(trade: Trade, unrealized: Decimal, price: Decimal) -> None:
    plan = dict(trade.recovery_plan or {})
    plan["trail"] = {"peak_profit": str(unrealized), "peak_price": str(price)}
    trade.recovery_plan = plan
    flag_modified(trade, "recovery_plan")


def _update_peak(trade: Trade, unrealized: Decimal, price: Decimal) -> None:
    plan = dict(trade.recovery_plan or {})
    trail = dict(plan.get("trail") or {})
    trail["peak_profit"] = str(unrealized)
    trail["peak_price"] = str(price)
    plan["trail"] = trail
    trade.recovery_plan = plan
    flag_modified(trade, "recovery_plan")


async def _shadow_projection(
    session: AsyncSession,
    trade: Trade,
    tick: MarketTickSchema,
) -> Optional[Decimal]:
    bar = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == Timeframe.H1,
            )
            .order_by(PriceBar.time.desc())
            .limit(1)
        )
    ).scalars().first()
    if bar is not None and trade.tp is not None and trade.sl is not None:
        if trade.direction == Direction.buy:
            if bar.high >= trade.tp:
                return _paper_profit(trade, trade.tp)
            if bar.low <= trade.sl:
                return _paper_profit(trade, trade.sl)
        elif trade.direction == Direction.sell:
            if bar.low <= trade.tp:
                return _paper_profit(trade, trade.tp)
            if bar.high >= trade.sl:
                return _paper_profit(trade, trade.sl)
    return _paper_profit(trade, _side_price(trade, tick) or tick.bid)


def _paper_profit(trade: Trade, exit_price: Decimal) -> Optional[Decimal]:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return None

    if trade.direction == Direction.buy:
        raw = (exit_price - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    else:
        raw = (trade.open_price - exit_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
