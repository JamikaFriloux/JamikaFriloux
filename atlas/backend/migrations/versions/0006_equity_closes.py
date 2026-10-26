"""equity closes for the drawdown cooldown rule

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equity_closes",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("equity_closes")
