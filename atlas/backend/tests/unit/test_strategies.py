from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import AuditLog, StrategyRecord, StrategyStatus
from atlas.core.strategies import registry
from atlas.core.strategies.base import OpenPosition, Signal, Strategy
from atlas.core.strategies.baselines import RsiPullback, TrendBreakout

CAL = MarketCalendar()
DAYS = CAL.sessions_between(date(2025, 6, 1), date(2026, 10, 23))
AS_OF = DAYS[-1]


def series(closes, symbol="AAA", spread=0.5):
    days = DAYS[-len(closes) :]
    return [
        BarRecord(
            symbol=symbol,
            timeframe="1Day",
            ts=datetime(d.year, d.month, d.day, tzinfo=NY),
            open=Decimal(str(c)),
            high=Decimal(str(round(c + spread, 4))),
            low=Decimal(str(round(c - spread, 4))),
            close=Decimal(str(c)),
            volume=Decimal(1_000_000),
            source="t",
            adjustment="all",
        )
        for d, c in zip(days, closes, strict=True)
    ]


def uptrend(n=260, start=100.0, step=0.1):
    return [round(start + step * i, 4) for i in range(n)]


def pos(sessions_held=1):
    return OpenPosition(Decimal(10), Decimal(100), DAYS[-1 - sessions_held], sessions_held)


# ---------- trend breakout ----------
def test_breakout_entry_with_atr_stop():
    closes = uptrend()
    closes[-1] = closes[-2] + 3  # clears the prior 55-day high (prev high = closes[-2] + 0.5)
    sig = TrendBreakout().decide("AAA", series(closes), None)
    assert sig is not None and sig.kind == "entry" and sig.side == "buy"
    assert sig.as_of == AS_OF and sig.ref_price == Decimal(str(closes[-1]))
    assert sig.stop_price < sig.ref_price
    assert set(sig.reason) >= {"breakout_level", "sma_trend", "atr"}
    # stop = close - 2 x ATR, to the cent
    assert sig.stop_price == Decimal(str(round(closes[-1] - 2 * sig.reason["atr"], 2)))


def test_breakout_needs_uptrend_and_new_high():
    down = [round(200 - 0.1 * i, 4) for i in range(260)]
    down[-1] = down[-2] + 3  # a pop, but below the 55-day high and the 200-day SMA
    assert TrendBreakout().decide("AAA", series(down), None) is None
    assert TrendBreakout().decide("AAA", series(uptrend()), None) is None  # no new high


def test_breakout_exit_below_prior_low():
    closes = uptrend()
    closes[-1] = closes[-21] - 5
    sig = TrendBreakout().decide("AAA", series(closes), pos())
    assert sig is not None and sig.kind == "exit" and sig.side == "sell"
    assert TrendBreakout().decide("AAA", series(uptrend()), pos()) is None  # holds otherwise


# ---------- RSI pullback ----------
def test_rsi_pullback_entry_in_uptrend():
    closes = uptrend(step=0.2)
    closes[-2] = closes[-3] - 1.5
    closes[-1] = closes[-2] - 1.5  # two down days: RSI(2) collapses, still above 200-SMA
    sig = RsiPullback().decide("AAA", series(closes), None)
    assert sig is not None and sig.kind == "entry" and sig.reason["rsi"] < 10
    assert sig.stop_price < sig.ref_price


def test_rsi_pullback_exits():
    closes = uptrend(step=0.2)
    sig = RsiPullback().decide("AAA", series(closes), pos())
    assert sig is not None and sig.reason["rule"] == "above_exit_sma"
    flat_below = uptrend(step=0.2)
    flat_below[-1] = flat_below[-2] - 2  # below the 5-day SMA: keep holding...
    assert RsiPullback().decide("AAA", series(flat_below), pos(3)) is None
    held = RsiPullback().decide("AAA", series(flat_below), pos(10))  # ...until max hold
    assert held is not None and held.reason["rule"] == "max_hold"


# ---------- framework ----------
def test_generate_skips_unusable_data_and_never_looks_ahead():
    good = uptrend()
    good[-1] = good[-2] + 3
    stale = series(uptrend())[:-1]  # last bar is the day before as_of
    short = series(uptrend(50))
    broken = series(uptrend())
    broken[-5] = broken[-5].model_copy(update={"high": Decimal("1")})  # high < close
    future = [
        *series(good),
        series([999.0], symbol="AAA")[0].model_copy(
            update={"ts": datetime(2026, 10, 26, tzinfo=NY)}
        ),
    ]
    sigs, skipped = TrendBreakout().generate(
        AS_OF, {"AAA": future, "STALE": stale, "SHORT": short, "BROKEN": broken}, {}
    )
    assert [s.symbol for s in sigs] == ["AAA"] and sigs[0].ref_price != Decimal("999.0")
    assert skipped == {
        "STALE": "no_bar_for_session",
        "SHORT": "insufficient_history",
        "BROKEN": "bad_data:ohlc_inconsistent",
    }


def test_entry_without_valid_stop_is_a_bug():
    class NoStop(TrendBreakout):
        def decide(self, symbol, bars, position):
            return self.signal(symbol, "entry", bars, stop=float(bars[-1].close) + 1)

    with pytest.raises(ValueError, match="without a valid stop"):
        NoStop().generate(AS_OF, {"AAA": series(uptrend())}, {})


def test_signal_id_is_deterministic():
    a = Signal("s", "1", "AAA", "entry", AS_OF, Decimal(1), Decimal("0.5"))
    b = Signal("s", "1", "AAA", "entry", AS_OF, Decimal(2), Decimal("0.4"))
    assert a.id == b.id and len(a.id) == 32
    assert a.id != Signal("s", "2", "AAA", "entry", AS_OF, Decimal(1)).id


# ---------- registry ----------
def test_registry_sync_and_gated_promotion(db):
    rows = registry.sync_registry(db)
    assert [(r.id, r.status) for r in rows] == [
        ("rsi_pullback", StrategyStatus.RESEARCH),
        ("trend_breakout", StrategyStatus.RESEARCH),
    ]
    with pytest.raises(registry.StatusChangeRefused, match="validation report"):
        registry.set_status(db, "trend_breakout", StrategyStatus.PAPER, actor="admin", reason="go")
    with pytest.raises(registry.StatusChangeRefused, match="not allowed"):
        registry.set_status(
            db, "trend_breakout", StrategyStatus.LIVE_CANDIDATE, actor="admin", reason="skip ahead"
        )
    with pytest.raises(registry.StatusChangeRefused, match="reason"):
        registry.set_status(db, "trend_breakout", StrategyStatus.RETIRED, actor="admin", reason=" ")
    registry.set_status(db, "trend_breakout", StrategyStatus.RETIRED, actor="admin", reason="pause")
    registry.set_status(db, "trend_breakout", StrategyStatus.RESEARCH, actor="admin", reason="back")
    with pytest.raises(LookupError):
        registry.set_status(db, "nope", StrategyStatus.RETIRED, actor="admin", reason="x")
    actions = db.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
    assert actions.count("strategy.registered") == 2
    assert actions.count("strategy.status_changed") == 2


def test_registry_demotes_changed_code_and_retires_removed(db, monkeypatch):
    registry.sync_registry(db)
    row = db.get(StrategyRecord, "rsi_pullback")
    row.status = StrategyStatus.PAPER  # as if it had been promoted
    row.version = "0.9.0"  # ...for an older version of the code
    db.add(StrategyRecord(id="old_one", version="1", status=StrategyStatus.PAPER, params={}))
    db.flush()
    registry.sync_registry(db)
    assert db.get(StrategyRecord, "rsi_pullback").status == StrategyStatus.RESEARCH
    assert db.get(StrategyRecord, "rsi_pullback").version == "1.0.0"
    assert db.get(StrategyRecord, "old_one").status == StrategyStatus.RETIRED


def test_strategies_are_long_only_and_abstract():
    assert all(isinstance(s, Strategy) for s in registry.STRATEGIES.values())
    assert Signal("s", "1", "A", "exit", AS_OF, Decimal(1)).side == "sell"
