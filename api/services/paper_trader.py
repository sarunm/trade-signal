import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pattern import PaperTraderRule, Pattern
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services.indicators.common import (
    CYCLE_SPECS,
    MOMENTUM_SPECS,
    PATTERN_SPECS,
    SR_SPECS,
    TREND_SPECS,
    VOLATILITY_SPECS,
    VOLUME_SPECS,
    IndicatorSpec,
    _atr,
    _to_frame,
)
from services.scoring import (
    SignalQualityInputs,
    compute_score,
    score_to_lot,
)

logger = logging.getLogger(__name__)

PAPER_TRADER_ENABLED = os.getenv("PAPER_TRADER_ENABLED", "1") == "1"
CACHE_TTL_SECONDS = int(os.getenv("PAPER_TRADER_CACHE_TTL", 3600))
DEFAULT_TIMEFRAME = "H1"
BAR_LOOKBACK_LIMIT = 300
DEFAULT_VOLUME = Decimal("0.10")
XAUUSD_CONTRACT_SIZE = Decimal("100")
SL_ATR_MULTIPLIER = Decimal("1.5")
ATR_LENGTH = 14

SLOW_PATH_INTERVAL_SEC = int(os.getenv("PAPER_TRADER_SLOW_PATH_SEC", "15"))
FAST_PATH_GROUPS = {"momentum", "support_resistance"}
SLOW_PATH_GROUPS = {"trend", "volatility", "volume", "pattern", "cycle"}


_slow_path_state: dict[str, Optional[datetime]] = {"last_slow_at": None}
_slow_path_cache: dict[tuple[str, str], tuple[Optional[float], str, dict]] = {}


def reset_slow_path() -> None:
    global _slow_path_state, _slow_path_cache
    _slow_path_state = {"last_slow_at": None}
    _slow_path_cache = {}


def _slow_path_due(state: dict, now: datetime) -> bool:
    last = state.get("last_slow_at")
    if last is None:
        return True
    return (now - last).total_seconds() >= SLOW_PATH_INTERVAL_SEC


def _is_fast_slug(slug: str) -> bool:
    spec = ALL_SPECS.get(slug)
    return spec is not None and spec.group in FAST_PATH_GROUPS

ALL_SPECS: dict[str, IndicatorSpec] = {
    **TREND_SPECS,
    **MOMENTUM_SPECS,
    **VOLUME_SPECS,
    **VOLATILITY_SPECS,
    **SR_SPECS,
    **PATTERN_SPECS,
    **CYCLE_SPECS,
}


@dataclass
class _RuleSnapshot:
    rule_id: uuid.UUID
    pattern_id: uuid.UUID
    indicator_slugs: list[str]
    timeframe: str
    mode: str


_rule_cache: list[_RuleSnapshot] = []
_cache_refreshed_at: Optional[datetime] = None


def reset_cache() -> None:
    global _rule_cache, _cache_refreshed_at
    _rule_cache = []
    _cache_refreshed_at = None


def _cache_valid(now: datetime) -> bool:
    if _cache_refreshed_at is None:
        return False
    return (now - _cache_refreshed_at).total_seconds() < CACHE_TTL_SECONDS


async def load_active_rules(
    session: AsyncSession, now: Optional[datetime] = None
) -> list[_RuleSnapshot]:
    global _rule_cache, _cache_refreshed_at
    now = now or datetime.now(timezone.utc)
    if _cache_valid(now):
        return _rule_cache

    result = await session.execute(
        select(PaperTraderRule, Pattern)
        .join(Pattern, PaperTraderRule.pattern_id == Pattern.id)
        .where(PaperTraderRule.status == "active")
    )
    snapshots: list[_RuleSnapshot] = []
    for rule, pattern in result.all():
        snapshots.append(
            _RuleSnapshot(
                rule_id=rule.id,
                pattern_id=pattern.id,
                indicator_slugs=list(pattern.indicator_slugs),
                timeframe=pattern.timeframe or DEFAULT_TIMEFRAME,
                mode=rule.mode or "strict",
            )
        )
    _rule_cache = snapshots
    _cache_refreshed_at = now
    return _rule_cache


async def _fetch_bars(
    session: AsyncSession, symbol: str, timeframe: str, until: datetime
) -> list[PriceBar]:
    tf = Timeframe(timeframe)
    result = await session.execute(
        select(PriceBar)
        .where(
            PriceBar.symbol == symbol,
            PriceBar.timeframe == tf,
            PriceBar.time <= until,
        )
        .order_by(PriceBar.time.desc())
        .limit(BAR_LOOKBACK_LIMIT)
    )
    return list(reversed(result.scalars().all()))


def _compute(slug: str, bars: list[PriceBar]) -> tuple[Optional[float], str, dict]:
    spec = ALL_SPECS.get(slug)
    if spec is None or not bars:
        return None, "neutral", {"reason": "missing_spec_or_bars"}
    return spec.compute(_to_frame(bars))


def _build_indicator_cache(
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
    now: Optional[datetime] = None,
) -> dict[tuple[str, str], tuple[Optional[float], str, dict]]:
    now = now or datetime.now(timezone.utc)
    refresh_slow = _slow_path_due(_slow_path_state, now)
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]] = {}

    for rule in rules:
        bars = bars_by_tf.get(rule.timeframe) or bars_by_tf.get(DEFAULT_TIMEFRAME)
        if not bars:
            continue
        for slug in rule.indicator_slugs:
            key = (slug, rule.timeframe)
            if key in cache:
                continue
            if _is_fast_slug(slug):
                cache[key] = _compute(slug, bars)
            else:
                if refresh_slow or key not in _slow_path_cache:
                    _slow_path_cache[key] = _compute(slug, bars)
                cache[key] = _slow_path_cache[key]

    if refresh_slow:
        _slow_path_state["last_slow_at"] = now

    return cache


def _cached_direction(
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
    slug: str,
    timeframe: str,
) -> str:
    item = cache.get((slug, timeframe)) or cache.get((slug, DEFAULT_TIMEFRAME))
    if item is None:
        return "neutral"
    return item[1]


def _consensus_direction(directions: list[str]) -> Optional[Direction]:
    if not directions or any(d == "neutral" for d in directions):
        return None
    if all(d == "bullish" for d in directions):
        return Direction.buy
    if all(d == "bearish" for d in directions):
        return Direction.sell
    return None


def _compute_tp(
    direction: Direction, entry: Decimal, bars: list[PriceBar], atr: Optional[Decimal]
) -> Optional[Decimal]:
    spec = SR_SPECS.get("pivot_std")
    if spec is None or not bars:
        return None
    _, _, metadata = spec.compute(_to_frame(bars))
    levels = {k: Decimal(str(v)) for k, v in metadata.items() if k in ("r1", "r2", "s1", "s2")}
    if direction == Direction.buy:
        candidates = [v for k, v in levels.items() if k.startswith("r") and v > entry]
        if candidates:
            return min(candidates)
    else:
        candidates = [v for k, v in levels.items() if k.startswith("s") and v < entry]
        if candidates:
            return max(candidates)
    if atr is None:
        return None
    return entry + atr * 2 if direction == Direction.buy else entry - atr * 2


def _compute_atr(bars: list[PriceBar]) -> Optional[Decimal]:
    if len(bars) < ATR_LENGTH + 1:
        return None
    df = _to_frame(bars)
    series = _atr(df, ATR_LENGTH).dropna()
    if series.empty:
        return None
    return Decimal(str(float(series.iloc[-1])))


def _compute_sl(direction: Direction, entry: Decimal, atr: Decimal) -> Decimal:
    offset = atr * SL_ATR_MULTIPLIER
    return entry - offset if direction == Direction.buy else entry + offset


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)


def _first_momentum_slug(slugs: list[str]) -> Optional[str]:
    for slug in slugs:
        spec = ALL_SPECS.get(slug)
        if spec is not None and spec.group == "momentum":
            return slug
    return None


async def _has_open_paper_for_rule(
    session: AsyncSession, rule_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(Trade.id).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_(None),
            Trade.recovery_plan["paper_trader_rule_id"].as_string() == str(rule_id),
        )
    )
    return result.first() is not None


async def _open_papers_for_rules(
    session: AsyncSession, rule_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Trade]]:
    if not rule_ids:
        return {}
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_(None),
        )
    )
    trades = result.scalars().all()
    by_rule: dict[uuid.UUID, list[Trade]] = {}
    rule_id_strs = {str(rid) for rid in rule_ids}
    for t in trades:
        plan = t.recovery_plan or {}
        rid_str = plan.get("paper_trader_rule_id")
        if rid_str in rule_id_strs:
            by_rule.setdefault(uuid.UUID(rid_str), []).append(t)
    return by_rule


def _paper_profit(
    trade: Trade, exit_price: Decimal
) -> Optional[Decimal]:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return None
    if trade.direction == Direction.buy:
        raw = (exit_price - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    else:
        raw = (trade.open_price - exit_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _check_entries(
    session: AsyncSession,
    tick: MarketTickSchema,
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
    open_by_rule: dict[uuid.UUID, list[Trade]],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
) -> list[Trade]:
    opened: list[Trade] = []
    for rule in rules:
        existings = open_by_rule.get(rule.rule_id, [])
        latest = existings[-1] if existings else None
        if latest is not None:
            from services.basket_recovery import should_open_recovery
            rule_row = await session.get(PaperTraderRule, rule.rule_id)
            balance = (
                rule_row.virtual_balance_start if rule_row else Decimal("5000")
            )
            if not should_open_recovery(
                existing=latest,
                current_bid=tick.bid,
                current_ask=tick.ask,
                virtual_balance=balance,
                now=tick.timestamp,
                mode=rule.mode,
            ):
                continue
            # else: fall through and open a recovery trade alongside `latest`
        bars = bars_by_tf.get(rule.timeframe) or bars_by_tf.get(DEFAULT_TIMEFRAME)
        if not bars:
            continue
        directions = [
            _cached_direction(cache, slug, rule.timeframe)
            for slug in rule.indicator_slugs
        ]
        direction = _consensus_direction(directions)
        if direction is None:
            continue
        cached = [
            cache.get((slug, rule.timeframe)) or cache.get((slug, DEFAULT_TIMEFRAME))
            for slug in rule.indicator_slugs
        ]
        matched = sum(1 for c in cached if c is not None and c[1] != "neutral")
        if matched == 0:
            continue
        avg_strength = sum(
            min(abs(c[0] or 0.0) / 100.0, 1.0) for c in cached if c is not None
        ) / max(len(cached), 1)
        rule_row = await session.get(PaperTraderRule, rule.rule_id)
        winrate = (
            (rule_row.win_count / rule_row.total_trades)
            if rule_row and rule_row.total_trades
            else 0.0
        )
        score = compute_score(
            SignalQualityInputs(
                matched_count=matched,
                total_count=len(rule.indicator_slugs),
                avg_indicator_strength=avg_strength,
                rule_winrate=winrate,
            )
        )
        lot = score_to_lot(score)
        entry = (tick.ask if direction == Direction.buy else tick.bid)
        atr = _compute_atr(bars)
        if atr is None:
            continue
        sl = _compute_sl_for_mode(rule.mode, direction, entry, atr)
        tp_raw = _compute_tp(direction, entry, bars, atr)
        if tp_raw is None:
            continue
        tp = _quantize(tp_raw)
        trade = _build_paper_trade(
            tick, rule, direction, entry, tp, sl, volume=lot,
        )
        session.add(trade)
        await session.flush()
        if rule_row is not None:
            rule_row.total_trades += 1
        opened.append(trade)
        open_by_rule.setdefault(rule.rule_id, []).append(trade)
    return opened


def _compute_sl_for_mode(
    mode: str, direction: Direction, entry: Decimal, atr: Decimal
) -> Optional[Decimal]:
    """variant_A (strict) carries a hard SL = lot×ATR×2; basket modes have no SL."""
    if mode == "strict":
        return _quantize(_compute_sl(direction, entry, atr))
    return None


def _build_paper_trade(
    tick: MarketTickSchema,
    rule: _RuleSnapshot,
    direction: Direction,
    entry: Decimal,
    tp: Decimal,
    sl: Optional[Decimal],
    volume: Decimal,
) -> Trade:
    return Trade(
        ticket=int(tick.timestamp.timestamp() * 1000) % 1_000_000_000_000
        + abs(hash(rule.rule_id)) % 1000,
        symbol=tick.symbol,
        direction=direction,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=tick.timestamp,
        fill_time=tick.timestamp,
        open_price=entry,
        volume=volume,
        tp=tp,
        sl=sl,
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule.rule_id)},
        paper_trader_rule_id=rule.rule_id,
        account_id=tick.account_id,
    )


def _trail_should_close(
    trade: Trade,
    rule: _RuleSnapshot,
    cur_price: Decimal,
    bars: list[PriceBar],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
    atr: Decimal,
) -> bool:
    pivot_item = cache.get(("pivot_std", rule.timeframe)) or cache.get(
        ("pivot_std", DEFAULT_TIMEFRAME)
    )
    if pivot_item is None:
        spec = SR_SPECS.get("pivot_std")
        if spec is not None and bars:
            pivot_item = spec.compute(_to_frame(bars))
    if pivot_item is not None:
        _, _, meta = pivot_item
        if trade.direction == Direction.buy:
            res = [
                Decimal(str(meta[k]))
                for k in ("r1", "r2")
                if k in meta and Decimal(str(meta[k])) > cur_price
            ]
            if res and min(r - cur_price for r in res) < atr:
                return True
        else:
            sup = [
                Decimal(str(meta[k]))
                for k in ("s1", "s2")
                if k in meta and Decimal(str(meta[k])) < cur_price
            ]
            if sup and min(cur_price - s for s in sup) < atr:
                return True

    trend_dirs = [
        _cached_direction(cache, s, rule.timeframe)
        for s in rule.indicator_slugs
        if (ALL_SPECS.get(s) and ALL_SPECS[s].group == "trend")
    ]
    if trend_dirs:
        target = "bullish" if trade.direction == Direction.buy else "bearish"
        ratio = sum(1 for d in trend_dirs if d == target) / len(trend_dirs)
        if ratio < 0.5:
            return True

    pattern_dirs = [
        _cached_direction(cache, s, rule.timeframe)
        for s in rule.indicator_slugs
        if (ALL_SPECS.get(s) and ALL_SPECS[s].group == "pattern")
    ]
    reverse = "bearish" if trade.direction == Direction.buy else "bullish"
    if any(d == reverse for d in pattern_dirs):
        return True
    return False


async def _check_exits(
    session: AsyncSession,
    tick: MarketTickSchema,
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
    open_by_rule: dict[uuid.UUID, list[Trade]],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
) -> tuple[list[Trade], int]:
    rules_by_id = {r.rule_id: r for r in rules}
    closed: list[Trade] = []
    armed_count = 0

    for rule_id, trades in list(open_by_rule.items()):
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        rule_row = await session.get(PaperTraderRule, rule_id)
        for trade in list(trades):
            if trade.direction is None:
                continue

            exit_price: Optional[Decimal] = None
            reason: Optional[str] = None
            is_win = False

            # Trail mirror — arm at balance×pct, close on weakening signals
            if rule_row is not None and getattr(rule_row, "trail_enabled", False):
                plan = trade.recovery_plan or {}
                armed = plan.get("trail_armed", False)
                cur_price = tick.bid if trade.direction == Direction.buy else tick.ask

                if not armed:
                    pct = getattr(rule_row, "trail_arm_pct", None)
                    balance = getattr(rule_row, "virtual_balance_current", None)
                    if pct is not None and balance is not None:
                        threshold = Decimal(balance) * Decimal(pct)
                        unreal = _paper_profit(trade, cur_price)
                        if unreal is not None and unreal >= threshold:
                            new_plan = dict(plan)
                            new_plan["trail_armed"] = True
                            trade.recovery_plan = new_plan
                            armed = True
                            armed_count += 1

                if armed:
                    bars = bars_by_tf.get(rule.timeframe) or bars_by_tf.get(DEFAULT_TIMEFRAME)
                    atr = _compute_atr(bars) if bars else None
                    if atr and _trail_should_close(trade, rule, cur_price, bars, cache, atr):
                        exit_price = cur_price
                        reason = "trail_weaken"
                        profit = _paper_profit(trade, exit_price)
                        is_win = bool(profit and profit > 0)

            # SL/TP for strict only — basket modes have no SL
            if exit_price is None:
                if rule.mode == "strict":
                    if trade.direction == Direction.buy:
                        if trade.tp is not None and tick.bid >= trade.tp:
                            exit_price, reason, is_win = trade.tp, "tp", True
                        elif trade.sl is not None and tick.bid <= trade.sl:
                            exit_price, reason = trade.sl, "sl"
                    else:
                        if trade.tp is not None and tick.ask <= trade.tp:
                            exit_price, reason, is_win = trade.tp, "tp", True
                        elif trade.sl is not None and tick.ask >= trade.sl:
                            exit_price, reason = trade.sl, "sl"
                else:
                    if trade.tp is not None and trade.direction == Direction.buy and tick.bid >= trade.tp:
                        exit_price, reason, is_win = trade.tp, "tp", True
                    elif trade.tp is not None and trade.direction == Direction.sell and tick.ask <= trade.tp:
                        exit_price, reason, is_win = trade.tp, "tp", True

            if exit_price is None:
                momentum_slug = _first_momentum_slug(rule.indicator_slugs)
                if momentum_slug is not None:
                    mdir = _cached_direction(cache, momentum_slug, rule.timeframe)
                    flipped = (
                        (trade.direction == Direction.buy and mdir == "bearish")
                        or (trade.direction == Direction.sell and mdir == "bullish")
                    )
                    if flipped:
                        exit_price = tick.bid if trade.direction == Direction.buy else tick.ask
                        reason = "momentum_flip"
                        profit = _paper_profit(trade, exit_price)
                        is_win = bool(profit and profit > 0)

            if exit_price is None:
                continue

            trade.close_price = exit_price
            trade.close_time = tick.timestamp
            trade.profit = _paper_profit(trade, exit_price)
            trade.paper_exit_reason = reason
            if rule_row is not None and is_win:
                rule_row.win_count += 1
            closed.append(trade)
            trades.remove(trade)
        if not trades:
            del open_by_rule[rule_id]

    return closed, armed_count


def evals_for_broadcaster(
    rules: list[_RuleSnapshot],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
    open_by_rule: dict[uuid.UUID, list[Trade]],
) -> list:
    from services.signal_broadcaster import RuleEval, SignalEvalInputs

    out = []
    for rule in rules:
        matched: list[str] = []
        missing: list[str] = []
        for slug in rule.indicator_slugs:
            item = cache.get((slug, rule.timeframe)) or cache.get((slug, DEFAULT_TIMEFRAME))
            direction = item[1] if item else "neutral"
            if direction == "neutral":
                missing.append(slug)
            else:
                matched.append(slug)
        out.append(
            RuleEval(
                rule_id=rule.rule_id,
                inputs=SignalEvalInputs(
                    matched_count=len(matched),
                    total_count=len(rule.indicator_slugs),
                    has_open_paper=bool(open_by_rule.get(rule.rule_id)),
                ),
                matched_conditions=matched,
                missing_conditions=missing,
            )
        )
    return out


async def run_paper_trader(
    session: AsyncSession, tick: MarketTickSchema
) -> dict:
    if not PAPER_TRADER_ENABLED:
        return {"opened": 0, "closed": 0, "skipped": "disabled", "evals": []}

    rules = await load_active_rules(session, tick.timestamp)
    if not rules:
        return {"opened": 0, "closed": 0, "evals": []}

    timeframes = {rule.timeframe for rule in rules}
    bars_by_tf: dict[str, list[PriceBar]] = {}
    for tf in timeframes:
        bars_by_tf[tf] = await _fetch_bars(session, tick.symbol, tf, tick.timestamp)

    cache = _build_indicator_cache(rules, bars_by_tf, now=tick.timestamp)
    open_by_rule = await _open_papers_for_rules(session, [r.rule_id for r in rules])
    closed, armed_count = await _check_exits(session, tick, rules, bars_by_tf, open_by_rule, cache)
    opened = await _check_entries(session, tick, rules, bars_by_tf, open_by_rule, cache)

    if opened or closed or armed_count:
        await session.commit()

    return {
        "opened": len(opened),
        "closed": len(closed),
        "evals": evals_for_broadcaster(rules, cache, open_by_rule),
    }
