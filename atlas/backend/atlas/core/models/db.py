"""SQLAlchemy ORM models.

All timestamps are timezone-aware UTC. Money is stored as Numeric, never float. Models are
portable (JSON falls back from JSONB) so unit tests can run on SQLite; production and
integration tests use PostgreSQL, where the migration additionally installs an append-only
trigger on ``audit_log``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(18, 6)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


ROLE_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}


class OrderState(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, native_enum=False, length=32, validate_strings=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Append-only record of every security- or trading-relevant action."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))


class KillSwitch(Base):
    """Singleton row (id=1). When engaged, no new orders may be submitted."""

    __tablename__ = "kill_switch"
    __table_args__ = (CheckConstraint("id = 1", name="kill_switch_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    engaged: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    engaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engaged_by: Mapped[str | None] = mapped_column(String(64))
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_by: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=0)
    __mapper_args__ = {"version_id_col": version}


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"

    service: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(32))  # e.g. "alpaca_paper"
    is_paper: Mapped[bool] = mapped_column(Boolean)
    account_status: Mapped[str] = mapped_column(String(32))
    equity: Mapped[Decimal] = mapped_column(Money)
    last_equity: Mapped[Decimal] = mapped_column(Money)  # broker's prior-close equity
    cash: Mapped[Decimal] = mapped_column(Money)
    buying_power: Mapped[Decimal] = mapped_column(Money)
    long_market_value: Mapped[Decimal] = mapped_column(Money)
    trading_blocked: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (CheckConstraint("is_paper", name="account_snapshot_paper_only"),)


class Position(Base):
    __tablename__ = "positions"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    qty: Mapped[Decimal] = mapped_column(Money)
    avg_entry_price: Mapped[Decimal] = mapped_column(Money)
    market_value: Mapped[Decimal] = mapped_column(Money)
    unrealized_pl: Mapped[Decimal] = mapped_column(Money)
    current_price: Mapped[Decimal | None] = mapped_column(Money)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_order_id: Mapped[str] = mapped_column(String(128), unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    qty: Mapped[Decimal] = mapped_column(Money)
    limit_price: Mapped[Decimal | None] = mapped_column(Money)
    stop_price: Mapped[Decimal | None] = mapped_column(Money)
    state: Mapped[OrderState] = mapped_column(
        _enum(OrderState, "order_state"), default=OrderState.CANDIDATE, index=True
    )
    strategy_id: Mapped[str | None] = mapped_column(String(64))
    strategy_version: Mapped[str | None] = mapped_column(String(32))
    filled_qty: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    filled_avg_price: Mapped[Decimal | None] = mapped_column(Money)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("side IN ('buy', 'sell')", name="order_side_valid"),)


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Bar(Base):
    """OHLCV bar. ``ts`` is the bar's open time in UTC as reported by the data source."""

    __tablename__ = "bars"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    adjustment: Mapped[str] = mapped_column(String(16), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Money)
    high: Mapped[Decimal] = mapped_column(Money)
    low: Mapped[Decimal] = mapped_column(Money)
    close: Mapped[Decimal] = mapped_column(Money)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    vwap: Mapped[Decimal | None] = mapped_column(Money)
    trade_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_bars_symbol_tf_ts", "symbol", "timeframe", "ts"),)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    symbols: Mapped[list[str]] = mapped_column(JSONType, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
