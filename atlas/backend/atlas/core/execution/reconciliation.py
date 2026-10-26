"""Broker reconciliation: the broker is the source of truth for balances, positions and order
status. Local state is updated to match and every discrepancy is reported."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from atlas.core.execution.broker import BrokerGateway
from atlas.core.execution.state_machine import (
    ALPACA_STATUS_MAP,
    OPEN_BROKER_STATES,
    InvalidTransition,
    can_transition,
    transition,
)
from atlas.core.models.db import AccountSnapshot, Order, OrderState, Position, utcnow
from atlas.core.observability.logging import get_logger

log = get_logger(__name__)


@dataclass
class ReconciliationReport:
    account_equity: str | None = None
    positions: int = 0
    orders_updated: int = 0
    discrepancies: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.discrepancies


def reconcile(
    session: Session, gateway: BrokerGateway, source: str = "alpaca_paper"
) -> ReconciliationReport:
    report = ReconciliationReport()

    account = gateway.get_account()
    if not account.is_paper:
        raise RuntimeError("refusing to reconcile a non-paper account")
    session.add(
        AccountSnapshot(
            source=source,
            is_paper=True,
            account_status=account.status,
            equity=account.equity,
            last_equity=account.last_equity,
            cash=account.cash,
            buying_power=account.buying_power,
            long_market_value=account.long_market_value,
            trading_blocked=account.trading_blocked,
            shorting_enabled=account.shorting_enabled,
            margin_multiplier=account.margin_multiplier,
        )
    )
    report.account_equity = str(account.equity)

    broker_positions = gateway.list_positions()
    local_symbols = set(session.scalars(select(Position.symbol)))
    broker_symbols = {p.symbol for p in broker_positions}
    for sym in sorted(local_symbols - broker_symbols):
        report.discrepancies.append(f"position {sym} existed locally but not at broker")
    for sym in sorted(broker_symbols - local_symbols):
        if local_symbols:
            report.discrepancies.append(f"position {sym} at broker was not tracked locally")
    session.execute(delete(Position))
    now = utcnow()
    for p in broker_positions:
        if p.qty < 0:
            report.discrepancies.append(f"SHORT position {p.symbol} qty={p.qty} (long-only policy)")
        session.add(
            Position(
                symbol=p.symbol,
                qty=p.qty,
                avg_entry_price=p.avg_entry_price,
                market_value=p.market_value,
                unrealized_pl=p.unrealized_pl,
                current_price=p.current_price,
                synced_at=now,
            )
        )
    report.positions = len(broker_positions)

    # Orders we believe may be live at the broker.
    local_open = session.scalars(select(Order).where(Order.state.in_(OPEN_BROKER_STATES))).all()
    broker_open = {o.client_order_id: o for o in gateway.list_open_orders()}
    for order in local_open:
        b = broker_open.pop(order.client_order_id, None) or gateway.get_order_by_client_id(
            order.client_order_id
        )
        if b is None:
            report.discrepancies.append(
                f"order {order.client_order_id} in {order.state} locally but unknown to broker"
            )
            continue
        new_state = ALPACA_STATUS_MAP.get(b.status)
        if new_state is None:
            report.discrepancies.append(f"order {order.client_order_id} unknown status {b.status}")
            continue
        fill_changed = b.filled_qty != order.filled_qty
        order.broker_order_id = b.broker_order_id
        order.filled_qty = b.filled_qty
        order.filled_avg_price = b.filled_avg_price
        if new_state != order.state or (new_state == OrderState.PARTIALLY_FILLED and fill_changed):
            if can_transition(order.state, new_state):
                try:
                    transition(session, order, new_state, {"source": "reconciliation"})
                    report.orders_updated += 1
                except InvalidTransition:  # pragma: no cover - guarded by can_transition
                    pass
            elif new_state != order.state:
                report.discrepancies.append(
                    f"order {order.client_order_id}: illegal {order.state}->{new_state}"
                )
    for cid in broker_open:
        report.discrepancies.append(f"broker has open order {cid} not tracked locally")

    if report.discrepancies:
        log.warning("reconciliation_discrepancies", items=report.discrepancies)
    return report
