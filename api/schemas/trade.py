from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class TradeResponse(BaseModel):
    id: UUID
    ticket: int
    symbol: str
    direction: Optional[str] = None
    order_type: Optional[str] = None
    order_state: Optional[str] = None
    is_paper: bool
    paper_mode: Optional[str] = None
    paper_exit_strategy: Optional[str] = None
    paper_exit_reason: Optional[str] = None
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    tp: Optional[Decimal] = None
    sl: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None

    model_config = {"from_attributes": True}
