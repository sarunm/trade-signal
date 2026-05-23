"""add trade indicator signals

Revision ID: 009
Revises: 008
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()
    if "trade_indicator_signals" not in table_names:
        op.create_table(
            "trade_indicator_signals",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id"), nullable=False),
            sa.Column("indicator_slug", sa.String(80), nullable=False),
            sa.Column("timeframe", sa.String(10), nullable=False),
            sa.Column("value", sa.Float(), nullable=True),
            sa.Column("direction", sa.String(20), nullable=True),
            sa.Column("matched", sa.Boolean(), nullable=False),
            sa.Column("metadata", postgresql.JSONB(), nullable=False),
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("trade_indicator_signals")}
    if "ix_trade_indicator_signals_trade_id" not in indexes:
        op.create_index("ix_trade_indicator_signals_trade_id", "trade_indicator_signals", ["trade_id"])
    if "ix_trade_indicator_signals_indicator_slug" not in indexes:
        op.create_index("ix_trade_indicator_signals_indicator_slug", "trade_indicator_signals", ["indicator_slug"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "trade_indicator_signals" not in inspector.get_table_names():
        return
    indexes = {idx["name"] for idx in inspector.get_indexes("trade_indicator_signals")}
    if "ix_trade_indicator_signals_indicator_slug" in indexes:
        op.drop_index("ix_trade_indicator_signals_indicator_slug", table_name="trade_indicator_signals")
    if "ix_trade_indicator_signals_trade_id" in indexes:
        op.drop_index("ix_trade_indicator_signals_trade_id", table_name="trade_indicator_signals")
    op.drop_table("trade_indicator_signals")
