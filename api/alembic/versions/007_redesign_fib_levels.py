"""redesign fib levels table

Revision ID: 007
Revises: 006
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clear existing rows to avoid null constraints or structure mismatch
    op.execute("DELETE FROM fib_levels")
    
    op.drop_constraint("uq_fib_symbol_tf", "fib_levels", type_="unique")
    
    op.drop_column("fib_levels", "timeframe")
    op.drop_column("fib_levels", "swing_high")
    op.drop_column("fib_levels", "swing_low")
    op.drop_column("fib_levels", "direction")
    
    op.add_column("fib_levels", sa.Column("period", sa.String(), nullable=False))
    op.add_column("fib_levels", sa.Column("prev_high", sa.Numeric(12, 5), nullable=False))
    op.add_column("fib_levels", sa.Column("prev_low", sa.Numeric(12, 5), nullable=False))
    op.add_column("fib_levels", sa.Column("prev_close", sa.Numeric(12, 5), nullable=False))
    op.add_column("fib_levels", sa.Column("pp", sa.Numeric(12, 5), nullable=False))
    
    op.alter_column("fib_levels", "levels", new_column_name="resistance")
    op.alter_column("fib_levels", "extensions", new_column_name="support")
    
    op.create_unique_constraint("uq_fib_symbol_period", "fib_levels", ["symbol", "period"])


def downgrade() -> None:
    # Clear existing rows to avoid null constraints or structure mismatch
    op.execute("DELETE FROM fib_levels")
    
    op.drop_constraint("uq_fib_symbol_period", "fib_levels", type_="unique")
    
    op.alter_column("fib_levels", "resistance", new_column_name="levels")
    op.alter_column("fib_levels", "support", new_column_name="extensions")
    
    op.drop_column("fib_levels", "pp")
    op.drop_column("fib_levels", "prev_close")
    op.drop_column("fib_levels", "prev_low")
    op.drop_column("fib_levels", "prev_high")
    op.drop_column("fib_levels", "period")
    
    op.add_column("fib_levels", sa.Column("timeframe", sa.String(), nullable=False))
    op.add_column("fib_levels", sa.Column("swing_high", sa.Numeric(12, 5), nullable=False))
    op.add_column("fib_levels", sa.Column("swing_low", sa.Numeric(12, 5), nullable=False))
    op.add_column("fib_levels", sa.Column("direction", sa.String(), nullable=False))
    
    op.create_unique_constraint("uq_fib_symbol_tf", "fib_levels", ["symbol", "timeframe"])
