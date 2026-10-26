"""Protective stops: every filled entry is covered by a broker-side stop.

A stop lives at the broker (GTC), so it protects the position even if ATLAS is down. After
each reconciliation, ``ensure_protection`` compares what each strategy holds in a symbol
with the quantity covered by its open protective stops and places a stop for any uncovered
quantity, at the stop price of the entry's signal. This also re-protects a position after an
exit attempt cancelled its stop and the exit then failed.

Placing a protective stop reduces risk, so it is allowed while the kill switch is engaged;
the kill switch also leaves existing protective stops in place (it never liquidates).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.execution.broker import (
    BrokerError,
    BrokerGateway,
    BrokerRejected,
    OrderRequest,
    SubmissionUncertain,
    submit_idempotent,
)
from atlas.core.execution.positions import strategy_holdings
from atlas.core.execution.state_machine import (
    ALPACA_STATUS_MAP,
    OPEN_BROKER_STATES,
    can_transition,
    transition,
)
from atlas.core.models.db import Order, OrderState, Position, SignalRecord
from atlas.core.observability.logging import get_logger

log = get_logger(__name__)
PRE_SUBMIT = (OrderState.CANDIDATE, OrderState.VALIDATED, OrderState.RISK_APPROVED)


def protective_stop_ids(session: Session) -> frozenset[str]:
    """Client order ids of protective stops that may be live at the broker."""
    rows = session.scalars(
        select(Order.client_order_id).where(
            Order.purpose == "protective_stop", Order.state.in_(OPEN_BROKER_STATES)
        )
    ).all()
    return frozenset(rows)


@dataclass(frozen=True)
class ProtectionAction:
    symbol: str
    strategy_id: str
    qty: Decimal
    stop_price: Decimal
    client_order_id: str
    outcome: str


def cancel_and_confirm(
    session: Session, gateway: BrokerGateway, order: Order, sleep: Callable[[float], None]
) -> OrderState | None:
    """Cancel at the broker and wait for a terminal state. None if it can't be confirmed."""
    try:
        if order.broker_order_id:
            gateway.cancel_order(order.broker_order_id)
    except BrokerError as exc:
        log.warning(
            "cancel_failed", client_order_id=order.client_order_id, error=type(exc).__name__
        )
    for attempt in range(5):
        b = gateway.get_order_by_client_id(order.client_order_id)
        state = ALPACA_STATUS_MAP.get(b.status) if b else None
        if b is not None and state in (OrderState.CANCELLED, OrderState.FILLED, OrderState.EXPIRED):
            order.filled_qty = b.filled_qty
            if can_transition(order.state, state):
                transition(session, order, state, {"source": "cancel_confirmed"})
            return state
        sleep(0.5 * (attempt + 1))
    return None


def cancel_orphan_stops(
    session: Session, gateway: BrokerGateway, sleep: Callable[[float], None] = time.sleep
) -> list[str]:
    """Cancel protective stops covering more than is actually held.

    The broker accepts a stop-sell without a position (verified live), and a triggered one
    would open a short. If a position shrinks or disappears outside ATLAS (manual close,
    corporate action), its stops must go too; ``ensure_protection`` re-covers what remains.
    """
    broker_qty = {p.symbol: p.qty for p in session.scalars(select(Position)).all()}
    held = {(h.strategy_id, h.symbol): h.qty for h in strategy_holdings(session)}
    live = session.scalars(
        select(Order).where(Order.purpose == "protective_stop", Order.state.in_(OPEN_BROKER_STATES))
    ).all()
    groups: dict[tuple[str, str], list[Order]] = {}
    for o in live:
        groups.setdefault((o.strategy_id or "", o.symbol), []).append(o)
    cancelled = []
    for key, stops in groups.items():
        qty = min(held.get(key, Decimal(0)), broker_qty.get(key[1], Decimal(0)))
        covered = sum((o.qty - o.filled_qty for o in stops), Decimal(0))
        if covered <= qty:
            continue
        log.warning(
            "orphan_protective_stops",
            strategy=key[0],
            symbol=key[1],
            covered=str(covered),
            held=str(qty),
        )
        for o in stops:
            if cancel_and_confirm(session, gateway, o, sleep) is not None:
                cancelled.append(o.client_order_id)
    return cancelled


def ensure_protection(
    session: Session, gateway: BrokerGateway, now: datetime
) -> list[ProtectionAction]:
    actions: list[ProtectionAction] = []
    broker_qty = {p.symbol: p.qty for p in session.scalars(select(Position)).all()}
    for h in strategy_holdings(session):
        held = min(h.qty, broker_qty.get(h.symbol, Decimal(0)))
        if held <= 0:
            continue
        mine = session.scalars(
            select(Order).where(Order.strategy_id == h.strategy_id, Order.symbol == h.symbol)
        ).all()
        if any(o.purpose == "exit" and o.state in (*OPEN_BROKER_STATES, *PRE_SUBMIT) for o in mine):
            continue  # an exit is working; it owns the shares
        covered = sum(
            (
                o.qty - o.filled_qty
                for o in mine
                if o.purpose == "protective_stop" and o.state in (*OPEN_BROKER_STATES, *PRE_SUBMIT)
            ),
            Decimal(0),
        )
        need = held - covered
        if need <= 0:
            continue
        entry = next((o for o in reversed(mine) if o.purpose == "entry" and o.filled_qty > 0), None)
        signal = session.get(SignalRecord, entry.signal_id) if entry and entry.signal_id else None
        if entry is None or signal is None or signal.stop_price is None:
            log.error("protection_missing_stop_price", symbol=h.symbol, strategy=h.strategy_id)
            continue
        n = sum(1 for o in mine if o.purpose == "protective_stop")
        cid = f"atl-{entry.id.hex[:16]}-s{n}"
        order = Order(
            client_order_id=cid,
            symbol=h.symbol,
            side="sell",
            order_type="stop",
            qty=need,
            stop_price=signal.stop_price,
            limit_price=None,
            strategy_id=h.strategy_id,
            strategy_version=entry.strategy_version,
            signal_id=entry.signal_id,
            purpose="protective_stop",
            parent_order_id=entry.id,
            time_in_force="gtc",
        )
        session.add(order)
        session.flush()
        for state in (OrderState.VALIDATED, OrderState.RISK_APPROVED):
            transition(session, order, state, {"source": "protection", "reason": "risk-reducing"})
        outcome = submit_order(session, order, gateway, now)
        actions.append(
            ProtectionAction(h.symbol, h.strategy_id, need, signal.stop_price, cid, outcome)
        )
    return actions


def submit_order(session: Session, order: Order, gateway: BrokerGateway, now: datetime) -> str:
    """Submit a RISK_APPROVED order once. Returns the outcome; never resubmits blindly."""
    req = OrderRequest(
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        side="buy" if order.side == "buy" else "sell",
        qty=order.qty,
        limit_price=order.limit_price,
        order_type="stop" if order.order_type == "stop" else "limit",
        stop_price=order.stop_price,
        time_in_force="gtc" if order.time_in_force == "gtc" else "day",
    )
    order.submitted_at = now.astimezone(UTC)  # storage is UTC (CLAUDE.md rule 10)
    transition(session, order, OrderState.SUBMITTED, {"source": "submit"})
    session.flush()
    try:
        b = submit_idempotent(gateway, req)
    except BrokerRejected as exc:
        order.last_error = str(exc)[:500]
        transition(
            session, order, OrderState.REJECTED, {"source": "broker", "error": order.last_error}
        )
        return "rejected"
    except SubmissionUncertain as exc:
        # Left in SUBMITTED: reconciliation queries the broker by client order id.
        order.last_error = str(exc)[:500]
        return "uncertain"
    order.broker_order_id = b.broker_order_id
    order.filled_qty = b.filled_qty
    order.filled_avg_price = b.filled_avg_price
    new = ALPACA_STATUS_MAP.get(b.status)
    if new is not None and new != OrderState.SUBMITTED:
        transition(session, order, new, {"source": "submit", "broker_status": b.status})
    return "submitted"
