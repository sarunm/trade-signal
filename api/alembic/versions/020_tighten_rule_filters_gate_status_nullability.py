"""enforce NOT NULL on paper_trader_rules.filters and gate_status

Revision ID: 020
Revises: 019
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "UPDATE paper_trader_rules SET filters = '[]'::jsonb WHERE filters IS NULL"
    )
    op.execute(
        "UPDATE paper_trader_rules SET gate_status = '{}'::jsonb WHERE gate_status IS NULL"
    )

    op.alter_column(
        "paper_trader_rules", "filters",
        existing_type=postgresql.JSONB(),
        nullable=False,
        existing_server_default=sa.text("'[]'::jsonb"),
    )
    op.alter_column(
        "paper_trader_rules", "gate_status",
        existing_type=postgresql.JSONB(),
        nullable=False,
        existing_server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.alter_column(
        "paper_trader_rules", "filters",
        existing_type=postgresql.JSONB(),
        nullable=True,
        existing_server_default=sa.text("'[]'::jsonb"),
    )
    op.alter_column(
        "paper_trader_rules", "gate_status",
        existing_type=postgresql.JSONB(),
        nullable=True,
        existing_server_default=sa.text("'{}'::jsonb"),
    )
