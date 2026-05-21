from datetime import datetime
from decimal import Decimal
from typing import Dict
from pydantic import BaseModel, field_validator

RESISTANCE_KEYS = {f"R{i}" for i in range(1, 11)}
SUPPORT_KEYS = {f"S{i}" for i in range(1, 11)}


class FibLevelInSchema(BaseModel):
    symbol: str
    period: str
    prev_high: Decimal
    prev_low: Decimal
    prev_close: Decimal
    pp: Decimal
    resistance: Dict[str, float]
    support: Dict[str, float]
    computed_at: datetime

    @field_validator("resistance")
    @classmethod
    def validate_resistance(cls, value):
        if set(value.keys()) != RESISTANCE_KEYS:
            raise ValueError(f"resistance must contain exactly: {sorted(RESISTANCE_KEYS)}")
        return value

    @field_validator("support")
    @classmethod
    def validate_support(cls, value):
        if set(value.keys()) != SUPPORT_KEYS:
            raise ValueError(f"support must contain exactly: {sorted(SUPPORT_KEYS)}")
        return value


class FibLevelResponse(BaseModel):
    id: int
    symbol: str
    period: str
    prev_high: Decimal
    prev_low: Decimal
    prev_close: Decimal
    pp: Decimal
    resistance: Dict[str, float]
    support: Dict[str, float]
    computed_at: datetime

    model_config = {"from_attributes": True}
