"""add account_id to trades and account_snapshots

Revision ID: 006
Revises: 005
Create Date: 2026-05-20

"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("account_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_trades_account_id", "trades", ["account_id"])
    op.add_column("account_snapshots", sa.Column("account_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_account_snapshots_account_id", "account_snapshots", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_account_snapshots_account_id", table_name="account_snapshots")
    op.drop_index("ix_trades_account_id", table_name="trades")
    op.drop_column("trades", "account_id")
    op.drop_column("account_snapshots", "account_id")
