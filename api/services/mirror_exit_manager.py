import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services.indicators.common import _to_frame
from services.indicators.sr.pivot_std import compute_pivot_std as pivot_compute  # noqa: F401  (registers spec)
from services.indicators.common import SR_SPECS
from services.indicators.common import MOMENTUM_SPECS

HARD_STOP_LOSS_THB = Decimal(os.getenv("MIRROR_HARD_STOP_THB", "2500"))
XAUUSD_CONTRACT_SIZE = Decimal("100")
RSI_WEAKEN_BUY_THRESHOLD = Decimal("60")    # buy: RSI < 60 = weakening
RSI_WEAKEN_SELL_THRESHOLD = Decimal("40")   # sell: RSI > 40 = weakening
DAILY_LOOKBACK = 30
H1_LOOKBACK = 250


async def evaluate_mirror_exits(session: AsyncSession, tick: MarketTickSchema) -> int:
    rows = await session.execute(
        select(Trade).where(
            Trade.symbol == tick.symbol,
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.mirror,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
        )
    )
    open_mirrors = list(rows.scalars().all())
    if not open_mirrors:
        return 0

    daily_bars = await _fetch_bars(session, tick.symbol, Timeframe.D, DAILY_LOOKBACK)
    h1_bars = await _fetch_bars(session, tick.symbol, Timeframe.H1, H1_LOOKBACK)

    closed = 0
    for trade in open_mirrors:
        exit_price, reason = _exit_decision(trade, tick, daily_bars, h1_bars)
        if exit_price is None:
            continue
        trade.close_price = exit_price
        trade.close_time = tick.timestamp
        trade.profit = _floating_pnl(trade, exit_price)
        trade.paper_exit_reason = reason
        closed += 1

    if closed:
        await session.commit()
    return closed


def _exit_decision(
    trade: Trade,
    tick: MarketTickSchema,
    daily_bars: list[PriceBar],
    h1_bars: list[PriceBar],
) -> tuple[Optional[Decimal], Optional[str]]:
    if trade.direction is None or trade.open_price is None:
        return None, None

    pivot_levels = _pivot_levels(daily_bars)
    tp_level = _tp_level(trade.direction, tick, pivot_levels)
    if tp_level is not None and _momentum_weakening(trade.direction, h1_bars):
        return tp_level, "tp_pivot"

    if _momentum_flipped(trade.direction, h1_bars):
        cur = tick.bid if trade.direction == Direction.buy else tick.ask
        return cur, "momentum_flip"

    floating = _floating_pnl(trade, tick.bid if trade.direction == Direction.buy else tick.ask)
    if floating is not None and floating <= -HARD_STOP_LOSS_THB:
        cur = tick.bid if trade.direction == Direction.buy else tick.ask
        return cur, "hard_stop"

    return None, None


def _pivot_levels(daily_bars: list[PriceBar]) -> dict[str, Decimal]:
    spec = SR_SPECS.get("pivot_std")
    if spec is None or not daily_bars:
        return {}
    _, _, metadata = spec.compute(_to_frame(daily_bars))
    return {
        k: Decimal(str(v))
        for k, v in metadata.items()
        if k in ("r1", "r2", "s1", "s2") and v is not None
    }


def _tp_level(direction: Direction, tick: MarketTickSchema, levels: dict[str, Decimal]) -> Optional[Decimal]:
    if direction == Direction.buy:
        for key in ("r1", "r2"):
            level = levels.get(key)
            if level is not None and tick.bid >= level:
                return level
        return None
    for key in ("s1", "s2"):
        level = levels.get(key)
        if level is not None and tick.ask <= level:
            return level
    return None


def _momentum_weakening(direction: Direction, h1_bars: list[PriceBar]) -> bool:
    rsi = _rsi(h1_bars)
    if rsi is None:
        return False
    if direction == Direction.buy:
        return rsi < RSI_WEAKEN_BUY_THRESHOLD
    return rsi > RSI_WEAKEN_SELL_THRESHOLD


def _momentum_flipped(direction: Direction, h1_bars: list[PriceBar]) -> bool:
    spec = MOMENTUM_SPECS.get("rsi")
    if spec is None or not h1_bars:
        return False
    _, dir_label, _ = spec.compute(_to_frame(h1_bars))
    if direction == Direction.buy:
        return dir_label == "bearish"
    return dir_label == "bullish"


def _rsi(h1_bars: list[PriceBar]) -> Optional[Decimal]:
    spec = MOMENTUM_SPECS.get("rsi")
    if spec is None or not h1_bars:
        return None
    value, _, _ = spec.compute(_to_frame(h1_bars))
    return Decimal(str(value)) if value is not None else None


async def _fetch_bars(
    session: AsyncSession, symbol: str, tf: Timeframe, limit: int,
) -> list[PriceBar]:
    res = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == tf)
        .order_by(PriceBar.time.desc())
        .limit(limit)
    )
    return list(reversed(res.scalars().all()))


def _floating_pnl(trade: Trade, mark_price: Decimal) -> Optional[Decimal]:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return None
    if trade.direction == Direction.buy:
        raw = (mark_price - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    else:
        raw = (trade.open_price - mark_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
