"""add entry context columns

Revision ID: 005
Revises: 004
Create Date: 2026-05-19

"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("setup_pattern", sa.String(30), nullable=True))
    op.add_column("trades", sa.Column("trade_bias", sa.String(10), nullable=True))
    op.add_column("trades", sa.Column("near_fib_level", sa.String(10), nullable=True))
    op.add_column("trades", sa.Column("fib_distance_pts", sa.Numeric(8, 2), nullable=True))
    op.add_column("trades", sa.Column("entry_candle", sa.String(30), nullable=True))
    op.add_column("trades", sa.Column("entry_candle_tf", sa.String(5), nullable=True))
    op.add_column("trades", sa.Column("is_rescue", sa.Boolean(), nullable=True))
    op.add_column("trades", sa.Column("post_close_run_pts", sa.Numeric(8, 2), nullable=True))


def downgrade() -> None:
    for col in [
        "setup_pattern",
        "trade_bias",
        "near_fib_level",
        "fib_distance_pts",
        "entry_candle",
        "entry_candle_tf",
        "is_rescue",
        "post_close_run_pts",
    ]:
        op.drop_column("trades", col)
