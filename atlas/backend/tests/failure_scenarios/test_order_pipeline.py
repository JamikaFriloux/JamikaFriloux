"""Signal -> risk -> order -> protective stop -> exit, against the FakeBroker."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.execution.broker import BrokerRejected, BrokerUncertain
from atlas.core.execution.pipeline import ExecutionDeps, process_pending_signals
from atlas.core.execution.protection import (
    cancel_orphan_stops,
    ensure_protection,
    protective_stop_ids,
)
from atlas.core.models.db import (
    AccountSnapshot,
    KillSwitch,
    Order,
    OrderEvent,
    OrderState,
    Position,
    RiskDecision,
    SignalRecord,
    StrategyRecord,
    StrategyStatus,
    UniverseMember,
    UniverseSnapshot,
)
from atlas.core.risk.engine import QuoteState
from atlas.core.strategies.registry import sync_registry
from tests.fakes import FakeBroker

CAL = MarketCalendar()
NOW = datetime(2026, 10, 22, 10, 0, tzinfo=NY)  # Thursday 10:00
AS_OF = date(2026, 10, 21)  # Wednesday's close produced the signal
D = Decimal


def setup(db, status=StrategyStatus.PAPER, engaged=False, positions=()):
    db.get(KillSwitch, 1).engaged = engaged
    sync_registry(db)
    db.get(StrategyRecord, "trend_breakout").status = status
    db.add(
        AccountSnapshot(
            ts=(NOW - timedelta(seconds=30)).astimezone(UTC),
            source="t",
            is_paper=True,
            account_status="ACTIVE",
            equity=D(100_000),
            last_equity=D(100_000),
            cash=D(100_000),
            buying_power=D(200_000),
            long_market_value=D(0),
            trading_blocked=False,
            shorting_enabled=False,
        )
    )
    snap = UniverseSnapshot(
        as_of=AS_OF, source="t", criteria={}, assets_seen=2, member_count=2, exclusions={}
    )
    db.add(snap)
    db.flush()
    for sym in ("AAA", "BBB"):
        db.add(
            UniverseMember(
                snapshot_id=snap.id,
                symbol=sym,
                name=sym,
                exchange="NYSE",
                last_close=D(100),
                adv_usd=D("1e8"),
                sessions=20,
                fractionable=True,
                shortable=False,
                easy_to_borrow=False,
            )
        )
    for sym, qty in positions:
        db.add(
            Position(
                symbol=sym,
                qty=D(qty),
                avg_entry_price=D(100),
                market_value=D(qty) * 100,
                unrealized_pl=D(0),
            )
        )
    db.commit()


def signal(db, kind="entry", symbol="AAA", as_of=AS_OF, mode="paper", stop="98"):
    rec = SignalRecord(
        id=f"{kind}{symbol}{as_of:%m%d}".ljust(32, "0"),
        strategy_id="trend_breakout",
        strategy_version="1.0.0",
        symbol=symbol,
        kind=kind,
        side="buy" if kind == "entry" else "sell",
        as_of=as_of,
        ref_price=D(100),
        stop_price=D(stop) if kind == "entry" else None,
        reason={},
        mode=mode,
        status="NEW",
    )
    db.add(rec)
    db.commit()
    return rec


def quote(bid="99.98", ask="100.00", at=None):
    return lambda _s: QuoteState(D(bid), D(ask), (at or NOW) - timedelta(seconds=1))


def deps(broker, q=None, earnings=False):
    return ExecutionDeps(
        gateway=broker,
        quote_for=q or quote(),
        earnings_blackout=lambda _s: earnings,
        sleep=lambda _x: None,
    )


@pytest.fixture(autouse=True)
def _policy(policy):
    global POLICY
    POLICY = policy.policy


def run(db, d, now=NOW):
    return process_pending_signals(db, d, now=now, policy=POLICY, calendar=CAL)


def test_paper_entry_is_risk_checked_sized_and_submitted_once(db):
    setup(db)
    rec = signal(db)
    broker = FakeBroker()
    out = run(db, deps(broker))
    assert [(o.status, o.mode) for o in out] == [("ORDERED", "paper")]
    order = db.scalars(select(Order)).one()
    assert order.client_order_id == f"atl-{rec.id[:20]}-e" and order.purpose == "entry"
    assert (order.qty, order.limit_price, order.time_in_force) == (D(9), D("100.05"), "day")
    assert order.state == OrderState.ACKNOWLEDGED and order.broker_order_id
    events = db.scalars(select(OrderEvent.to_state).order_by(OrderEvent.id)).all()
    assert events == ["VALIDATED", "RISK_APPROVED", "SUBMITTED", "ACKNOWLEDGED"]
    decision = db.scalars(select(RiskDecision)).one()
    assert decision.approved and decision.mode == "paper" and decision.capital_base == D(10_000)
    # Re-running (even if the signal were reset) never submits a second order.
    db.get(SignalRecord, rec.id).status = "NEW"
    db.commit()
    run(db, deps(broker))
    assert broker.submit_calls == 1


def test_research_strategy_signal_is_shadow_evaluated_never_ordered(db):
    setup(db, status=StrategyStatus.RESEARCH)
    signal(db, mode="shadow")
    broker = FakeBroker()
    out = run(db, deps(broker))
    assert out[0].status == "SHADOWED" and broker.submit_calls == 0
    d = db.scalars(select(RiskDecision)).one()
    assert d.mode == "shadow" and d.approved  # it *would* have passed


def test_missing_earnings_calendar_rejects_entries(db):
    setup(db)
    signal(db)
    broker = FakeBroker()
    out = run(db, deps(broker, earnings=None))
    assert out[0].status == "REJECTED" and "earnings_blackout" in out[0].failed
    assert broker.submit_calls == 0 and db.scalars(select(Order)).all() == []
    assert db.scalars(select(RiskDecision)).one().failed == ["earnings_blackout"]


def test_transient_failures_retry_then_reject_at_window_end(db):
    setup(db)
    rec = signal(db)
    broker = FakeBroker()
    out = run(db, deps(broker, q=lambda _s: None))
    assert out[0].status == "PENDING" and db.get(SignalRecord, rec.id).status == "NEW"
    assert db.scalars(select(RiskDecision)).all() == []  # nothing final yet
    late = datetime(2026, 10, 22, 15, 50, tzinfo=NY)
    db.add(
        AccountSnapshot(
            ts=(late - timedelta(seconds=10)).astimezone(UTC),
            source="t",
            is_paper=True,
            account_status="ACTIVE",
            equity=D(100_000),
            last_equity=D(100_000),
            cash=D(100_000),
            buying_power=D(1),
            long_market_value=D(0),
            trading_blocked=False,
            shorting_enabled=False,
        )
    )
    db.commit()
    out = run(db, deps(broker, q=lambda _s: None), now=late)
    assert out[0].status == "REJECTED"
    assert set(db.scalars(select(RiskDecision)).one().failed) >= {"quote", "entry_window"}


def test_old_signals_expire_and_closed_market_does_nothing(db):
    setup(db)
    old = signal(db, as_of=date(2026, 10, 19))
    broker = FakeBroker()
    saturday = datetime(2026, 10, 24, 11, tzinfo=NY)
    assert run(db, deps(broker), now=saturday) == []
    out = run(db, deps(broker))
    assert [o.status for o in out] == ["EXPIRED"] and db.get(
        SignalRecord, old.id
    ).status == "EXPIRED"


def test_kill_switch_blocks_new_orders(db):
    setup(db, engaged=True)
    signal(db)
    broker = FakeBroker()
    out = run(db, deps(broker))
    assert out[0].status == "REJECTED" and "kill_switch" in out[0].failed
    assert broker.submit_calls == 0


def test_broker_rejection_marks_order_and_signal(db):
    setup(db)
    rec = signal(db)
    broker = FakeBroker()

    def reject(_req):
        raise BrokerRejected("insufficient buying power")

    broker.on_submit = [reject]
    run(db, deps(broker))
    order = db.scalars(select(Order)).one()
    assert order.state == OrderState.REJECTED and "buying power" in order.last_error
    assert db.get(SignalRecord, rec.id).status == "REJECTED"


def test_lost_response_is_resolved_by_lookup_not_resubmission(db):
    setup(db)
    signal(db)
    broker = FakeBroker()
    broker.accept_then_fail = True  # the broker accepts, then the response is lost

    def lose_response(_req):
        raise BrokerUncertain("timeout")

    broker.on_submit = [lose_response]
    out = run(db, deps(broker))
    order = db.scalars(select(Order)).one()
    assert out[0].status == "ORDERED" and order.state == OrderState.ACKNOWLEDGED
    assert broker.submit_calls == 1  # found by client order id, never sent twice


def _filled_entry(db, broker, qty="9"):
    """Run a paper entry and fill it at the broker and locally."""
    setup(db)
    rec = signal(db)
    run(db, deps(broker))
    order = db.scalars(select(Order).where(Order.purpose == "entry")).one()
    db.add(
        Position(
            symbol="AAA",
            qty=D(qty),
            avg_entry_price=D("100.05"),
            market_value=D(qty) * 100,
            unrealized_pl=D(0),
        )
    )
    broker.set_status(order.client_order_id, "filled", filled=qty, price="100.05")
    order.filled_qty, order.filled_avg_price = D(qty), D("100.05")
    order.state = OrderState.FILLED
    db.commit()
    return rec, order


def test_filled_entry_gets_one_gtc_protective_stop(db):
    broker = FakeBroker()
    _, entry = _filled_entry(db, broker)
    acts = ensure_protection(db, broker, NOW)
    db.commit()
    assert [(a.qty, a.stop_price, a.outcome) for a in acts] == [(D(9), D(98), "submitted")]
    stop = db.scalars(select(Order).where(Order.purpose == "protective_stop")).one()
    req = broker.requests[stop.client_order_id]
    assert (req.order_type, req.time_in_force, req.side, req.stop_price) == (
        "stop",
        "gtc",
        "sell",
        D(98),
    )
    assert stop.parent_order_id == entry.id and stop.client_order_id in protective_stop_ids(db)
    assert ensure_protection(db, broker, NOW) == []  # already covered: no duplicate


def test_protection_allowed_while_kill_switch_engaged(db):
    broker = FakeBroker()
    _filled_entry(db, broker)
    db.get(KillSwitch, 1).engaged = True
    db.commit()
    assert [a.outcome for a in ensure_protection(db, broker, NOW)] == ["submitted"]


def test_exit_releases_stop_then_sells(db):
    broker = FakeBroker()
    _filled_entry(db, broker)
    ensure_protection(db, broker, NOW)
    db.commit()
    signal(db, kind="exit")
    out = run(db, deps(broker))
    assert [o.status for o in out if o.kind == "exit"] == ["ORDERED"]
    stop = db.scalars(select(Order).where(Order.purpose == "protective_stop")).one()
    exit_order = db.scalars(select(Order).where(Order.purpose == "exit")).one()
    assert stop.state == OrderState.CANCELLED and stop.client_order_id in broker.cancelled
    assert (exit_order.side, exit_order.qty, exit_order.limit_price) == ("sell", D(9), D("99.93"))
    assert ensure_protection(db, broker, NOW) == []  # the working exit owns the shares


def test_exit_waits_if_stop_cancel_not_confirmed(db):
    broker = FakeBroker()
    _filled_entry(db, broker)
    ensure_protection(db, broker, NOW)
    db.commit()
    rec = signal(db, kind="exit")
    broker.cancel_error = BrokerUncertain("timeout")
    run(db, deps(broker))
    assert db.get(SignalRecord, rec.id).status == "NEW"  # retried next run
    assert db.scalars(select(Order).where(Order.purpose == "exit")).all() == []
    stop = db.scalars(select(Order).where(Order.purpose == "protective_stop")).one()
    assert broker.orders[stop.client_order_id].status == "new"  # still protected


def test_exit_skipped_when_stop_already_filled(db):
    broker = FakeBroker()
    _filled_entry(db, broker)
    ensure_protection(db, broker, NOW)
    db.commit()
    stop = db.scalars(select(Order).where(Order.purpose == "protective_stop")).one()
    broker.set_status(stop.client_order_id, "filled", filled="9", price="97.90")
    rec = signal(db, kind="exit")
    run(db, deps(broker))
    assert db.get(SignalRecord, rec.id).status == "STOPPED_OUT"
    assert db.scalars(select(Order).where(Order.purpose == "exit")).all() == []


def test_orphan_stops_cancelled_when_position_disappears(db):
    broker = FakeBroker()
    _filled_entry(db, broker)
    ensure_protection(db, broker, NOW)
    db.commit()
    stop = db.scalars(select(Order).where(Order.purpose == "protective_stop")).one()
    # The position was closed outside ATLAS (e.g. manually in the broker's dashboard).
    db.query(Position).delete()
    db.commit()
    assert cancel_orphan_stops(db, broker, sleep=lambda _x: None) == [stop.client_order_id]
    assert (
        stop.state == OrderState.CANCELLED
        and broker.orders[stop.client_order_id].status == "canceled"
    )
    assert ensure_protection(db, broker, NOW) == []  # nothing held, nothing to protect


def test_matching_stops_are_left_alone(db):
    broker = FakeBroker()
    _filled_entry(db, broker)
    ensure_protection(db, broker, NOW)
    db.commit()
    assert cancel_orphan_stops(db, broker, sleep=lambda _x: None) == []


def test_drawdown_cooldown_blocks_entries_in_production(db):
    from atlas.core.models.db import EquityClose

    setup(db)
    prior = CAL.sessions_between(date(2026, 10, 1), date(2026, 10, 21))
    # Peak 100,500 then a close 500 below it on Oct 20 -> halted; Oct 22 is cooldown session 2.
    for d in prior:
        eq = D(100_500) if d < date(2026, 10, 20) else D(100_000)
        db.add(
            EquityClose(
                day=d, equity=eq, recorded_at=datetime(d.year, d.month, d.day, 21, tzinfo=UTC)
            )
        )
    db.commit()
    signal(db)
    out = run(db, deps(FakeBroker()))
    assert out[0].status == "REJECTED" and out[0].failed == ("drawdown",)
    d = db.scalars(select(RiskDecision)).one()
    assert "cooldown, 19 sessions left" in next(
        c["detail"] for c in d.checks if c["name"] == "drawdown"
    )


@pytest.mark.parametrize(("bbb_sector", "approved"), [("tech", False), ("energy", True)])
def test_sector_budget_counts_only_the_same_sector(db, bbb_sector, approved):
    # Capital base $10k, sector cap 25% = $2,500. BBB holds $2,400.
    setup(db, positions=[("BBB", "24")])
    signal(db)
    sectors = {"AAA": "tech", "BBB": bbb_sector}
    d = deps(FakeBroker())
    d.sector_for = lambda s: sectors.get(s, "unknown")
    out = run(db, d)
    decision = db.scalars(select(RiskDecision)).one()
    size = next(c for c in decision.checks if c["name"] == "size")
    assert "sector tech" in size["detail"]
    if approved:
        assert out[0].status == "ORDERED" and decision.qty > 0
    else:
        assert out[0].status == "REJECTED" and "binding: sector_exposure" in size["detail"]
