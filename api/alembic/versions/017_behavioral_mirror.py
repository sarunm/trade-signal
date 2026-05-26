"""behavioral mirror — trail_strategy on paper_trader_rules + shadow_profit on trades

Revision ID: 017
Revises: 016
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    rule_cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    if "trail_strategy" not in rule_cols:
        op.add_column(
            "paper_trader_rules",
            sa.Column("trail_strategy", sa.String(length=30), nullable=True),
        )
        op.execute(
            "UPDATE paper_trader_rules "
            "SET trail_strategy = 'user_avg_trail' "
            "WHERE status = 'active' AND trail_strategy IS NULL"
        )

    trade_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "shadow_profit" not in trade_cols:
        op.add_column(
            "trades",
            sa.Column("shadow_profit", sa.Numeric(12, 2), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    trade_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "shadow_profit" in trade_cols:
        op.drop_column("trades", "shadow_profit")

    rule_cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    if "trail_strategy" in rule_cols:
        op.drop_column("paper_trader_rules", "trail_strategy")
