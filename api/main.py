from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
import models  # noqa: F401 — registers all ORM models with Base.metadata
from routers.trade_events import router as trade_events_router
from routers.price_tick import router as price_tick_router
from routers.insights import router as insights_router
from routers.alerts import router as alerts_router
from routers.account import router as account_router
from routers.trades import router as trades_router


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
app.include_router(insights_router)
app.include_router(alerts_router)
app.include_router(account_router)
app.include_router(trades_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
