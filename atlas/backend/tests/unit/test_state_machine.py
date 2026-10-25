import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.execution.state_machine import (
    ALPACA_STATUS_MAP,
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransition,
    transition,
)
from atlas.core.models.db import Order, OrderEvent, OrderState

S = OrderState


def _order(db):
    o = Order(
        client_order_id=f"atlas-{uuid.uuid4()}",
        symbol="SPY",
        side="buy",
        order_type="limit",
        qty=Decimal(1),
        limit_price=Decimal(500),
    )
    db.add(o)
    db.flush()
    return o


def test_happy_path_records_events(db):
    o = _order(db)
    for st in [
        S.VALIDATED,
        S.RISK_APPROVED,
        S.SUBMITTED,
        S.ACKNOWLEDGED,
        S.PARTIALLY_FILLED,
        S.FILLED,
    ]:
        transition(db, o, st)
    db.flush()
    events = db.scalars(
        select(OrderEvent).where(OrderEvent.order_id == o.id).order_by(OrderEvent.id)
    ).all()
    assert [e.to_state for e in events][-1] == "FILLED"
    assert len(events) == 6
    assert o.state == S.FILLED


@pytest.mark.parametrize(
    ("start_path", "bad"),
    [
        ([], S.SUBMITTED),  # cannot skip risk approval
        ([], S.RISK_APPROVED),  # cannot skip validation
        ([S.VALIDATED], S.SUBMITTED),
        ([S.VALIDATED, S.RISK_APPROVED, S.SUBMITTED, S.FILLED], S.CANCELLED),
        ([S.REJECTED], S.VALIDATED),
    ],
)
def test_illegal_transitions_raise(db, start_path, bad):
    o = _order(db)
    for st in start_path:
        transition(db, o, st)
    with pytest.raises(InvalidTransition):
        transition(db, o, bad)


def test_terminal_states_have_no_exits():
    assert {S.FILLED, S.CANCELLED, S.REJECTED, S.EXPIRED} == TERMINAL_STATES
    for st in TERMINAL_STATES:
        assert not TRANSITIONS[st]


def test_every_state_has_transition_entry():
    assert set(TRANSITIONS) == set(OrderState)


def test_alpaca_status_map_covers_sdk_enum():
    from alpaca.trading.enums import OrderStatus

    assert {s.value for s in OrderStatus} <= set(ALPACA_STATUS_MAP)
