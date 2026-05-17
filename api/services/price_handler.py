from sqlalchemy.ext.asyncio import AsyncSession

from models.price_bar import PriceBar, Timeframe
from models.account_snapshot import AccountSnapshot
from schemas.price_tick import PriceTickSchema

VALID_TIMEFRAMES = {tf.value for tf in Timeframe}


async def save_price_tick(session: AsyncSession, tick: PriceTickSchema) -> None:
    snapshot = AccountSnapshot(
        timestamp=tick.timestamp,
        equity=tick.account.equity,
        balance=tick.account.balance,
        margin=tick.account.margin,
        free_margin=tick.account.free_margin,
        floating_pl=tick.account.floating_pl,
    )
    session.add(snapshot)

    for tf_str, ohlcv in tick.bars.items():
        if tf_str not in VALID_TIMEFRAMES:
            continue
        bar = PriceBar(
            time=tick.timestamp,
            symbol=tick.symbol,
            timeframe=Timeframe(tf_str),
            open=ohlcv.open,
            high=ohlcv.high,
            low=ohlcv.low,
            close=ohlcv.close,
            volume=ohlcv.volume,
        )
        session.add(bar)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
