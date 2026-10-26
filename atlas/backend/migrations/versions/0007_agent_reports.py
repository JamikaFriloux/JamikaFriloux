"""research agents: news articles and agent reports

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("symbols", JSONType, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"])
    op.create_table(
        "agent_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("prompt_version", sa.String(length=16), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("features", JSONType, nullable=False),
        sa.Column("narrative", JSONType, nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_reports_created_at", "agent_reports", ["created_at"])
    op.create_index(
        "ix_agent_reports_agent_scope_created", "agent_reports", ["agent", "scope", "created_at"]
    )
    op.create_index("ix_agent_reports_input_hash", "agent_reports", ["agent", "input_hash"])


def downgrade() -> None:
    op.drop_table("agent_reports")
    op.drop_table("news_articles")
