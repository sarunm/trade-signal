"""recovery foundation — ea_status + trades.paper_trader_rule_id

Revision ID: 014
Revises: 011
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "ea_status" not in inspector.get_table_names():
        op.create_table(
            "ea_status",
            sa.Column("account_id", sa.BigInteger(), primary_key=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.String(20), nullable=True),
            sa.Column("symbol", sa.String(20), nullable=True),
        )

    trade_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "paper_trader_rule_id" not in trade_cols:
        op.add_column(
            "trades",
            sa.Column(
                "paper_trader_rule_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

    trade_idx = {idx["name"] for idx in inspector.get_indexes("trades")}
    if "ix_trades_open_paper_rule" not in trade_idx:
        if bind.dialect.name == "postgresql":
            op.execute(
                "CREATE INDEX ix_trades_open_paper_rule "
                "ON trades(paper_trader_rule_id) "
                "WHERE close_time IS NULL AND is_paper = true;"
            )
        else:
            op.create_index(
                "ix_trades_open_paper_rule", "trades", ["paper_trader_rule_id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    trade_idx = {idx["name"] for idx in inspector.get_indexes("trades")}
    if "ix_trades_open_paper_rule" in trade_idx:
        op.drop_index("ix_trades_open_paper_rule", table_name="trades")

    trade_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "paper_trader_rule_id" in trade_cols:
        op.drop_column("trades", "paper_trader_rule_id")

    if "ea_status" in inspector.get_table_names():
        op.drop_table("ea_status")
