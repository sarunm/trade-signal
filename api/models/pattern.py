import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    indicator_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite"),
    )
    timeframe: Mapped[str] = mapped_column(String(10), default="H1")
    win_rate: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    consecutive_stable_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="candidate", index=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperTraderRule(Base):
    __tablename__ = "paper_trader_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patterns.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    spawned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_count: Mapped[int] = mapped_column(Integer, default=0)
