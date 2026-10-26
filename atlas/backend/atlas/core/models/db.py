"""SQLAlchemy ORM models.

All timestamps are timezone-aware UTC. Money is stored as Numeric, never float. Models are
portable (JSON falls back from JSONB) so unit tests can run on SQLite; production and
integration tests use PostgreSQL, where the migration additionally installs an append-only
trigger on ``audit_log``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
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
    shorting_enabled: Mapped[bool | None] = mapped_column(Boolean)
    margin_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

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
    # Phase 3: why the order exists. purpose is entry / exit / protective_stop; a protective
    # stop points at the entry order it protects.
    signal_id: Mapped[str | None] = mapped_column(String(32), index=True)
    purpose: Mapped[str | None] = mapped_column(String(16))
    parent_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    time_in_force: Mapped[str] = mapped_column(String(8), default="day")

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


class DataQualityReport(Base):
    """Outcome of one ingestion/validation pass for a symbol and timeframe.

    ``ok`` is false when any critical issue was found; bars from such a pass are not written.
    ``stale`` is true when the newest stored bar is older than the calendar says it should be.
    """

    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    symbol: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(32))
    adjustment: Mapped[str] = mapped_column(String(16), default="all", server_default="all")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bars_fetched: Mapped[int] = mapped_column(Integer, default=0)
    bars_written: Mapped[int] = mapped_column(Integer, default=0)
    latest_bar_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_latest_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean)
    stale: Mapped[bool] = mapped_column(Boolean)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    __table_args__ = (Index("ix_dq_reports_symbol_tf_ts", "symbol", "timeframe", "ts"),)


class UniverseSnapshot(Base):
    """Point-in-time tradable universe, built from data up to and including ``as_of``.

    Rows are written once and never updated, so research can ask "what was tradable on day
    D?" without survivorship bias (for days on or after the first snapshot).
    """

    __tablename__ = "universe_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)  # last session in the data window
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(32))
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    assets_seen: Mapped[int] = mapped_column(Integer)
    member_count: Mapped[int] = mapped_column(Integer)
    exclusions: Mapped[dict[str, int]] = mapped_column(JSONType, default=dict)


class UniverseMember(Base):
    __tablename__ = "universe_members"

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("universe_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    exchange: Mapped[str] = mapped_column(String(16))
    last_close: Mapped[Decimal] = mapped_column(Money)
    adv_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))  # mean daily close*volume
    sessions: Mapped[int] = mapped_column(Integer)
    fractionable: Mapped[bool] = mapped_column(Boolean)
    shortable: Mapped[bool] = mapped_column(Boolean)
    easy_to_borrow: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (Index("ix_universe_members_symbol", "symbol"),)


class StrategyStatus(enum.StrEnum):
    RESEARCH = "RESEARCH"  # signals are recorded and risk-checked in shadow; never ordered
    PAPER = "PAPER"  # may submit paper orders (requires passing validation gates)
    LIVE_CANDIDATE = "LIVE_CANDIDATE"  # still cannot submit live orders in this deployment
    RETIRED = "RETIRED"


class StrategyRecord(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[StrategyStatus] = mapped_column(
        _enum(StrategyStatus, "strategy_status"), default=StrategyStatus.RESEARCH
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    updated_by: Mapped[str] = mapped_column(String(64), default="system")


class SignalRecord(Base):
    """A strategy's decision for one symbol and session. ``id`` is deterministic, so
    re-running the signal engine for the same session never duplicates a signal."""

    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_version: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(8))  # entry / exit
    side: Mapped[str] = mapped_column(String(8))
    as_of: Mapped[date] = mapped_column(Date, index=True)  # session whose close produced it
    ref_price: Mapped[Decimal] = mapped_column(Money)
    stop_price: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    mode: Mapped[str] = mapped_column(String(8))  # shadow / paper
    status: Mapped[str] = mapped_column(String(16), default="NEW", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("kind IN ('entry', 'exit')", name="signal_kind_valid"),
        CheckConstraint("side IN ('buy', 'sell')", name="signal_side_valid"),
    )


class RiskDecision(Base):
    """Every risk-engine evaluation, approved or not, with each check's outcome."""

    __tablename__ = "risk_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    signal_id: Mapped[str | None] = mapped_column(String(32), index=True)
    strategy_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str] = mapped_column(String(8))
    approved: Mapped[bool] = mapped_column(Boolean)
    qty: Mapped[Decimal | None] = mapped_column(Money)
    limit_price: Mapped[Decimal | None] = mapped_column(Money)
    failed: Mapped[list[str]] = mapped_column(JSONType, default=list)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    capital_base: Mapped[Decimal | None] = mapped_column(Money)


class ValidationReport(Base):
    """Evidence for promoting one exact strategy version (and parameter set) to PAPER."""

    __tablename__ = "validation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    params_hash: Mapped[str] = mapped_column(String(16))
    target_status: Mapped[str] = mapped_column(String(32))
    policy_sha256: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool] = mapped_column(Boolean)
    data_start: Mapped[date] = mapped_column(Date)
    data_end: Mapped[date] = mapped_column(Date)
    symbols: Mapped[list[str]] = mapped_column(JSONType, default=list)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    equity_curve: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    caveats: Mapped[list[str]] = mapped_column(JSONType, default=list)
    runtime_seconds: Mapped[float] = mapped_column(Numeric(10, 1))
    requested_by: Mapped[str] = mapped_column(String(64), default="system")


class EquityClose(Base):
    """Broker equity at each session close; the drawdown halt is replayed from these."""

    __tablename__ = "equity_closes"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    equity: Mapped[Decimal] = mapped_column(Money)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # snapshot time


class NewsArticle(Base):
    """A news item from the broker's news feed, stored as received (untrusted text).

    Fetched by the executor, which holds the data credentials; analysed by the research
    worker, which always wraps ``headline``/``summary`` with ``wrap_untrusted``.
    """

    __tablename__ = "news_articles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "<source>:<provider id>"
    source: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str | None] = mapped_column(String(64))  # e.g. benzinga
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text)
    symbols: Mapped[list[str]] = mapped_column(JSONType, default=list)


class AgentReport(Base):
    """One run of a research agent. Advisory only: nothing reads these to trade.

    ``features`` are computed deterministically in code and are the source of truth.
    ``narrative`` is the schema-validated LLM output, or null when the LLM was disabled,
    over budget, refused or failed (``status`` and ``error`` say which).
    """

    __tablename__ = "agent_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    agent: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(32), default="market")  # "market" or a symbol
    as_of: Mapped[date] = mapped_column(Date)
    prompt_version: Mapped[str] = mapped_column(String(16))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    features: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_agent_reports_agent_scope_created", "agent", "scope", "created_at"),
        Index("ix_agent_reports_input_hash", "agent", "input_hash"),
    )
