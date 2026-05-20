import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Boolean, Numeric, BigInteger, Enum as SAEnum, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
import enum

from database import Base


class Direction(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class OrderType(str, enum.Enum):
    market = "market"
    buy_limit = "buy_limit"
    sell_limit = "sell_limit"
    buy_stop = "buy_stop"
    sell_stop = "sell_stop"
    buy_stop_limit = "buy_stop_limit"
    sell_stop_limit = "sell_stop_limit"


class OrderState(str, enum.Enum):
    pending = "pending"
    filled = "filled"
    cancelled = "cancelled"
    expired = "expired"


class PaperMode(str, enum.Enum):
    mirror = "mirror"
    independent = "independent"


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket: Mapped[int] = mapped_column(BigInteger, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[Optional[Direction]] = mapped_column(SAEnum(Direction), nullable=True)
    order_type: Mapped[Optional[OrderType]] = mapped_column(SAEnum(OrderType), nullable=True)
    order_state: Mapped[Optional[OrderState]] = mapped_column(SAEnum(OrderState), nullable=True)
    pending_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 5), nullable=True)
    open_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fill_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    close_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 5), nullable=True)
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 5), nullable=True)
    volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    tp: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 5), nullable=True)
    sl: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 5), nullable=True)
    profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    swap: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    commission: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=False)
    paper_mode: Mapped[Optional[PaperMode]] = mapped_column(SAEnum(PaperMode), nullable=True)
    paper_exit_strategy: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    paper_exit_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    setup_pattern: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    trade_bias: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    near_fib_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    fib_distance_pts: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    entry_candle: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    entry_candle_tf: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    is_rescue: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    post_close_run_pts: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
