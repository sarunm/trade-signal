from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class FibLevel(Base):
    __tablename__ = "fib_levels"
    __table_args__ = (UniqueConstraint("symbol", "period", name="uq_fib_symbol_period"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)
    prev_high: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    prev_low: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    prev_close: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    pp: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    resistance: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    support: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
