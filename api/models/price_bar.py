from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from database import Base


class Timeframe(str, enum.Enum):
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D = "D"
    W1 = "W1"


class PriceBar(Base):
    __tablename__ = "price_bars"

    time: Mapped[datetime] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
