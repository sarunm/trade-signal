from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.trader_profile import TraderProfileResponse
from services.trader_profile import build_trader_profile

router = APIRouter(prefix="/api", tags=["trader-profile"])


@router.get("/trader-profile", response_model=TraderProfileResponse)
async def get_trader_profile(session: AsyncSession = Depends(get_session)):
    return await build_trader_profile(session)
