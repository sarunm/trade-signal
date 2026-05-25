import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PaperSignal(Base):
    __tablename__ = "paper_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_trader_rules.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    match_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    matched_conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite")
    )
    missing_conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite")
    )
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    suggested_lot: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        default=lambda: datetime.now(timezone.utc),
    )
