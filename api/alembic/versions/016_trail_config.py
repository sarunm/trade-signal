"""trail config — trail_arm_pct + trail_enabled on paper_trader_rules

Revision ID: 016
Revises: 015
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    if "trail_arm_pct" not in cols:
        op.add_column(
            "paper_trader_rules",
            sa.Column("trail_arm_pct", sa.Numeric(5, 4), nullable=True),
        )
    if "trail_enabled" not in cols:
        op.add_column(
            "paper_trader_rules",
            sa.Column(
                "trail_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    if "trail_enabled" in cols:
        op.drop_column("paper_trader_rules", "trail_enabled")
    if "trail_arm_pct" in cols:
        op.drop_column("paper_trader_rules", "trail_arm_pct")
