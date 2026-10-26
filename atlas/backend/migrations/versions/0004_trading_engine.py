"""trading engine: strategies, signals, risk decisions, order linkage

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
MONEY = sa.Numeric(precision=18, scale=6)


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "RESEARCH",
                "PAPER",
                "LIVE_CANDIDATE",
                "RETIRED",
                name="strategy_status",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("params", JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("ref_price", MONEY, nullable=False),
        sa.Column("stop_price", MONEY, nullable=True),
        sa.Column("reason", JSON, nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('entry', 'exit')", name="signal_kind_valid"),
        sa.CheckConstraint("side IN ('buy', 'sell')", name="signal_side_valid"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signals_as_of"), "signals", ["as_of"], unique=False)
    op.create_index(op.f("ix_signals_status"), "signals", ["status"], unique=False)
    op.create_index(op.f("ix_signals_strategy_id"), "signals", ["strategy_id"], unique=False)
    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_id", sa.String(length=32), nullable=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("qty", MONEY, nullable=True),
        sa.Column("limit_price", MONEY, nullable=True),
        sa.Column("failed", JSON, nullable=False),
        sa.Column("checks", JSON, nullable=False),
        sa.Column("capital_base", MONEY, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_decisions_signal_id"), "risk_decisions", ["signal_id"])
    op.create_index(op.f("ix_risk_decisions_ts"), "risk_decisions", ["ts"])
    op.add_column("orders", sa.Column("signal_id", sa.String(length=32), nullable=True))
    op.add_column("orders", sa.Column("purpose", sa.String(length=16), nullable=True))
    op.add_column("orders", sa.Column("parent_order_id", sa.Uuid(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("time_in_force", sa.String(length=8), nullable=False, server_default="day"),
    )
    op.create_index(op.f("ix_orders_signal_id"), "orders", ["signal_id"], unique=False)
    op.add_column("account_snapshots", sa.Column("shorting_enabled", sa.Boolean(), nullable=True))
    op.add_column(
        "account_snapshots",
        sa.Column("margin_multiplier", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.create_foreign_key(
        "orders_parent_order_id_fkey", "orders", "orders", ["parent_order_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_column("account_snapshots", "margin_multiplier")
    op.drop_column("account_snapshots", "shorting_enabled")
    op.drop_constraint("orders_parent_order_id_fkey", "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_signal_id"), table_name="orders")
    for col in ("time_in_force", "parent_order_id", "purpose", "signal_id"):
        op.drop_column("orders", col)
    op.drop_index(op.f("ix_risk_decisions_ts"), table_name="risk_decisions")
    op.drop_index(op.f("ix_risk_decisions_signal_id"), table_name="risk_decisions")
    op.drop_table("risk_decisions")
    op.drop_index(op.f("ix_signals_strategy_id"), table_name="signals")
    op.drop_index(op.f("ix_signals_status"), table_name="signals")
    op.drop_index(op.f("ix_signals_as_of"), table_name="signals")
    op.drop_table("signals")
    op.drop_table("strategies")
