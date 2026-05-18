from datetime import datetime
from decimal import Decimal
from typing import Dict, Literal
from pydantic import BaseModel, field_validator

LEVEL_RATIOS = {"0.000", "0.235", "0.382", "0.5", "0.618", "0.728", "1.000", "1.235", "1.328", "1.500", "1.618"}
EXT_RATIOS   = {"0.235", "0.382", "0.5", "0.618", "0.728", "1.000", "1.235", "1.328", "1.500", "1.618"}


class FibLevelInSchema(BaseModel):
    symbol: str
    timeframe: str
    swing_high: Decimal
    swing_low: Decimal
    direction: Literal["bullish", "bearish"]
    levels: Dict[str, float]
    extensions: Dict[str, float]
    computed_at: datetime

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, value):
        if set(value.keys()) != LEVEL_RATIOS:
            raise ValueError(f"levels must contain exactly: {sorted(LEVEL_RATIOS)}")
        return value

    @field_validator("extensions")
    @classmethod
    def validate_extensions(cls, value):
        if set(value.keys()) != EXT_RATIOS:
            raise ValueError(f"extensions must contain exactly: {sorted(EXT_RATIOS)}")
        return value


class FibLevelResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    swing_high: Decimal
    swing_low: Decimal
    direction: str
    levels: Dict[str, float]
    extensions: Dict[str, float]
    computed_at: datetime

    model_config = {"from_attributes": True}
