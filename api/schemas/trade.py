from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


VALID_SETUP_PATTERNS = {
    "double_top",
    "double_bottom",
    "triple_top",
    "triple_bottom",
    "rounded_top",
    "rounded_bottom",
    "price_cluster",
    "other",
}


class TradeTagSchema(BaseModel):
    setup_pattern: Optional[Literal[
        "double_top",
        "double_bottom",
        "triple_top",
        "triple_bottom",
        "rounded_top",
        "rounded_bottom",
        "price_cluster",
        "other",
    ]] = None
    trade_bias: Optional[Literal["bullish", "bearish"]] = None


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
    setup_pattern: Optional[str] = None
    trade_bias: Optional[str] = None
    near_fib_level: Optional[str] = None
    fib_distance_pts: Optional[Decimal] = None
    entry_candle: Optional[str] = None
    entry_candle_tf: Optional[str] = None
    is_rescue: Optional[bool] = None
    post_close_run_pts: Optional[Decimal] = None

    model_config = {"from_attributes": True}
