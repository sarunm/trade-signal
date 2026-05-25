"""paper trade redesign — schema additions

Revision ID: 011
Revises: 010
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    rule_cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    additions = [
        ("mode", sa.String(20), "strict"),
        ("virtual_balance_start", sa.Numeric(12, 2), "5000"),
        ("virtual_balance_current", sa.Numeric(12, 2), "5000"),
        ("score_weights", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), None),
        ("filters", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), "[]"),
        ("shadow_of_rule_id", postgresql.UUID(as_uuid=True), None),
        ("gate_status", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), "{}"),
        ("promoted_at", sa.DateTime(timezone=True), None),
        ("consecutive_stable_days", sa.Integer(), "0"),
        ("last_signal_status", sa.String(20), None),
    ]
    for name, col_type, default in additions:
        if name in rule_cols:
            continue
        kwargs = {"nullable": True}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column("paper_trader_rules", sa.Column(name, col_type, **kwargs))

    if "paper_signals" not in inspector.get_table_names():
        op.create_table(
            "paper_signals",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("rule_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("paper_trader_rules.id"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("match_pct", sa.Numeric(5, 4), nullable=False),
            sa.Column("matched_conditions",
                      postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
                      nullable=False),
            sa.Column("missing_conditions",
                      postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
                      nullable=False),
            sa.Column("score", sa.Numeric(6, 2), nullable=True),
            sa.Column("suggested_lot", sa.Numeric(6, 2), nullable=True),
            sa.Column("emitted_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id", "emitted_at"),
        )
        op.create_index(
            "ix_paper_signals_rule_emitted",
            "paper_signals", ["rule_id", "emitted_at"],
        )
        if bind.dialect.name == "postgresql":
            op.execute(
                "SELECT create_hypertable('paper_signals', 'emitted_at', "
                "if_not_exists => TRUE);"
            )
            op.execute(
                "SELECT add_retention_policy('paper_signals', INTERVAL '30 days', "
                "if_not_exists => TRUE);"
            )

    if "score_calibrations" not in inspector.get_table_names():
        op.create_table(
            "score_calibrations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("score_tier", sa.String(10), nullable=False),
            sa.Column("expected_winrate", sa.Numeric(5, 4), nullable=False),
            sa.Column("actual_winrate", sa.Numeric(5, 4), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("calibrated_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.text("now()")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "score_calibrations" in inspector.get_table_names():
        op.drop_table("score_calibrations")

    if "paper_signals" in inspector.get_table_names():
        op.drop_index("ix_paper_signals_rule_emitted", table_name="paper_signals")
        op.drop_table("paper_signals")

    rule_cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    for name in [
        "last_signal_status", "consecutive_stable_days", "promoted_at",
        "gate_status", "shadow_of_rule_id", "filters", "score_weights",
        "virtual_balance_current", "virtual_balance_start", "mode",
    ]:
        if name in rule_cols:
            op.drop_column("paper_trader_rules", name)
