from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.alert import Alert
from schemas.alert import AlertResponse

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    unacknowledged_only: bool = False,
    types: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Alert).order_by(Alert.sent_at.desc())
    if unacknowledged_only:
        query = query.where(Alert.acknowledged == False)
    if types:
        type_list = [t.strip() for t in types.split(",")]
        query = query.where(Alert.type.in_(type_list))
    result = await session.execute(query)
    return result.scalars().all()


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await session.commit()
    await session.refresh(alert)
    return alert


@router.post("/alerts/acknowledge-all")
async def acknowledge_all_alerts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Alert).where(Alert.acknowledged == False))
    alerts = result.scalars().all()
    count = len(alerts)
    for alert in alerts:
        alert.acknowledged = True
    await session.commit()
    return {"acknowledged": count}
