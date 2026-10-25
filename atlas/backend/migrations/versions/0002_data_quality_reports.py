"""data quality reports

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 20:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bars_fetched", sa.Integer(), nullable=False),
        sa.Column("bars_written", sa.Integer(), nullable=False),
        sa.Column("latest_bar_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_latest_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column(
            "issues",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_data_quality_reports_run_id"), "data_quality_reports", ["run_id"], unique=False
    )
    op.create_index(
        "ix_dq_reports_symbol_tf_ts",
        "data_quality_reports",
        ["symbol", "timeframe", "ts"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dq_reports_symbol_tf_ts", table_name="data_quality_reports")
    op.drop_index(op.f("ix_data_quality_reports_run_id"), table_name="data_quality_reports")
    op.drop_table("data_quality_reports")
