import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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

    mode: Mapped[str] = mapped_column(String(20), default="strict")
    virtual_balance_start: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5000"))
    virtual_balance_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5000"))
    score_weights: Mapped[Optional[dict]] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    filters: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=list)
    shadow_of_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    gate_status: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=dict)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_stable_days_rule: Mapped[int] = mapped_column(
        "consecutive_stable_days", Integer, default=0
    )
    last_signal_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    trail_arm_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    trail_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    trail_strategy: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    trust_tier: Mapped[str] = mapped_column(String(20), default="experimental", server_default="experimental")
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    spawn_strategy: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    net_ev_per_trade: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    wilson_lower_95: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    baseline_delta: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
