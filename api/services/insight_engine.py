import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import pandas as pd

from models.trade import Trade, OrderState, Direction
from models.insight import Insight
from models.price_bar import PriceBar, Timeframe
from models.account_snapshot import AccountSnapshot
from services.pattern_detector import detect_pin_bar, detect_engulfing

MIN_SAMPLE_SIZE = 10
MIN_ENTRY_SAMPLE = 5
MIN_CONFIDENCE = 0.6
# XAUUSD: 1 point = 0.01 price unit → 200 pts = 20,000 pips
LARGE_ADVERSE_THRESHOLD_PTS = 200.0
_ICT = timezone(timedelta(hours=7))


async def _get_current_account_id(session: AsyncSession):
    result = await session.execute(
        select(AccountSnapshot.account_id)
        .where(AccountSnapshot.account_id.isnot(None))
        .order_by(AccountSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def run_insight_engine(session: AsyncSession) -> None:
    account_id = await _get_current_account_id(session)

    query = select(Trade).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.open_time.isnot(None),
        Trade.close_time.isnot(None),
        Trade.profit.isnot(None),
    )
    if account_id is not None:
        query = query.where(Trade.account_id == account_id)

    result = await session.execute(query)
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
    await _compute_early_exit_rate(session, trades)
    await _compute_large_adverse_recovery(session, trades)
    tagged = [t for t in trades if t.setup_pattern is not None]
    await _compute_setup_win_rate(session, tagged)
    await _compute_fib_proximity_win_rate(session, tagged)
    await _compute_rescue_outcome(session, trades)
    await _compute_best_combo(session, tagged)
    await _compute_post_close_run(session, trades)
    await session.commit()

    from services.alert_manager import check_insight_alerts
    await check_insight_alerts(session, tagged, trades)


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


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        if hour_start.tzinfo is None:
            hour_start = hour_start.replace(tzinfo=timezone.utc)
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

    deactivated = False

    for _, row in grouped.iterrows():
        if int(row["trades"]) < MIN_SAMPLE_SIZE or float(row["win_rate"]) < MIN_CONFIDENCE:
            continue
        if not deactivated:
            old = await session.execute(
                select(Insight).where(Insight.type == "pattern_win_rate", Insight.is_active == True)
            )
            for ins in old.scalars().all():
                ins.is_active = False
            deactivated = True
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


async def _compute_early_exit_rate(session: AsyncSession, trades: list) -> None:
    tickets = [t.ticket for t in trades]
    paper_res = await session.execute(
        select(Trade).where(
            Trade.is_paper == True,
            Trade.ticket.in_(tickets),
            Trade.order_state == OrderState.filled,
            Trade.profit.isnot(None),
        )
    )
    paper_by_ticket = {t.ticket: t for t in paper_res.scalars().all()}

    winning_real = [t for t in trades if float(t.profit) > 0]
    if len(winning_real) < MIN_SAMPLE_SIZE:
        return

    early_exits = [
        t for t in winning_real
        if t.ticket in paper_by_ticket
        and float(paper_by_ticket[t.ticket].profit) > float(t.profit)
    ]
    rate = len(early_exits) / len(winning_real)
    if rate < MIN_CONFIDENCE:
        return

    avg_left = sum(
        float(paper_by_ticket[t.ticket].profit) - float(t.profit)
        for t in early_exits
    ) / len(early_exits)

    old = await session.execute(
        select(Insight).where(Insight.type == "early_exit_rate", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="early_exit_rate",
        description=(
            f"{rate:.0%} ของเทรดที่ชนะถูกปิดก่อน Paper TP "
            f"เฉลี่ยเหลือทิ้ง ฿{avg_left:.0f} ต่อเทรด ({len(winning_real)} เทรด)"
        ),
        confidence=rate,
        sample_size=len(winning_real),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            "early_exit_count": len(early_exits),
            "winning_trades": len(winning_real),
            "avg_profit_left": avg_left,
        },
    ))


async def _compute_large_adverse_recovery(session: AsyncSession, trades: list) -> None:
    records = []
    for trade in trades:
        if trade.open_price is None or trade.open_time is None or trade.close_time is None:
            continue

        open_p = float(trade.open_price)
        if trade.direction == Direction.buy:
            bar_res = await session.execute(
                select(func.min(PriceBar.low)).where(
                    PriceBar.symbol == trade.symbol,
                    PriceBar.timeframe == Timeframe.H1,
                    PriceBar.time >= trade.open_time,
                    PriceBar.time <= trade.close_time,
                )
            )
            extreme = bar_res.scalar()
            if extreme is None:
                continue
            adverse = open_p - float(extreme)
        else:
            bar_res = await session.execute(
                select(func.max(PriceBar.high)).where(
                    PriceBar.symbol == trade.symbol,
                    PriceBar.timeframe == Timeframe.H1,
                    PriceBar.time >= trade.open_time,
                    PriceBar.time <= trade.close_time,
                )
            )
            extreme = bar_res.scalar()
            if extreme is None:
                continue
            adverse = float(extreme) - open_p

        if adverse >= LARGE_ADVERSE_THRESHOLD_PTS:
            records.append({"is_win": float(trade.profit) > 0, "adverse": adverse})

    if len(records) < MIN_SAMPLE_SIZE:
        return

    total = len(records)
    wins = sum(1 for r in records if r["is_win"])
    win_rate = wins / total
    avg_adverse = sum(r["adverse"] for r in records) / total

    old = await session.execute(
        select(Insight).where(Insight.type == "large_adverse_recovery", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    outcome = "ส่วนใหญ่รอดได้" if win_rate >= 0.5 else "ส่วนใหญ่ขาดทุน"
    session.add(Insight(
        type="large_adverse_recovery",
        description=(
            f"เมื่อราคาวิ่งมา >{LARGE_ADVERSE_THRESHOLD_PTS:.0f} pts ต้านออเดอร์ "
            f"คุณชนะ {win_rate:.0%} ({total} เทรด) — {outcome}"
        ),
        confidence=win_rate if win_rate >= 0.5 else 1.0 - win_rate,
        sample_size=total,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            "threshold_pts": LARGE_ADVERSE_THRESHOLD_PTS,
            "sample": total,
            "wins": wins,
            "win_rate": win_rate,
            "avg_adverse_pts": avg_adverse,
        },
    ))


async def _compute_setup_win_rate(session: AsyncSession, tagged: list) -> None:
    if not tagged:
        return

    records = [
        {
            "setup_pattern": t.setup_pattern,
            "trade_bias": t.trade_bias,
            "near_fib_level": t.near_fib_level,
            "is_win": float(t.profit) > 0,
            "profit": float(t.profit),
        }
        for t in tagged
        if t.profit is not None
    ]
    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby(["setup_pattern", "trade_bias", "near_fib_level"]).agg(
        count=("is_win", "count"),
        win_rate=("is_win", "mean"),
        avg_profit=("profit", "mean"),
    ).reset_index()

    qualified = grouped[grouped["count"] >= MIN_ENTRY_SAMPLE]
    if qualified.empty:
        return

    old = await session.execute(
        select(Insight).where(Insight.type == "setup_win_rate", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    for _, row in qualified.iterrows():
        session.add(Insight(
            type="setup_win_rate",
            description=(
                f"{row['setup_pattern']} + {row['trade_bias'] or 'any'}"
                f" + near {row['near_fib_level'] or 'any'}"
                f" -> ชนะ {float(row['win_rate']):.0%} ({int(row['count'])} เทรด)"
                f" เฉลี่ย +฿{float(row['avg_profit']):.0f}"
            ),
            confidence=float(row["win_rate"]),
            sample_size=int(row["count"]),
            discovered_at=datetime.now(timezone.utc),
            is_active=True,
            data={
                "pattern": row["setup_pattern"],
                "bias": row["trade_bias"],
                "fib_level": row["near_fib_level"],
                "win_rate": float(row["win_rate"]),
                "avg_profit": float(row["avg_profit"]),
                "trades": int(row["count"]),
            },
        ))


async def _compute_fib_proximity_win_rate(session: AsyncSession, tagged: list) -> None:
    records = [
        {
            "bucket": (
                "close" if float(t.fib_distance_pts) < 5
                else "medium" if float(t.fib_distance_pts) < 15
                else "far"
            ),
            "is_win": float(t.profit) > 0,
        }
        for t in tagged
        if t.fib_distance_pts is not None and t.profit is not None
    ]
    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby("bucket").agg(
        count=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    qualified = grouped[grouped["count"] >= MIN_ENTRY_SAMPLE]
    if len(qualified) < 2:
        return

    rates = qualified["win_rate"].values
    spread = float(max(rates) - min(rates))
    if spread < 0.20:
        return

    bucket_stats = {
        row["bucket"]: (float(row["win_rate"]), int(row["count"]))
        for _, row in grouped.iterrows()
    }

    def fmt(name):
        if name not in bucket_stats:
            return "-"
        return f"{bucket_stats[name][0]:.0%}"

    total = int(grouped["count"].sum())

    old = await session.execute(
        select(Insight).where(
            Insight.type == "fib_proximity_win_rate",
            Insight.is_active == True,
        )
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="fib_proximity_win_rate",
        description=(
            f"Entry ห่าง Fib < 5 pts -> {fmt('close')} | "
            f"5-15 pts -> {fmt('medium')} | "
            f">15 pts -> {fmt('far')} ({total} เทรด)"
        ),
        confidence=spread,
        sample_size=total,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            bucket: {"win_rate": stats[0], "count": stats[1]}
            for bucket, stats in bucket_stats.items()
        },
    ))


async def _compute_rescue_outcome(session: AsyncSession, trades: list) -> None:
    trades_with_data = [
        t for t in trades
        if t.profit is not None and t.is_rescue is not None
    ]
    rescue = [t for t in trades_with_data if t.is_rescue]
    initial = [t for t in trades_with_data if not t.is_rescue]

    if len(rescue) < MIN_ENTRY_SAMPLE or len(initial) < MIN_ENTRY_SAMPLE:
        return

    rescue_wr = sum(1 for t in rescue if float(t.profit) > 0) / len(rescue)
    initial_wr = sum(1 for t in initial if float(t.profit) > 0) / len(initial)

    old = await session.execute(
        select(Insight).where(
            Insight.type == "rescue_outcome",
            Insight.is_active == True,
        )
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="rescue_outcome",
        description=(
            f"ไม้แก้: ชนะ {rescue_wr:.0%} ({len(rescue)} เทรด) "
            f"vs ไม้เดิม: ชนะ {initial_wr:.0%} ({len(initial)} เทรด)"
        ),
        confidence=max(rescue_wr, initial_wr),
        sample_size=len(trades_with_data),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            "rescue_win_rate": rescue_wr,
            "initial_win_rate": initial_wr,
            "rescue_count": len(rescue),
            "initial_count": len(initial),
        },
    ))


async def _compute_best_combo(session: AsyncSession, tagged: list) -> None:
    records = [
        {
            "session": _assign_session(_as_utc(t.open_time).astimezone(_ICT).hour),
            "setup_pattern": t.setup_pattern,
            "trade_bias": t.trade_bias,
            "near_fib_level": t.near_fib_level,
            "is_win": float(t.profit) > 0,
            "profit": float(t.profit),
        }
        for t in tagged
        if t.profit is not None and t.open_time is not None
    ]
    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby(
        ["session", "setup_pattern", "trade_bias", "near_fib_level"]
    ).agg(
        count=("is_win", "count"),
        win_rate=("is_win", "mean"),
        avg_profit=("profit", "mean"),
    ).reset_index()

    qualified = (
        grouped[grouped["count"] >= MIN_ENTRY_SAMPLE]
        .sort_values("win_rate", ascending=False)
        .head(3)
    )
    if qualified.empty:
        return

    top = qualified.iloc[0]

    old = await session.execute(
        select(Insight).where(
            Insight.type == "best_combo",
            Insight.is_active == True,
        )
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="best_combo",
        description=(
            f"Best: {top['session']} + {top['setup_pattern']}"
            f" + {top['trade_bias'] or 'any'}"
            f" + near {top['near_fib_level'] or 'any'}"
            f" -> {float(top['win_rate']):.0%} win rate ({int(top['count'])} เทรด)"
        ),
        confidence=float(top["win_rate"]),
        sample_size=int(qualified["count"].sum()),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            "combos": [
                {
                    "session": row["session"],
                    "pattern": row["setup_pattern"],
                    "bias": row["trade_bias"],
                    "fib_level": row["near_fib_level"],
                    "win_rate": float(row["win_rate"]),
                    "avg_profit": float(row["avg_profit"]),
                    "count": int(row["count"]),
                }
                for _, row in qualified.iterrows()
            ]
        },
    ))


async def _compute_post_close_run(session: AsyncSession, trades: list) -> None:
    to_backfill = [
        t for t in trades
        if t.close_price is not None
        and t.close_time is not None
        and t.post_close_run_pts is None
    ]
    for trade in to_backfill:
        close_price = float(trade.close_price)
        close_time = _as_utc(trade.close_time)
        end_time = close_time + timedelta(hours=8)

        if trade.direction == Direction.buy:
            bar_res = await session.execute(
                select(func.max(PriceBar.high)).where(
                    PriceBar.symbol == trade.symbol,
                    PriceBar.timeframe == Timeframe.H1,
                    PriceBar.time >= close_time,
                    PriceBar.time <= end_time,
                )
            )
            extreme = bar_res.scalar()
            if extreme is not None:
                run = float(extreme) - close_price
                if run > 0:
                    trade.post_close_run_pts = round(run, 2)
        else:
            bar_res = await session.execute(
                select(func.min(PriceBar.low)).where(
                    PriceBar.symbol == trade.symbol,
                    PriceBar.timeframe == Timeframe.H1,
                    PriceBar.time >= close_time,
                    PriceBar.time <= end_time,
                )
            )
            extreme = bar_res.scalar()
            if extreme is not None:
                run = close_price - float(extreme)
                if run > 0:
                    trade.post_close_run_pts = round(run, 2)

    winning_tagged = [
        t for t in trades
        if t.setup_pattern is not None
        and t.profit is not None
        and float(t.profit) > 0
        and t.post_close_run_pts is not None
    ]
    if not winning_tagged:
        return

    df = pd.DataFrame([
        {"setup_pattern": t.setup_pattern, "run_pts": float(t.post_close_run_pts)}
        for t in winning_tagged
    ])
    grouped = df.groupby("setup_pattern").agg(
        count=("run_pts", "count"),
        avg_run=("run_pts", "mean"),
    ).reset_index()

    qualified = grouped[grouped["count"] >= 3]
    if qualified.empty:
        return

    old = await session.execute(
        select(Insight).where(
            Insight.type == "post_close_run",
            Insight.is_active == True,
        )
    )
    for ins in old.scalars().all():
        ins.is_active = False

    by_pattern = {
        row["setup_pattern"]: float(row["avg_run"])
        for _, row in qualified.iterrows()
    }
    parts = " | ".join(f"{p} -> {r:.0f} pts" for p, r in by_pattern.items())
    overall_avg = float(df["run_pts"].mean())

    session.add(Insight(
        type="post_close_run",
        description=f"ราคาวิ่งต่อหลังปิด: {parts}",
        confidence=1.0,
        sample_size=len(winning_tagged),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={"by_pattern": by_pattern, "overall_avg": overall_avg},
    ))
