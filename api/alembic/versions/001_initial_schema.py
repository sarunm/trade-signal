"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_snapshots",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("balance", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("margin", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("free_margin", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("floating_pl", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.PrimaryKeyConstraint("timestamp"),
    )

    op.create_table(
        "price_bars",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.Enum("M5", "M15", "M30", "H1", "H4", "D", "W1", name="timeframe"), nullable=False),
        sa.Column("open", sa.Numeric(precision=12, scale=5), nullable=False),
        sa.Column("high", sa.Numeric(precision=12, scale=5), nullable=False),
        sa.Column("low", sa.Numeric(precision=12, scale=5), nullable=False),
        sa.Column("close", sa.Numeric(precision=12, scale=5), nullable=False),
        sa.Column("volume", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.PrimaryKeyConstraint("time", "symbol", "timeframe"),
    )

    op.execute("SELECT create_hypertable('price_bars', 'time', if_not_exists => TRUE)")

    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.Enum("buy", "sell", name="direction"), nullable=True),
        sa.Column("order_type", sa.Enum("market", "buy_limit", "sell_limit", "buy_stop", "sell_stop", "buy_stop_limit", "sell_stop_limit", name="ordertype"), nullable=True),
        sa.Column("order_state", sa.Enum("pending", "filled", "cancelled", "expired", name="orderstate"), nullable=True),
        sa.Column("pending_price", sa.Numeric(precision=12, scale=5), nullable=True),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_price", sa.Numeric(precision=12, scale=5), nullable=True),
        sa.Column("close_price", sa.Numeric(precision=12, scale=5), nullable=True),
        sa.Column("volume", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("tp", sa.Numeric(precision=12, scale=5), nullable=True),
        sa.Column("sl", sa.Numeric(precision=12, scale=5), nullable=True),
        sa.Column("profit", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("swap", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("commission", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("is_paper", sa.Boolean(), nullable=False),
        sa.Column("paper_mode", sa.Enum("mirror", "independent", name="papermode"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_ticket", "trades", ["ticket"])
    op.create_index("ix_trades_symbol", "trades", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_trades_symbol", table_name="trades")
    op.drop_index("ix_trades_ticket", table_name="trades")
    op.drop_table("trades")
    sa.Enum(name="papermode").drop(op.get_bind())
    sa.Enum(name="orderstate").drop(op.get_bind())
    sa.Enum(name="ordertype").drop(op.get_bind())
    sa.Enum(name="direction").drop(op.get_bind())
    op.drop_table("price_bars")
    sa.Enum(name="timeframe").drop(op.get_bind())
    op.drop_table("account_snapshots")
