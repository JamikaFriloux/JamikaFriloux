"""reference data: instrument classification and earnings calendar

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_reference",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("asset_type", sa.String(length=8), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("leveraged", sa.Boolean(), nullable=False),
        sa.Column("sic", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("asset_type IN ('etf', 'stock')", name="instrument_asset_type_valid"),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_table(
        "earnings_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("timing", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_earnings_symbol_day_source", "earnings_events", ["symbol", "day", "source"], unique=True
    )
    op.create_index("ix_earnings_day", "earnings_events", ["day"])
    op.create_table(
        "earnings_coverage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("events", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_earnings_coverage_fetched_at", "earnings_coverage", ["fetched_at"])


def downgrade() -> None:
    op.drop_table("earnings_coverage")
    op.drop_table("earnings_events")
    op.drop_table("instrument_reference")
