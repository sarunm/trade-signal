from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict
from pydantic import BaseModel


class OHLCVSchema(BaseModel):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[Decimal] = None


class AccountStateSchema(BaseModel):
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal


class PriceTickSchema(BaseModel):
    timestamp: datetime
    symbol: str
    account_id: Optional[int] = None
    account: AccountStateSchema
    bars: Dict[str, OHLCVSchema]
