from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.backtesting.validation import params_hash
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import upsert_bars
from atlas.core.models.db import (
    AuditLog,
    EquityClose,
    Order,
    OrderEvent,
    OrderState,
    SignalRecord,
    StrategyStatus,
    TrackRecord,
    ValidationReport,
)
from atlas.core.performance import track_record as tr
from atlas.core.performance.account import account_performance
from atlas.core.performance.ledger import build_ledger
from atlas.core.risk.engine import evaluate
from atlas.core.strategies import registry
from tests.unit.test_strategies import series, uptrend

CAL = MarketCalendar()
D = Decimal
DAYS = CAL.sessions_between(date(2026, 1, 2), date(2026, 10, 23))


def _ts(day, hour=10):
    return datetime(day.year, day.month, day.day, hour, tzinfo=NY).astimezone(UTC)


def _order(
    db,
    *,
    side,
    qty,
    price,
    day,
    purpose,
    strategy="trend_breakout",
    symbol="AAA",
    signal_id=None,
    parent=None,
    stop=None,
    version="1.0.0",
):
    o = Order(
        client_order_id=f"c-{side}-{symbol}-{day}-{purpose}-{qty}-{price}",
        symbol=symbol,
        side=side,
        order_type="limit" if purpose != "protective_stop" else "stop",
        qty=D(qty),
        limit_price=D(price),
        stop_price=None if stop is None else D(stop),
        state=OrderState.FILLED if price is not None else OrderState.CANCELLED,
        strategy_id=strategy,
        strategy_version=version,
        filled_qty=D(qty) if price is not None else D(0),
        filled_avg_price=None if price is None else D(price),
        signal_id=signal_id,
        purpose=purpose,
        parent_order_id=parent,
        created_at=_ts(day, 9),
        updated_at=_ts(day, 15),
    )
    db.add(o)
    db.flush()
    if price is not None:
        db.add(OrderEvent(order_id=o.id, ts=_ts(day), from_state="ACKNOWLEDGED", to_state="FILLED"))
    db.flush()
    return o


def _signal(db, sid, stop):
    db.add(
        SignalRecord(
            id=sid,
            strategy_id="trend_breakout",
            strategy_version="1.0.0",
            symbol="AAA",
            kind="entry",
            side="buy",
            as_of=DAYS[0],
            ref_price=D(100),
            stop_price=None if stop is None else D(stop),
            reason={},
            mode="paper",
            status="ORDERED",
        )
    )
    db.flush()


# ---------- ledger ----------
def test_ledger_fifo_round_trips_with_r_multiples(db):
    _signal(db, "s1", 95)
    e1 = _order(db, side="buy", qty=10, price="100", day=DAYS[0], purpose="entry", signal_id="s1")
    e2 = _order(db, side="buy", qty=5, price="110", day=DAYS[2], purpose="entry")
    _order(
        db,
        side="sell",
        qty=4,
        price="0",
        day=DAYS[2],
        purpose="protective_stop",
        parent=e2.id,
        stop="104",
    )  # protective stop on e2; its price doubles as risk
    db.execute(  # it never filled: make it an open, unfilled stop
        Order.__table__.update()
        .where(Order.parent_order_id == e2.id)
        .values(filled_qty=D(0), filled_avg_price=None, state=OrderState.ACKNOWLEDGED)
    )
    _order(db, side="sell", qty=12, price="106", day=DAYS[5], purpose="exit")
    led = build_ledger(db)
    assert [(t.trade.qty, t.trade.entry_price, t.trade.exit_reason) for t in led.trades] == [
        (D(10), D(100), "signal"),
        (D(2), D(110), "signal"),
    ]
    first = led.trades[0].trade
    assert first.pnl == D(60) and first.r_multiple == pytest.approx(60 / 50)
    assert first.entry_date == DAYS[0] and first.exit_date == DAYS[5]
    assert led.trades[1].trade.risk_per_share == D(6)  # from the protective stop (110 - 104)
    assert [(lot.qty, lot.price) for lot in led.open_lots] == [(D(3), D(110))]
    assert e1.id != e2.id and led.unmatched_sell_qty == {}


def test_ledger_reports_unmatched_sells_and_skips_unpriced_fills(db):
    _order(db, side="sell", qty=3, price="50", day=DAYS[1], purpose="exit", symbol="ZZZ")
    o = _order(db, side="buy", qty=1, price="10", day=DAYS[1], purpose="entry", symbol="YYY")
    o.filled_avg_price = None
    db.flush()
    led = build_ledger(db)
    assert led.trades == [] and led.open_lots == []
    assert led.unmatched_sell_qty == {"trend_breakout/ZZZ": D(3)}


# ---------- account ----------
def test_account_performance_vs_spy(db):
    days = DAYS[-3:]
    for d, eq in zip(days, (10_000, 10_100, 10_050), strict=True):
        db.add(EquityClose(day=d, equity=D(eq), recorded_at=_ts(d, 16)))
    upsert_bars(db, series([100.0, 102.0, 101.0], symbol="SPY"))
    out = account_performance(db)
    assert out["sessions"] == 3 and out["metrics"]["total_return_pct"] == 0.5
    c = out["comparison"]
    assert c["account_return_pct"] == 0.5 and c["benchmark_return_pct"] == 1.0
    assert c["excess_return_pct"] == -0.5 and c["missing_benchmark_sessions"] == 0
    assert c["correlation"] is None  # two returns are too few


def test_account_performance_needs_two_closes(db):
    db.add(EquityClose(day=DAYS[-1], equity=D(10_000), recorded_at=_ts(DAYS[-1], 16)))
    out = account_performance(db)
    assert out["metrics"] is None and "two recorded" in out["note"]


# ---------- forward simulation ----------
def _report(db, policy, data_end, *, passed=True, avg_r=1.0, version="1.0.0"):
    strat = registry.STRATEGIES["trend_breakout"]
    params = strat.params.model_dump()
    r = ValidationReport(
        strategy_id="trend_breakout",
        version=version,
        params=params,
        params_hash=params_hash(params),
        target_status="PAPER",
        policy_sha256=policy.sha256,
        passed=passed,
        data_start=date(2016, 1, 4),
        data_end=data_end,
        symbols=["AAA", "SPY"],
        gates=[],
        metrics={"full": {"trades": 200, "sharpe": 0.8, "avg_r": avg_r, "profit_factor": 2.0}},
        equity_curve=[],
        caveats=[],
        runtime_seconds=D("1.0"),
    )
    db.add(r)
    db.flush()
    return r


def _row(db):
    return {r.id: r for r in registry.sync_registry(db)}["trend_breakout"]


def test_forward_sim_without_report_or_new_data(db, policy):
    row = _row(db)
    strat = registry.STRATEGIES["trend_breakout"]
    out = tr.forward_sim(db, strat, row, policy=policy, calendar=CAL, as_of=DAYS[-1])
    assert out["anchor_report_id"] is None and "no validation report" in out["note"]
    for sym in ("AAA", "SPY"):
        upsert_bars(db, series(uptrend(260), symbol=sym))
    rep = _report(db, policy, DAYS[-1])
    out = tr.forward_sim(db, strat, row, policy=policy, calendar=CAL, as_of=DAYS[-1])
    assert out["anchor_report_id"] == rep.id and "after the validation data" in out["note"]
    assert out["metrics"]["backtest_reference"]["avg_r"] == 1.0


def test_forward_sim_runs_only_after_the_validation_data(db, policy):
    # A breakout 10 sessions before the end that holds (a level shift, not a one-day spike).
    closes = [c + (3 if i >= 250 else 0) for i, c in enumerate(uptrend(260))]
    for sym in ("AAA", "SPY"):
        bars = series(closes, symbol=sym)
        upsert_bars(db, bars)  # adjusted: prices; raw: the point-in-time liquidity screen
        upsert_bars(db, [b.model_copy(update={"adjustment": "raw"}) for b in bars])
    rep = _report(db, policy, DAYS[-21])  # validation data ended 20 sessions before the last bar
    row = _row(db)
    out = tr.forward_sim(
        db,
        registry.STRATEGIES["trend_breakout"],
        row,
        policy=policy,
        calendar=CAL,
        as_of=DAYS[-1],
    )
    assert out["start"] == DAYS[-20] and out["as_of"] == DAYS[-1] and out["sessions"] == 20
    assert out["equity_curve"][0][0] == DAYS[-20].isoformat()
    assert out["anchor_report_id"] == rep.id
    m = out["metrics"]
    assert m["start_equity"] is not None and m["backtest_reference"]["report_id"] == rep.id
    # Open simulated positions are reported as such, not as closed trades.
    assert all(t["exit_reason"] != "end_of_test" for t in out["trades"])
    # The breakout after the validation data was traded; still held, so it is open, not a trade.
    assert {p["symbol"] for p in out["open_positions"]} == {"AAA", "SPY"}
    assert out["trades"] == [] and m["trades"] == 0 and "universe" not in m["rejections"]
    assert all(p["entry_date"] == DAYS[-9].isoformat() for p in out["open_positions"])


# ---------- paper record and the LIVE_CANDIDATE gate ----------
def _promote(db, when, version="1.0.0"):
    db.add(
        AuditLog(
            ts=when,
            actor="admin",
            action="strategy.status_changed",
            target="trend_breakout",
            details={"from": "RESEARCH", "to": "PAPER", "version": version},
        )
    )
    db.flush()


def _paper_trades(db, n, start_idx, win=True):
    for i in range(n):
        d0, d1 = DAYS[start_idx + 2 * i], DAYS[start_idx + 2 * i + 1]
        sid = f"sig{start_idx}-{i}"
        _signal(db, sid, 98)
        _order(
            db,
            side="buy",
            qty=10,
            price="100",
            day=d0,
            purpose="entry",
            signal_id=sid,
            symbol=f"S{i}",
        )
        _order(
            db,
            side="sell",
            qty=10,
            price="103" if win or i % 3 else "99",
            day=d1,
            purpose="exit",
            symbol=f"S{i}",
        )


def test_paper_record_without_promotion_fails_closed(db, policy):
    row = _row(db)
    rec = tr.paper_record(db, row, policy=policy, calendar=CAL, as_of=DAYS[-1])
    assert rec["passed"] is False and "no promotion" in rec["note"]
    assert {g["name"] for g in rec["gates"]} == {
        "paper_sessions",
        "paper_trades",
        "profit_factor",
        "drawdown",
        "expectancy_vs_backtest",
    }


def test_paper_record_gates(db, policy):
    _report(db, policy, DAYS[0], avg_r=1.0)
    _promote(db, _ts(DAYS[0], 12))
    _paper_trades(db, 25, 5, win=False)  # 2 in 3 win: +30, loss -10 every third
    row = _row(db)
    rec = tr.paper_record(db, row, policy=policy, calendar=CAL, as_of=DAYS[-1])
    gates = {g["name"]: g for g in rec["gates"]}
    assert rec["sessions"] == len(DAYS) - 1 and gates["paper_sessions"]["passed"]
    assert gates["paper_trades"]["value"] == 25 and gates["paper_trades"]["passed"]
    assert gates["profit_factor"]["passed"] and gates["drawdown"]["passed"]
    # avg R: (16 x 1.5 + 9 x -0.5) / 25 = 0.78 >= 0.5 x 1.0
    assert gates["expectancy_vs_backtest"]["value"] == pytest.approx(0.78)
    assert rec["passed"] is True
    # Trades before the promotion, or of another version, don't count.
    assert all(t["entry_date"] >= DAYS[0].isoformat() for t in rec["trades"])


def test_paper_record_expectancy_far_below_backtest_fails(db, policy):
    _report(db, policy, DAYS[0], avg_r=4.0)
    _promote(db, _ts(DAYS[0], 12))
    _paper_trades(db, 25, 5, win=False)
    rec = tr.paper_record(db, _row(db), policy=policy, calendar=CAL, as_of=DAYS[-1])
    gates = {g["name"]: g for g in rec["gates"]}
    assert not gates["expectancy_vs_backtest"]["passed"] and rec["passed"] is False
    assert "(2.0)" in gates["expectancy_vs_backtest"]["threshold"]


def test_promotion_of_another_version_does_not_count(db):
    _promote(db, _ts(DAYS[0], 12), version="0.9.0")
    assert tr.paper_since(db, "trend_breakout", "1.0.0") is None


def test_live_candidate_promotion_requires_a_passing_record(db, policy):
    row = _row(db)
    row.status = StrategyStatus.PAPER
    db.flush()
    with pytest.raises(registry.StatusChangeRefused, match="paper track record"):
        registry.set_status(
            db, "trend_breakout", StrategyStatus.LIVE_CANDIDATE, actor="admin", reason="test"
        )
    _report(db, policy, DAYS[0], avg_r=1.0)
    _promote(db, _ts(DAYS[0], 12))
    _paper_trades(db, 25, 5, win=False)
    rec = tr.paper_record(db, row, policy=policy, calendar=CAL, as_of=DAYS[-1])
    stored = tr.store(db, row, rec, policy=policy, as_of=DAYS[-1], now=datetime.now(UTC))
    assert tr.passing_track_record(db, "trend_breakout", policy) == str(stored.id)
    registry.set_status(
        db, "trend_breakout", StrategyStatus.LIVE_CANDIDATE, actor="admin", reason="record ok"
    )
    entry = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert entry.details["track_record"] == str(stored.id)
    # An old record no longer qualifies.
    stored.created_at = datetime.now(UTC) - timedelta(days=8)
    db.flush()
    assert tr.passing_track_record(db, "trend_breakout", policy) is None


def test_live_candidate_keeps_paper_trading_and_research_does_not(policy):
    from tests.unit.test_risk_engine import ENTRY, ctx

    lc = evaluate(ENTRY, ctx(strategy_status=StrategyStatus.LIVE_CANDIDATE), policy.policy, CAL)
    assert "strategy_status" not in lc.failed
    research = evaluate(ENTRY, ctx(strategy_status=StrategyStatus.RESEARCH), policy.policy, CAL)
    assert "strategy_status" in research.failed


def test_update_track_records_is_idempotent_per_session(db, policy):
    for sym in ("AAA", "SPY"):
        upsert_bars(db, series(uptrend(260), symbol=sym))
    _report(db, policy, DAYS[-6])
    rows = registry.sync_registry(db)
    rows[1].status = StrategyStatus.PAPER  # trend_breakout
    _promote(db, _ts(DAYS[-6], 12))
    db.flush()
    kw = dict(
        strategies=registry.STRATEGIES, rows=rows, policy=policy, calendar=CAL, as_of=DAYS[-1]
    )
    first = tr.update_track_records(db, now=datetime.now(UTC), **kw)
    assert set(first) == {"rsi_pullback", "trend_breakout"}
    assert "paper" in first["trend_breakout"] and "paper" not in first["rsi_pullback"]
    assert first["trend_breakout"]["passed"] is False
    again = tr.update_track_records(db, now=datetime.now(UTC), **kw)
    assert again["trend_breakout"] == first["trend_breakout"]
    assert len(db.scalars(select(TrackRecord)).all()) == 3
