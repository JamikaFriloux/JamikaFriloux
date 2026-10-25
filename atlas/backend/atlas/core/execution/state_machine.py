"""Order lifecycle state machine.

CANDIDATE -> VALIDATED -> RISK_APPROVED -> SUBMITTED -> ACKNOWLEDGED
          -> PARTIALLY_FILLED / FILLED / CANCELLED / REJECTED / EXPIRED

Any transition not listed in ``TRANSITIONS`` raises ``InvalidTransition``. Terminal states have
no outgoing transitions. Broker updates may skip ACKNOWLEDGED (e.g. an immediate fill observed
during reconciliation), so SUBMITTED may move directly to any broker-reported state.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from atlas.core.models.db import Order, OrderEvent, OrderState

S = OrderState

TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    S.CANDIDATE: frozenset({S.VALIDATED, S.REJECTED, S.EXPIRED}),
    S.VALIDATED: frozenset({S.RISK_APPROVED, S.REJECTED, S.EXPIRED}),
    S.RISK_APPROVED: frozenset({S.SUBMITTED, S.REJECTED, S.EXPIRED}),
    S.SUBMITTED: frozenset(
        {S.ACKNOWLEDGED, S.PARTIALLY_FILLED, S.FILLED, S.CANCELLED, S.REJECTED, S.EXPIRED}
    ),
    S.ACKNOWLEDGED: frozenset({S.PARTIALLY_FILLED, S.FILLED, S.CANCELLED, S.REJECTED, S.EXPIRED}),
    S.PARTIALLY_FILLED: frozenset({S.PARTIALLY_FILLED, S.FILLED, S.CANCELLED, S.EXPIRED}),
    S.FILLED: frozenset(),
    S.CANCELLED: frozenset(),
    S.REJECTED: frozenset(),
    S.EXPIRED: frozenset(),
}

TERMINAL_STATES = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)
# States in which the broker may hold a live order for us.
OPEN_BROKER_STATES = frozenset({S.SUBMITTED, S.ACKNOWLEDGED, S.PARTIALLY_FILLED})

# Alpaca order status -> ATLAS state. Unknown statuses map to None and must be investigated.
ALPACA_STATUS_MAP: dict[str, OrderState] = {
    "new": S.ACKNOWLEDGED,
    "accepted": S.ACKNOWLEDGED,
    "pending_new": S.SUBMITTED,
    "accepted_for_bidding": S.ACKNOWLEDGED,
    "held": S.ACKNOWLEDGED,
    "pending_replace": S.ACKNOWLEDGED,
    "replaced": S.CANCELLED,
    "partially_filled": S.PARTIALLY_FILLED,
    "filled": S.FILLED,
    "done_for_day": S.EXPIRED,
    "pending_cancel": S.ACKNOWLEDGED,
    "canceled": S.CANCELLED,
    "expired": S.EXPIRED,
    "rejected": S.REJECTED,
    "suspended": S.ACKNOWLEDGED,
    "stopped": S.ACKNOWLEDGED,
    "calculated": S.ACKNOWLEDGED,
    "pending_review": S.ACKNOWLEDGED,
}


class InvalidTransition(ValueError):
    pass


def can_transition(current: OrderState, new: OrderState) -> bool:
    return new in TRANSITIONS[current]


def transition(
    session: Session, order: Order, new: OrderState, details: dict[str, Any] | None = None
) -> Order:
    current = order.state
    if not can_transition(current, new):
        raise InvalidTransition(f"{current} -> {new} is not permitted for order {order.id}")
    order.state = new
    session.add(
        OrderEvent(
            order_id=order.id,
            from_state=current.value,
            to_state=new.value,
            details=details or {},
        )
    )
    return order
