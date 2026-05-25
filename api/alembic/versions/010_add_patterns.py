"""add patterns and paper_trader_rules

Revision ID: 010
Revises: 009
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "patterns" not in table_names:
        op.create_table(
            "patterns",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "indicator_slugs",
                postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
                nullable=False,
            ),
            sa.Column("timeframe", sa.String(10), nullable=False, server_default="H1"),
            sa.Column("win_rate", sa.Float(), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column(
                "consecutive_stable_days",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="candidate",
            ),
            sa.Column(
                "discovered_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("patterns")}
    if "ix_patterns_status" not in indexes:
        op.create_index("ix_patterns_status", "patterns", ["status"])

    if "paper_trader_rules" not in inspector.get_table_names():
        op.create_table(
            "paper_trader_rules",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "pattern_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("patterns.id"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "spawned_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "total_trades",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "win_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    rule_indexes = {idx["name"] for idx in inspector.get_indexes("paper_trader_rules")}
    if "ix_paper_trader_rules_status" not in rule_indexes:
        op.create_index("ix_paper_trader_rules_status", "paper_trader_rules", ["status"])
    if "ix_paper_trader_rules_pattern_id" not in rule_indexes:
        op.create_index(
            "ix_paper_trader_rules_pattern_id", "paper_trader_rules", ["pattern_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "paper_trader_rules" in table_names:
        rule_indexes = {idx["name"] for idx in inspector.get_indexes("paper_trader_rules")}
        if "ix_paper_trader_rules_pattern_id" in rule_indexes:
            op.drop_index("ix_paper_trader_rules_pattern_id", table_name="paper_trader_rules")
        if "ix_paper_trader_rules_status" in rule_indexes:
            op.drop_index("ix_paper_trader_rules_status", table_name="paper_trader_rules")
        op.drop_table("paper_trader_rules")

    if "patterns" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("patterns")}
        if "ix_patterns_status" in indexes:
            op.drop_index("ix_patterns_status", table_name="patterns")
        op.drop_table("patterns")
