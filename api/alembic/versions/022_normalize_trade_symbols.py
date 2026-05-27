"""normalize trades.symbol aliases (GOLD, XAUUSD, etc.) → GOLD#

Broker symbol renames (GOLD → GOLD#) created orphan rows: open events stored
under one symbol, close events arrived under another, upsert key (ticket,
symbol, is_paper) failed to match. This collapses aliases to canonical GOLD#.

Pure UPDATE — no row collision is possible because tickets are unique within
broker history; aliases never coexist for the same ticket.

Revision ID: 022
Revises: 021
Create Date: 2026-05-27
"""
from alembic import op


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE trades
        SET symbol = 'GOLD#'
        WHERE upper(symbol) IN ('GOLD', 'XAUUSD', 'XAUUSD#', 'XAUUSD.', 'GOLD.')
        """
    )


def downgrade() -> None:
    pass
