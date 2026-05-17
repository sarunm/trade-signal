from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, engine
import models  # noqa: F401 — registers all ORM models with Base.metadata
from routers.trade_events import router as trade_events_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)
app.include_router(trade_events_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
