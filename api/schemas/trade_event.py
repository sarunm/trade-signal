from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from models.trade import Direction, OrderType, OrderState


class TradeEventSchema(BaseModel):
    transaction_type: str
    ticket: int
    symbol: str
    direction: Optional[Direction] = None
    order_type: Optional[OrderType] = None
    order_state: Optional[OrderState] = None
    pending_price: Optional[Decimal] = None
    open_time: Optional[datetime] = None
    fill_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    tp: Optional[Decimal] = None
    sl: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    swap: Optional[Decimal] = None
    commission: Optional[Decimal] = None

    model_config = {"from_attributes": True}
