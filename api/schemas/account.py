from datetime import datetime
from datetime import date
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


class DailyPLResponse(BaseModel):
    date: date
    profit: Decimal
    profit_pct: Optional[Decimal] = None
    base_balance: Optional[Decimal] = None
    trade_count: int
