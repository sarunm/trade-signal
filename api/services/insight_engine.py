import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pandas as pd

from models.trade import Trade, OrderState
from models.insight import Insight
from models.price_bar import PriceBar, Timeframe
from services.pattern_detector import detect_pin_bar, detect_engulfing

MIN_SAMPLE_SIZE = 10
MIN_CONFIDENCE = 0.6


async def run_insight_engine(session: AsyncSession) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.open_time.isnot(None),
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        )
    )
    trades = result.scalars().all()
    if not trades:
        return

    df = pd.DataFrame([{
        "open_time": t.open_time,
        "profit": float(t.profit),
    } for t in trades])

    df["is_win"] = df["profit"] > 0
    df["hour"] = pd.to_datetime(df["open_time"], utc=True).dt.hour

    await _compute_time_bias(session, df)
    await _compute_session_bias(session, df)
    await _compute_pattern_win_rate(session, trades)
    await session.commit()


async def _compute_time_bias(session: AsyncSession, df: pd.DataFrame) -> None:
    hourly = df.groupby("hour").agg(
        trades=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    loss_hours = hourly[
        (hourly["trades"] >= MIN_SAMPLE_SIZE) &
        (hourly["win_rate"] <= (1.0 - MIN_CONFIDENCE))
    ]
    if loss_hours.empty:
        return

    worst = loss_hours.loc[loss_hours["win_rate"].idxmin()]
    sample_size = int(worst["trades"])
    confidence = float(1.0 - worst["win_rate"])

    old = await session.execute(
        select(Insight).where(Insight.type == "time_bias", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    data = json.loads(hourly.to_json(orient="records"))
    session.add(Insight(
        type="time_bias",
        description=(
            f"{confidence:.0%} of your trades at {int(worst['hour']):02d}:00 UTC "
            f"result in a loss ({sample_size} trades)"
        ),
        confidence=confidence,
        sample_size=sample_size,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data=data,
    ))


def _assign_session(hour: int) -> str:
    if 7 <= hour < 16:
        return "London"
    if 13 <= hour < 22:
        return "NY"
    return "Asia"  # hours 0-6 and 22-23: post-NY pre-Asia overlap treated as Asia


async def _compute_session_bias(session: AsyncSession, df: pd.DataFrame) -> None:
    df = df.copy()
    df["session"] = df["hour"].apply(_assign_session)

    stats = df.groupby("session").agg(
        trades=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    qualified = stats[stats["trades"] >= MIN_SAMPLE_SIZE]
    if qualified.empty:
        return

    best = qualified.loc[qualified["win_rate"].idxmax()]
    if float(best["win_rate"]) < MIN_CONFIDENCE:
        return

    sample_size = int(best["trades"])
    confidence = float(best["win_rate"])

    old = await session.execute(
        select(Insight).where(Insight.type == "session_bias", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    data = json.loads(stats.to_json(orient="records"))
    session.add(Insight(
        type="session_bias",
        description=(
            f"Your win rate is highest during {best['session']} session "
            f"({confidence:.0%} from {sample_size} trades)"
        ),
        confidence=confidence,
        sample_size=sample_size,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data=data,
    ))


async def _compute_pattern_win_rate(session: AsyncSession, trades: list) -> None:
    records = []
    for trade in trades:
        hour_start = trade.open_time.replace(minute=0, second=0, microsecond=0)
        bar_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == Timeframe.H1,
                PriceBar.time >= hour_start,
                PriceBar.time < hour_start + timedelta(hours=1),
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        bar = bar_res.scalar_one_or_none()
        if bar is None:
            continue

        prev_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == Timeframe.H1,
                PriceBar.time >= hour_start - timedelta(hours=1),
                PriceBar.time < hour_start,
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        prev_bar = prev_res.scalar_one_or_none()

        bar_dict = {"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
        bars = []
        if prev_bar:
            bars.append({"open": prev_bar.open, "high": prev_bar.high,
                         "low": prev_bar.low, "close": prev_bar.close})
        bars.append(bar_dict)

        pin_dir = detect_pin_bar(bars)
        eng_dir = detect_engulfing(bars)
        if pin_dir:
            records.append({"pattern": "pin_bar", "direction": pin_dir,
                            "is_win": float(trade.profit) > 0})
        elif eng_dir:
            records.append({"pattern": "engulfing", "direction": eng_dir,
                            "is_win": float(trade.profit) > 0})

    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby(["pattern", "direction"]).agg(
        trades=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    old = await session.execute(
        select(Insight).where(Insight.type == "pattern_win_rate", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    for _, row in grouped.iterrows():
        if int(row["trades"]) < MIN_SAMPLE_SIZE or float(row["win_rate"]) < MIN_CONFIDENCE:
            continue
        session.add(Insight(
            type="pattern_win_rate",
            description=(
                f"Trades opened after a {row['direction']} "
                f"{row['pattern']} on H1 "
                f"have a {float(row['win_rate']):.0%} win rate ({int(row['trades'])} trades)"
            ),
            confidence=float(row["win_rate"]),
            sample_size=int(row["trades"]),
            discovered_at=datetime.now(timezone.utc),
            is_active=True,
            data={
                "pattern": row["pattern"],
                "direction": row["direction"],
                "timeframe": "H1",
                "win_rate": float(row["win_rate"]),
            },
        ))
