import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.execution.broker import AccountInfo, OrderRequest, PositionInfo
from atlas.core.execution.reconciliation import reconcile
from atlas.core.models.db import AccountSnapshot, Order, OrderState, Position
from tests.fakes import FakeBroker


def _local_order(db, cid, state=OrderState.SUBMITTED):
    o = Order(
        id=uuid.uuid4(),
        client_order_id=cid,
        symbol="SPY",
        side="buy",
        order_type="limit",
        qty=Decimal(10),
        limit_price=Decimal(500),
        state=state,
    )
    db.add(o)
    db.flush()
    return o


def test_account_and_positions_synced(db):
    b = FakeBroker()
    b.positions = [
        PositionInfo("SPY", Decimal(2), Decimal(500), Decimal(1010), Decimal(10), Decimal(505))
    ]
    r = reconcile(db, b)
    assert r.clean and r.positions == 1
    assert db.scalar(select(AccountSnapshot)).equity == Decimal(10000)
    assert db.get(Position, "SPY").qty == Decimal(2)


def test_position_drift_reported(db):
    b = FakeBroker()
    db.add(Position(symbol="AAPL", qty=1, avg_entry_price=1, market_value=1, unrealized_pl=0))
    db.flush()
    r = reconcile(db, b)
    assert any("AAPL" in d for d in r.discrepancies)
    assert db.get(Position, "AAPL") is None  # broker is source of truth


def test_partial_then_full_fill_progresses_state(db):
    b = FakeBroker()
    order = _local_order(db, "c1")
    b.submit_limit_order(OrderRequest("c1", "SPY", "buy", Decimal(10), Decimal(500)))
    b.set_status("c1", "partially_filled", filled="4", price="499.9")
    reconcile(db, b)
    assert order.state == OrderState.PARTIALLY_FILLED and order.filled_qty == Decimal(4)
    reconcile(db, b)  # no change -> no duplicate transition
    b.set_status("c1", "filled", filled="10", price="499.95")
    reconcile(db, b)
    assert order.state == OrderState.FILLED and order.filled_qty == Decimal(10)


def test_rejected_and_cancelled_orders(db):
    b = FakeBroker()
    o1, o2 = _local_order(db, "r1"), _local_order(db, "x1", OrderState.ACKNOWLEDGED)
    for cid in ("r1", "x1"):
        b.submit_limit_order(OrderRequest(cid, "SPY", "buy", Decimal(1), Decimal(1)))
    b.set_status("r1", "rejected")
    b.set_status("x1", "canceled")
    reconcile(db, b)
    assert o1.state == OrderState.REJECTED and o2.state == OrderState.CANCELLED


def test_order_unknown_to_broker_reported(db):
    _local_order(db, "ghost")
    r = reconcile(db, FakeBroker())
    assert any("ghost" in d for d in r.discrepancies)


def test_untracked_broker_order_reported(db):
    b = FakeBroker()
    b.submit_limit_order(OrderRequest("manual", "SPY", "buy", Decimal(1), Decimal(1)))
    r = reconcile(db, b)
    assert any("manual" in d for d in r.discrepancies)


def test_unknown_broker_status_reported(db):
    b = FakeBroker()
    _local_order(db, "u1")
    b.submit_limit_order(OrderRequest("u1", "SPY", "buy", Decimal(1), Decimal(1)))
    b.set_status("u1", "brand_new_status")
    r = reconcile(db, b)
    assert any("unknown status" in d for d in r.discrepancies)


def test_short_position_flagged(db):
    b = FakeBroker()
    b.positions = [PositionInfo("TSLA", Decimal(-1), Decimal(1), Decimal(-1), Decimal(0), None)]
    r = reconcile(db, b)
    assert any("SHORT" in d for d in r.discrepancies)


def test_refuses_non_paper_account(db):
    b = FakeBroker()
    b.account = AccountInfo(**{**b.account.__dict__, "account_number": "123", "is_paper": False})
    with pytest.raises(RuntimeError):
        reconcile(db, b)
