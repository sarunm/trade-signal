"""create ml_pattern_scores

Revision ID: 023
Revises: 022
Create Date: 2026-05-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ml_pattern_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pattern_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("features", postgresql.JSONB, nullable=False),
        sa.Column("spawn_decision", sa.String(20), nullable=True),
        sa.Column("ml_decision", sa.String(20), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"]),
    )
    op.create_index("ix_ml_pattern_scores_pattern_id", "ml_pattern_scores", ["pattern_id"])
    op.create_index("ix_ml_pattern_scores_computed_at", "ml_pattern_scores", [sa.text("computed_at DESC")])


def downgrade():
    op.drop_index("ix_ml_pattern_scores_computed_at", table_name="ml_pattern_scores")
    op.drop_index("ix_ml_pattern_scores_pattern_id", table_name="ml_pattern_scores")
    op.drop_table("ml_pattern_scores")
