"""normalize legacy mirror paper_exit_strategy labels to 'rule_driven'

Revision ID: 019
Revises: 018
Create Date: 2026-05-26
"""
from alembic import op


revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE trades
        SET paper_exit_strategy = 'rule_driven'
        WHERE is_paper = true
          AND paper_mode = 'mirror'
          AND paper_exit_strategy IS NOT NULL
          AND paper_exit_strategy <> 'rule_driven'
          AND (paper_exit_strategy LIKE 'tp:%' OR paper_exit_strategy LIKE 'sl:%')
        """
    )


def downgrade() -> None:
    pass
