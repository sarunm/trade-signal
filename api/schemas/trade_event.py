from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator
from models.trade import Direction, OrderType, OrderState
from services.symbol_normalizer import normalize_symbol


class TradeEventSchema(BaseModel):
    transaction_type: str
    ticket: int
    pending_ticket: Optional[int] = None
    symbol: str

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return normalize_symbol(v)
    account_id: Optional[int] = None
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
