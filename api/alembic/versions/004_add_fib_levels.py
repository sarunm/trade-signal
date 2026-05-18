"""add fib levels table

Revision ID: 004
Revises: 003
Create Date: 2026-05-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fib_levels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("timeframe", sa.String(), nullable=False),
        sa.Column("swing_high", sa.Numeric(12, 5), nullable=False),
        sa.Column("swing_low", sa.Numeric(12, 5), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("levels", postgresql.JSONB(), nullable=False),
        sa.Column("extensions", postgresql.JSONB(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timeframe", name="uq_fib_symbol_tf"),
    )


def downgrade() -> None:
    op.drop_table("fib_levels")
