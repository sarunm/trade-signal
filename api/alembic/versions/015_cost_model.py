"""cost model — cost_calibrations table

Revision ID: 015
Revises: 014
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cost_calibrations" not in inspector.get_table_names():
        op.create_table(
            "cost_calibrations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("learned_spread_pip", sa.Numeric(8, 2), nullable=False),
            sa.Column("learned_commission_per_lot_thb", sa.Numeric(10, 4), nullable=False),
            sa.Column("sample_count_spread", sa.Integer(), nullable=False),
            sa.Column("sample_count_commission", sa.Integer(), nullable=False),
            sa.Column(
                "calibrated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_cost_calibrations_calibrated",
            "cost_calibrations",
            ["calibrated_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cost_calibrations" in inspector.get_table_names():
        idx = {i["name"] for i in inspector.get_indexes("cost_calibrations")}
        if "ix_cost_calibrations_calibrated" in idx:
            op.drop_index("ix_cost_calibrations_calibrated", table_name="cost_calibrations")
        op.drop_table("cost_calibrations")
