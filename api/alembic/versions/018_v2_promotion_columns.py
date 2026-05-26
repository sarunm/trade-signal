"""v2 promotion columns — trust tier + cached stats

Revision ID: 018
Revises: 017
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    additions = [
        ("trust_tier", sa.String(20), "experimental"),
        ("is_baseline", sa.Boolean(), "false"),
        ("spawn_strategy", sa.String(40), None),
        ("net_ev_per_trade", sa.Numeric(10, 2), None),
        ("wilson_lower_95", sa.Numeric(5, 4), None),
        ("baseline_delta", sa.Numeric(5, 4), None),
    ]
    for name, col_type, default in additions:
        if name in cols:
            continue
        kwargs = {"nullable": True}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column("paper_trader_rules", sa.Column(name, col_type, **kwargs))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    for name in [
        "baseline_delta", "wilson_lower_95", "net_ev_per_trade",
        "spawn_strategy", "is_baseline", "trust_tier",
    ]:
        if name in cols:
            op.drop_column("paper_trader_rules", name)
