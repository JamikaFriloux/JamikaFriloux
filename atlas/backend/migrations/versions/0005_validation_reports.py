"""validation reports

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "validation_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("params", JSON, nullable=False),
        sa.Column("params_hash", sa.String(length=16), nullable=False),
        sa.Column("target_status", sa.String(length=32), nullable=False),
        sa.Column("policy_sha256", sa.String(length=64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("data_start", sa.Date(), nullable=False),
        sa.Column("data_end", sa.Date(), nullable=False),
        sa.Column("symbols", JSON, nullable=False),
        sa.Column("gates", JSON, nullable=False),
        sa.Column("metrics", JSON, nullable=False),
        sa.Column("equity_curve", JSON, nullable=False),
        sa.Column("caveats", JSON, nullable=False),
        sa.Column("runtime_seconds", sa.Numeric(precision=10, scale=1), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_validation_reports_created_at"), "validation_reports", ["created_at"])
    op.create_index(
        op.f("ix_validation_reports_strategy_id"), "validation_reports", ["strategy_id"]
    )
    op.add_column(
        "data_quality_reports",
        sa.Column("adjustment", sa.String(length=16), nullable=False, server_default="all"),
    )
    # Evidence must not be edited after the fact.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas_validation_report_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'validation reports are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER validation_reports_no_update BEFORE UPDATE ON validation_reports "
        "FOR EACH ROW EXECUTE FUNCTION atlas_validation_report_immutable();"
    )


def downgrade() -> None:
    op.drop_column("data_quality_reports", "adjustment")
    op.execute("DROP TRIGGER IF EXISTS validation_reports_no_update ON validation_reports")
    op.execute("DROP FUNCTION IF EXISTS atlas_validation_report_immutable()")
    op.drop_index(op.f("ix_validation_reports_strategy_id"), table_name="validation_reports")
    op.drop_index(op.f("ix_validation_reports_created_at"), table_name="validation_reports")
    op.drop_table("validation_reports")
