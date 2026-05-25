from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
import models  # noqa: F401 — registers all ORM models with Base.metadata
from routers.trade_events import router as trade_events_router
from routers.price_tick import router as price_tick_router
from routers.market_tick import router as market_tick_router
from routers.insights import router as insights_router
from routers.alerts import router as alerts_router
from routers.account import router as account_router
from routers.trades import router as trades_router
from routers.fib_levels import router as fib_levels_router
from routers.trader_profile import router as trader_profile_router
from routers.trade_advisor import router as trade_advisor_router
from routers.indicator_signals import router as indicator_signals_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trade_events_router)
app.include_router(price_tick_router)
app.include_router(market_tick_router)
app.include_router(insights_router)
app.include_router(alerts_router)
app.include_router(account_router)
app.include_router(trades_router)
app.include_router(fib_levels_router)
app.include_router(trader_profile_router)
app.include_router(trade_advisor_router)
app.include_router(indicator_signals_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
