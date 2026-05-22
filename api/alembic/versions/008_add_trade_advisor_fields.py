"""add trade advisor fields

Revision ID: 008
Revises: 007
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("entry_score", sa.Integer(), nullable=True))
    op.add_column("trades", sa.Column("entry_verdict", sa.String(20), nullable=True))
    op.add_column("trades", sa.Column("recovery_plan", postgresql.JSONB(), nullable=True))
    op.add_column("alerts", sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "trade_id")
    op.drop_column("trades", "recovery_plan")
    op.drop_column("trades", "entry_verdict")
    op.drop_column("trades", "entry_score")
