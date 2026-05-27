"""backfill trades.paper_trader_rule_id from recovery_plan->>'paper_trader_rule_id'

Independent paper trades opened by baseline_runner before the column was
populated have rule_id only in recovery_plan dict. This backfills the
indexed column so _check_exits can find them. Mirror trades are exempt
by design (they shadow real trades, no rule binding).

Revision ID: 021
Revises: 020
Create Date: 2026-05-27
"""
from alembic import op


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE trades
        SET paper_trader_rule_id = (recovery_plan->>'paper_trader_rule_id')::uuid
        WHERE is_paper = true
          AND paper_mode = 'independent'
          AND paper_trader_rule_id IS NULL
          AND recovery_plan ? 'paper_trader_rule_id'
          AND recovery_plan->>'paper_trader_rule_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        """
    )


def downgrade() -> None:
    pass
