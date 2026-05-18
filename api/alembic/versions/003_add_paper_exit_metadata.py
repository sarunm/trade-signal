"""add paper exit metadata

Revision ID: 003
Revises: 002
Create Date: 2026-05-18

"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("paper_exit_strategy", sa.String(length=80), nullable=True))
    op.add_column("trades", sa.Column("paper_exit_reason", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "paper_exit_reason")
    op.drop_column("trades", "paper_exit_strategy")
