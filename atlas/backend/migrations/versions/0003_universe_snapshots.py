"""universe snapshots

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "universe_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("criteria", JSON, nullable=False),
        sa.Column("assets_seen", sa.Integer(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("exclusions", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_universe_snapshots_as_of"), "universe_snapshots", ["as_of"], unique=False
    )
    op.create_table(
        "universe_members",
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("last_close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("adv_usd", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("fractionable", sa.Boolean(), nullable=False),
        sa.Column("shortable", sa.Boolean(), nullable=False),
        sa.Column("easy_to_borrow", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["universe_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id", "symbol"),
    )
    op.create_index("ix_universe_members_symbol", "universe_members", ["symbol"], unique=False)
    # Snapshots are point-in-time records: never edited in place (deletion for retention is ok).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas_universe_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'universe snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("universe_snapshots", "universe_members"):
        op.execute(
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION atlas_universe_immutable();"
        )


def downgrade() -> None:
    for table in ("universe_members", "universe_snapshots"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update ON {table}")
    op.execute("DROP FUNCTION IF EXISTS atlas_universe_immutable()")
    op.drop_index("ix_universe_members_symbol", table_name="universe_members")
    op.drop_table("universe_members")
    op.drop_index(op.f("ix_universe_snapshots_as_of"), table_name="universe_snapshots")
    op.drop_table("universe_snapshots")
