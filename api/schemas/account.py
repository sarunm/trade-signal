from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class AccountResponse(BaseModel):
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal
    timestamp: datetime
    account_id: Optional[int] = None

    model_config = {"from_attributes": True}


class AccountSnapshotResponse(BaseModel):
    timestamp: datetime
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal
    account_id: Optional[int] = None

    model_config = {"from_attributes": True}


class PnlHistoryItem(BaseModel):
    period: str
    profit: Decimal
    profit_pct: Optional[Decimal] = None
    trade_count: int


class PnlHistoryResponse(BaseModel):
    items: list[PnlHistoryItem]
    page: int
    page_size: int
    total_pages: int
    total_count: int


class HeaderSnapshotResponse(BaseModel):
    account_id: Optional[int] = None
    balance: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    floating_pl: Optional[Decimal] = None
    today_pnl_baht: Optional[Decimal] = None
    today_pnl_pct: Optional[Decimal] = None
    xau_price: Optional[Decimal] = None
    ea_online: bool = False
