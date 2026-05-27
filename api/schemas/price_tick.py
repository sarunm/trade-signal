from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict
from pydantic import BaseModel, field_validator
from services.symbol_normalizer import normalize_symbol


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

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return normalize_symbol(v)
