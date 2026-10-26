"""strategy track records (paper and simulated forward)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "track_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("params_hash", sa.String(length=16), nullable=False),
        sa.Column("policy_sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("start", sa.Date(), nullable=True),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("anchor_report_id", sa.Integer(), nullable=True),
        sa.Column("metrics", JSONType, nullable=False),
        sa.Column("equity_curve", JSONType, nullable=False),
        sa.Column("trades", JSONType, nullable=False),
        sa.Column("open_positions", JSONType, nullable=False),
        sa.Column("gates", JSONType, nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_track_records_created_at", "track_records", ["created_at"])
    op.create_index(
        "ix_track_records_strategy_kind_asof", "track_records", ["strategy_id", "kind", "as_of"]
    )


def downgrade() -> None:
    op.drop_table("track_records")
