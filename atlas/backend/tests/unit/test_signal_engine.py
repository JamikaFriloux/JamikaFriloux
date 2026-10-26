from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import upsert_bars
from atlas.core.execution.pipeline import is_transient
from atlas.core.models.db import SignalRecord, UniverseMember, UniverseSnapshot, Watchlist
from atlas.core.strategies.engine import generate_signals
from tests.unit.test_strategies import series, uptrend

CAL = MarketCalendar()
AS_OF = date(2026, 10, 23)


def test_is_transient():
    assert is_transient(("quote", "size", "spread"))  # size failed only because no quote
    assert is_transient(("entry_window",))
    assert not is_transient(("quote", "universe"))
    assert not is_transient(("size",))  # a real sizing limit is final
    assert not is_transient(())


def _seed(db, symbols=("AAA", "BBB", "OUT")):
    breakout = uptrend()
    breakout[-1] = breakout[-2] + 3
    for sym in symbols:
        upsert_bars(db, series(breakout if sym != "BBB" else uptrend(), symbol=sym))
    snap = UniverseSnapshot(
        as_of=AS_OF, source="t", criteria={}, assets_seen=2, member_count=2, exclusions={}
    )
    db.add(snap)
    db.flush()
    for sym in ("AAA", "BBB"):  # OUT is not in the universe
        db.add(
            UniverseMember(
                snapshot_id=snap.id,
                symbol=sym,
                name=sym,
                exchange="NYSE",
                last_close=Decimal(100),
                adv_usd=Decimal("1e8"),
                sessions=20,
                fractionable=True,
                shortable=False,
                easy_to_borrow=False,
            )
        )
    db.add(Watchlist(name="w", symbols=list(symbols)))
    db.flush()


def test_engine_scopes_to_universe_and_is_idempotent(db):
    _seed(db)
    summary = generate_signals(db, as_of=AS_OF, default_symbols=[], calendar=CAL)
    assert summary["scope"] == 2 and summary["universe_as_of"] == "2026-10-23"
    tb = summary["strategies"]["trend_breakout"]
    assert tb["status"] == "RESEARCH" and tb["new"] == 1
    sigs = db.scalars(select(SignalRecord)).all()
    assert [(s.symbol, s.kind, s.mode, s.status) for s in sigs] == [
        ("AAA", "entry", "shadow", "NEW")
    ]
    assert sigs[0].stop_price < sigs[0].ref_price and "breakout_level" in sigs[0].reason
    again = generate_signals(db, as_of=AS_OF, default_symbols=[], calendar=CAL)
    assert again["strategies"]["trend_breakout"]["new"] == 0
    assert len(db.scalars(select(SignalRecord)).all()) == 1


def test_engine_without_universe_produces_nothing(db):
    upsert_bars(db, series(uptrend(), symbol="AAA"))
    summary = generate_signals(db, as_of=AS_OF, default_symbols=["AAA"], calendar=CAL)
    assert summary["scope"] == 0 and summary["universe_as_of"] is None
    assert db.scalars(select(SignalRecord)).all() == []


def test_worker_task_skips_days_without_a_session():
    from atlas.apps.worker import tasks

    saturday = datetime(2026, 10, 24, 18, tzinfo=NY).astimezone(UTC)
    with patch.object(tasks, "datetime") as dt:
        dt.now.return_value = saturday
        assert tasks.generate_signals.run() == {"ok": True, "skipped": "no session closed today"}


def test_execute_task_skips_closed_market_and_alerts_on_failure():
    from atlas.apps.executor import tasks
    from tests.fakes import RecordingNotifier

    saturday = datetime(2026, 10, 24, 11, tzinfo=NY).astimezone(UTC)
    with patch.object(tasks, "datetime") as dt:
        dt.now.return_value = saturday
        assert tasks.execute_signals.run()["skipped"] == "market closed"

    notifier = RecordingNotifier()
    open_ = datetime(2026, 10, 22, 10, tzinfo=NY).astimezone(UTC)

    def no_gateway():
        raise RuntimeError("no credentials")

    from contextlib import contextmanager

    @contextmanager
    def scope():
        yield None  # beat is patched; nothing touches the session

    with (
        patch.object(tasks, "datetime") as dt,
        patch.object(tasks, "get_gateway", no_gateway),
        patch.object(tasks, "build_notifier", lambda: notifier),
        patch.object(tasks, "beat", lambda *a, **k: None),
        patch.object(tasks, "session_scope", scope),
    ):
        dt.now.return_value = open_
        assert tasks.execute_signals.run() == {"ok": False, "error": "RuntimeError"}
    assert "[PAPER TRADING] Signal execution failed" in notifier.messages[0][0]


def test_held_symbol_outside_universe_still_gets_exits(db):
    from atlas.core.models.db import Order, OrderState, StrategyRecord, StrategyStatus
    from atlas.core.strategies.registry import sync_registry

    _seed(db)
    sync_registry(db)
    db.get(StrategyRecord, "trend_breakout").status = StrategyStatus.PAPER
    # Held in GONE, which is in neither the universe nor any watchlist, and is breaking down.
    falling = uptrend()
    falling[-1] = falling[-21] - 10
    upsert_bars(db, series(falling, symbol="GONE"))
    db.add(
        Order(
            client_order_id="x1",
            symbol="GONE",
            side="buy",
            order_type="limit",
            qty=Decimal(5),
            limit_price=Decimal(100),
            state=OrderState.FILLED,
            filled_qty=Decimal(5),
            filled_avg_price=Decimal(100),
            strategy_id="trend_breakout",
            purpose="entry",
            submitted_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
        )
    )
    db.flush()
    summary = generate_signals(db, as_of=AS_OF, default_symbols=[], calendar=CAL)
    assert summary["held_outside_scope"] == ["GONE"]
    sigs = {(s.symbol, s.kind) for s in db.scalars(select(SignalRecord)).all()}
    assert ("GONE", "exit") in sigs and ("OUT", "entry") not in sigs
