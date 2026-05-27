import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import SessionLocal, engine
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
from routers.patterns import router as patterns_router
from routers.price_bars import router as price_bars_router
from routers.ea_status import router as ea_status_router
from routers.paper_signals import router as paper_signals_router
from routers.ml import router as ml_router
from services.adaptive_tuner import run_adaptive_tuner
from services.baseline_runner import BASELINE_ENABLED, open_baseline_trade
from services.cost_model import refresh_cost_cache
from services.pattern_discovery import run_pattern_discovery
from services.promotion_gate import evaluate_all_active_rules

logger = logging.getLogger(__name__)

PATTERN_DISCOVERY_ENABLED = os.getenv("PATTERN_DISCOVERY_ENABLED", "1") == "1"
COST_REFRESH_ENABLED = os.getenv("COST_REFRESH_ENABLED", "1") == "1"
COST_REFRESH_INTERVAL_MIN = int(os.getenv("COST_REFRESH_INTERVAL_MIN", 60))
BASELINE_ACCOUNT_ID = int(os.getenv("BASELINE_ACCOUNT_ID", "0"))
PROMOTION_GATE_ENABLED = os.getenv("PROMOTION_GATE_ENABLED", "1") == "1"
ADAPTIVE_ENABLED = os.getenv("ADAPTIVE_ENABLED", "1") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler: AsyncIOScheduler | None = None
    if PATTERN_DISCOVERY_ENABLED:
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            _safe_run_pattern_discovery,
            "cron",
            hour=0,
            minute=0,
            id="pattern_discovery_daily",
            replace_existing=True,
        )
        scheduler.start()
    if COST_REFRESH_ENABLED:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.start()
        scheduler.add_job(
            _safe_refresh_cost,
            "interval",
            minutes=COST_REFRESH_INTERVAL_MIN,
            id="cost_refresh_hourly",
            replace_existing=True,
        )
    if BASELINE_ENABLED:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.start()
        for jid, hour in (("baseline_london", 7), ("baseline_ny", 13), ("baseline_asia", 22)):
            scheduler.add_job(
                _safe_open_baseline,
                "cron",
                hour=hour,
                minute=0,
                id=jid,
                replace_existing=True,
            )
    if PROMOTION_GATE_ENABLED:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.start()
        scheduler.add_job(
            _safe_run_promotion_gate,
            "cron",
            hour=0,
            minute=30,
            id="promotion_gate_daily",
            replace_existing=True,
        )
    if ADAPTIVE_ENABLED:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.start()
        scheduler.add_job(
            _safe_run_adaptive_tuner,
            "cron",
            hour=0,
            minute=45,
            id="adaptive_tuner_daily",
            replace_existing=True,
        )
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await engine.dispose()


async def _safe_run_pattern_discovery() -> None:
    try:
        await run_pattern_discovery()
    except Exception:
        logger.exception("pattern discovery cron failed")


async def _safe_refresh_cost() -> None:
    try:
        await refresh_cost_cache()
    except Exception:
        logger.exception("cost refresh cron failed")


async def _safe_open_baseline() -> None:
    try:
        async with SessionLocal() as session:
            await open_baseline_trade(session, account_id=BASELINE_ACCOUNT_ID or None)
    except Exception:
        logger.exception("baseline runner cron failed")


async def _safe_run_promotion_gate() -> None:
    try:
        results = await evaluate_all_active_rules()
        logger.info("promotion gate cron evaluated %d rules", len(results))
    except Exception:
        logger.exception("promotion gate cron failed")


async def _safe_run_adaptive_tuner() -> None:
    try:
        async with SessionLocal() as session:
            await run_adaptive_tuner(session)
    except Exception:
        logger.exception("adaptive tuner cron failed")


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
app.include_router(patterns_router)
app.include_router(price_bars_router)
app.include_router(ea_status_router)
app.include_router(paper_signals_router)
app.include_router(ml_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
