"""Signal -> risk decision -> order.

Runs in the executor during the session after a signal's ``as_of`` close:
  * only signals from the last completed session are acted on; older ones expire;
  * every signal is evaluated by the risk engine with live inputs. RESEARCH (shadow) signals
    get their decision recorded and are never ordered. PAPER signals that pass become orders
    and go through the state machine and ``submit_idempotent``;
  * a rejection caused only by transient inputs (no fresh quote or account snapshot, outside
    the entry window) leaves the signal pending for the next run until the window closes;
    anything else is final and recorded;
  * the client order id is derived from the signal, so re-running can never submit twice;
  * each signal is committed on its own, so a submitted order is never lost to a later error;
  * an exit cancels the position's protective stop and waits for the cancel to be confirmed
    before selling (the stop reserves the shares). If the exit then fails, protection
    re-places a stop on the next sync.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.universe import current_universe, is_stale, member_symbols
from atlas.core.execution.broker import BrokerGateway
from atlas.core.execution.positions import strategy_holdings
from atlas.core.execution.protection import cancel_and_confirm, submit_order
from atlas.core.execution.state_machine import OPEN_BROKER_STATES, transition
from atlas.core.models.db import (
    AccountSnapshot,
    Order,
    OrderState,
    Position,
    RiskDecision,
    SignalRecord,
    StrategyRecord,
    StrategyStatus,
)
from atlas.core.observability.logging import get_logger
from atlas.core.risk import kill_switch
from atlas.core.risk.drawdown import at_session, production_state
from atlas.core.risk.engine import (
    AccountState,
    OpenOrderState,
    QuoteState,
    RiskContext,
    RiskResult,
    evaluate,
)
from atlas.core.strategies.base import Signal

log = get_logger(__name__)
TRANSIENT_CHECKS = frozenset({"quote", "spread", "account_snapshot", "entry_window", "market_open"})
# Checks computed from the quote/account; when those are missing they fail as a consequence.
DEPENDENT_CHECKS = frozenset({"size", "stop_below_entry", "daily_loss", "drawdown"})


def is_transient(failed: tuple[str, ...]) -> bool:
    """True when a rejection could clear by itself (fresh data, entry window opening)."""
    blocking = set(failed)
    if blocking & {"quote", "account_snapshot"}:
        blocking -= DEPENDENT_CHECKS
    return bool(blocking) and blocking <= TRANSIENT_CHECKS


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


@dataclass
class ExecutionDeps:
    gateway: BrokerGateway | None  # None: shadow evaluation only
    quote_for: Callable[[str], QuoteState | None]
    # Reference data (core/reference); the defaults mean "no data", which fails closed.
    earnings_blackout: Callable[[str], bool | None] = lambda _symbol: None
    sector_for: Callable[[str], str] | None = None  # None: all exposure shares one bucket
    sleep: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class SignalOutcome:
    signal_id: str
    symbol: str
    kind: str
    mode: str
    status: str
    failed: tuple[str, ...] = ()


def as_signal(rec: SignalRecord) -> Signal:
    return Signal(
        rec.strategy_id,
        rec.strategy_version,
        rec.symbol,
        rec.kind,  # type: ignore[arg-type]
        rec.as_of,
        rec.ref_price,
        rec.stop_price,
        rec.reason,
    )


def build_context(
    session: Session,
    rec: SignalRecord,
    status: StrategyStatus,
    deps: ExecutionDeps,
    *,
    now: datetime,
    calendar: MarketCalendar,
    policy: RiskPolicy,
) -> RiskContext:
    snap = session.scalars(
        select(AccountSnapshot).order_by(AccountSnapshot.ts.desc()).limit(1)
    ).first()
    account = (
        None
        if snap is None
        else AccountState(
            equity=snap.equity,
            last_equity=snap.last_equity,
            cash=snap.cash,
            long_market_value=snap.long_market_value,
            trading_blocked=snap.trading_blocked,
            as_of=_utc(snap.ts),
            shorting_enabled=snap.shorting_enabled,
        )
    )
    # Drawdown halt: replay recorded session closes (cooldown + reset, core/risk/drawdown.py).
    dd_state = production_state(session, now.astimezone(NY).date(), policy, calendar)
    hwm, cooldown_left = (
        at_session(dd_state, now.astimezone(NY).date(), account.equity, policy, calendar)
        if account is not None
        else (None, 0)
    )
    position_rows = session.scalars(select(Position)).all()
    positions = {p.symbol: p.qty for p in position_rows}
    open_rows = session.scalars(select(Order).where(Order.state.in_(OPEN_BROKER_STATES))).all()
    open_orders = tuple(
        OpenOrderState(o.symbol, o.side, o.purpose, o.qty - o.filled_qty, o.limit_price)
        for o in open_rows
        if o.purpose != "protective_stop"
    )
    sector = sector_exposure = None
    if deps.sector_for is not None:
        sector = deps.sector_for(rec.symbol)
        sector_exposure = sum(
            (p.market_value for p in position_rows if deps.sector_for(p.symbol) == sector),
            Decimal(0),
        ) + sum(
            (
                o.qty * (o.limit_price or Decimal(0))
                for o in open_orders
                if o.side == "buy" and deps.sector_for(o.symbol) == sector
            ),
            Decimal(0),
        )
    session_open = calendar.current_or_next_session(now).open
    entries_today = (
        session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.purpose == "entry", Order.submitted_at >= session_open)
        )
        or 0
    )
    universe = current_universe(session)
    held = next(
        (h.qty for h in strategy_holdings(session, rec.strategy_id) if h.symbol == rec.symbol),
        Decimal(0),
    )
    return RiskContext(
        now=now,
        mode="paper" if rec.mode == "paper" else "shadow",
        kill_switch_engaged=not kill_switch.is_trading_allowed(session),
        strategy_status=status,
        account=account,
        high_water_mark=hwm,
        positions=positions,
        open_orders=open_orders,
        entries_submitted_today=int(entries_today),
        universe_members=frozenset(member_symbols(session, universe)) if universe else None,
        universe_stale=is_stale(universe, now, calendar) if universe else True,
        quote=deps.quote_for(rec.symbol),
        strategy_position_qty=held,
        earnings_blackout=deps.earnings_blackout(rec.symbol),
        drawdown_cooldown_remaining=cooldown_left,
        sector=sector,
        sector_exposure=sector_exposure,
    )


def record_decision(
    session: Session, rec: SignalRecord, result: RiskResult, mode: str
) -> RiskDecision:
    d = RiskDecision(
        signal_id=rec.id,
        strategy_id=rec.strategy_id,
        symbol=rec.symbol,
        kind=rec.kind,
        mode=mode,
        approved=result.approved,
        qty=result.qty,
        limit_price=result.limit_price,
        failed=result.failed,
        checks=result.checks_json(),
        capital_base=result.capital_base,
    )
    session.add(d)
    session.flush()
    return d


def process_pending_signals(
    session: Session,
    deps: ExecutionDeps,
    *,
    now: datetime,
    policy: RiskPolicy,
    calendar: MarketCalendar,
) -> list[SignalOutcome]:
    if not calendar.is_open(now):
        return []
    today = now.astimezone(NY).date()
    prior = [d for d in calendar.sessions_between(today - timedelta(days=10), today) if d < today]
    valid_as_of = prior[-1]
    outcomes: list[SignalOutcome] = []

    stale = session.scalars(
        select(SignalRecord).where(SignalRecord.status == "NEW", SignalRecord.as_of < valid_as_of)
    ).all()
    for rec in stale:
        rec.status = "EXPIRED"
        outcomes.append(SignalOutcome(rec.id, rec.symbol, rec.kind, rec.mode, "EXPIRED"))
    session.commit()

    pending = session.scalars(
        select(SignalRecord)
        .where(SignalRecord.status == "NEW", SignalRecord.as_of == valid_as_of)
        .order_by(SignalRecord.kind.desc(), SignalRecord.created_at)  # exits before entries
    ).all()
    to_close = calendar.minutes_to_close(now) or 0.0
    window_left = to_close > policy.session.no_new_positions_minutes_before_close
    for rec in pending:
        row = session.get(StrategyRecord, rec.strategy_id)
        status = row.status if row else StrategyStatus.RETIRED
        ctx = build_context(session, rec, status, deps, now=now, calendar=calendar, policy=policy)
        result = evaluate(as_signal(rec), ctx, policy, calendar)
        failed = tuple(result.failed)
        if not result.approved and is_transient(failed) and window_left:
            outcomes.append(
                SignalOutcome(rec.id, rec.symbol, rec.kind, rec.mode, "PENDING", failed)
            )
            continue  # try again on the next run
        record_decision(session, rec, result, ctx.mode)
        if ctx.mode == "shadow":
            rec.status = "SHADOWED"
        elif not result.approved:
            rec.status = "REJECTED"
        else:
            rec.status = _place(session, rec, result, deps, now)
        outcomes.append(SignalOutcome(rec.id, rec.symbol, rec.kind, rec.mode, rec.status, failed))
        session.commit()
    return outcomes


def _place(
    session: Session, rec: SignalRecord, result: RiskResult, deps: ExecutionDeps, now: datetime
) -> str:
    if deps.gateway is None:
        raise RuntimeError("paper signal approved but no broker gateway available")
    purpose = "entry" if rec.kind == "entry" else "exit"
    cid = f"atl-{rec.id[:20]}-{purpose[0]}"
    if session.scalars(select(Order).where(Order.client_order_id == cid)).first() is not None:
        return "ORDERED"  # already placed on an earlier run
    if purpose == "exit":
        released = _release_protective_stops(session, rec, deps)
        if released == "pending":
            return "NEW"  # stop not confirmed cancelled; retry next run, still protected
        if released == "stopped_out":
            return "STOPPED_OUT"  # the stop sold first; selling again would oversell
    assert result.qty is not None and result.limit_price is not None
    order = Order(
        client_order_id=cid,
        symbol=rec.symbol,
        side=rec.side,
        order_type="limit",
        qty=result.qty,
        limit_price=result.limit_price,
        strategy_id=rec.strategy_id,
        strategy_version=rec.strategy_version,
        signal_id=rec.id,
        purpose=purpose,
        time_in_force="day",
    )
    session.add(order)
    session.flush()
    transition(session, order, OrderState.VALIDATED, {"source": "pipeline"})
    transition(
        session,
        order,
        OrderState.RISK_APPROVED,
        {"source": "risk_engine", "capital_base": str(result.capital_base)},
    )
    # Last look at the kill switch immediately before anything leaves the building.
    if not kill_switch.is_trading_allowed(session):
        transition(session, order, OrderState.REJECTED, {"source": "kill_switch"})
        return "REJECTED"
    outcome = submit_order(session, order, deps.gateway, now)
    return "REJECTED" if outcome == "rejected" else "ORDERED"


def _release_protective_stops(session: Session, rec: SignalRecord, deps: ExecutionDeps) -> str:
    """Cancel this position's protective stops and confirm.

    Returns "released" (none live), "stopped_out" (a stop filled first) or "pending".
    """
    assert deps.gateway is not None
    stops = session.scalars(
        select(Order).where(
            Order.strategy_id == rec.strategy_id,
            Order.symbol == rec.symbol,
            Order.purpose == "protective_stop",
            Order.state.in_(OPEN_BROKER_STATES),
        )
    ).all()
    stopped = False
    for stop in stops:
        if cancel_and_confirm(session, deps.gateway, stop, deps.sleep) is None:
            return "pending"
        stopped = stopped or stop.filled_qty > 0
    return "stopped_out" if stopped else "released"
