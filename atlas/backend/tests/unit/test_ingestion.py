from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import (
    expected_latest_bar,
    ingest_bars,
    ingestion_symbols,
    latest_stored,
    upsert_bars,
)
from atlas.core.models.db import Bar, DataQualityReport, Watchlist
from tests.fakes import FakeBarSource, make_bar

CAL = MarketCalendar()
# Thursday 2026-10-22, 15:00 New York: the market is open, the day's session is not complete.
NOW_OPEN = datetime(2026, 10, 22, 15, 0, tzinfo=NY)
YEAR = timedelta(days=400)


def daily(day: int, close: str = "100", symbol: str = "SPY", **kw):
    return make_bar(symbol, datetime(2026, 10, day, tzinfo=NY), "1Day", close, **kw)


def minute(hh: int, mm: int, symbol: str = "SPY", close: str = "100"):
    return make_bar(symbol, datetime(2026, 10, 22, hh, mm, tzinfo=NY), "1Min", close)


def run(db, source, symbols=("SPY",), tf="1Day", now=NOW_OPEN, **kw):
    kw.setdefault("lookback", YEAR if tf == "1Day" else timedelta(days=5))
    kw.setdefault("incremental", tf == "1Min")
    return ingest_bars(db, source, list(symbols), tf, now=now, calendar=CAL, **kw)


def test_expected_latest_daily_is_last_completed_session():
    assert expected_latest_bar("1Day", NOW_OPEN, CAL) == datetime(2026, 10, 21, tzinfo=NY)
    after_close = datetime(2026, 10, 22, 16, 1, tzinfo=NY)
    assert expected_latest_bar("1Day", after_close, CAL) == datetime(2026, 10, 22, tzinfo=NY)
    # Saturday: Friday's session.
    sat = datetime(2026, 10, 24, 12, tzinfo=NY)
    assert expected_latest_bar("1Day", sat, CAL) == datetime(2026, 10, 23, tzinfo=NY)


def test_expected_latest_minute():
    now = datetime(2026, 10, 22, 10, 0, 30, tzinfo=NY)
    assert expected_latest_bar("1Min", now, CAL) == datetime(2026, 10, 22, 9, 59, tzinfo=NY)
    # In the first minute of the session the previous session's last minute is expected.
    first = datetime(2026, 10, 22, 9, 30, 20, tzinfo=NY)
    assert expected_latest_bar("1Min", first, CAL) == datetime(2026, 10, 21, 15, 59, tzinfo=NY)
    night = datetime(2026, 10, 22, 21, 0, tzinfo=NY)
    assert expected_latest_bar("1Min", night, CAL) == datetime(2026, 10, 22, 15, 59, tzinfo=NY)


def test_unsupported_timeframe_rejected(db):
    with pytest.raises(ValueError):
        ingest_bars(db, FakeBarSource(), ["SPY"], "5Min", now=NOW_OPEN, lookback=YEAR,
                    incremental=False)  # fmt: skip


def test_daily_ingest_stores_complete_bars_and_drops_partial_session(db):
    src = FakeBarSource({"SPY": [daily(19), daily(20), daily(21), daily(22, "105")]})
    result = run(db, src)
    assert result.ok and result.bars_written == 3
    stored = db.scalars(select(Bar).order_by(Bar.ts)).all()
    assert [b.ts.replace(tzinfo=UTC).astimezone(NY).day for b in stored] == [19, 20, 21]
    report = db.scalars(select(DataQualityReport)).one()
    assert report.ok and not report.stale and report.bars_fetched == 4
    assert report.source == "fake_feed" and report.issues == []


def test_reingest_is_idempotent_and_updates_revised_values(db):
    src = FakeBarSource({"SPY": [daily(20), daily(21)]})
    run(db, src)
    src.bars["SPY"] = [daily(20), daily(21, "101.5")]
    result = run(db, src)
    assert result.ok and result.bars_written == 2
    rows = db.scalars(select(Bar).order_by(Bar.ts)).all()
    assert len(rows) == 2 and rows[-1].close == Decimal("101.5")


def test_invalid_series_is_not_written(db):
    bad = daily(21, "100", high="50")  # high below close
    src = FakeBarSource({"SPY": [daily(20), bad]})
    result = run(db, src)
    assert not result.ok and result.bars_written == 0
    assert db.scalars(select(Bar)).all() == []
    outcome = result.outcomes[0]
    assert "ohlc_inconsistent" in outcome.issue_codes and "stale" in outcome.issue_codes


def test_stale_when_latest_session_missing(db):
    src = FakeBarSource({"SPY": [daily(19), daily(20)]})
    result = run(db, src)
    assert result.stale_symbols == ["SPY"] and not result.ok
    assert result.bars_written == 2  # valid data is still stored, just flagged stale
    report = db.scalars(select(DataQualityReport)).one()
    assert report.stale and report.issues[-1]["code"] == "stale"


def test_symbol_with_no_data_is_stale_and_others_unaffected(db):
    src = FakeBarSource({"SPY": [daily(21)]})
    result = run(db, src, symbols=("SPY", "QQQ"))
    by_symbol = {o.symbol: o for o in result.outcomes}
    assert by_symbol["SPY"].ok
    assert by_symbol["QQQ"].stale and "no_new_bars" in by_symbol["QQQ"].issue_codes


def test_fetch_error_reports_type_only_and_writes_nothing(db):
    src = FakeBarSource({"SPY": [daily(21)]})
    src.error = ConnectionError("https://data.example/v2?token=secret")
    result = run(db, src)
    assert not result.ok and result.bars_written == 0
    report = db.scalars(select(DataQualityReport)).one()
    assert report.issues[0]["code"] == "fetch_error"
    assert "secret" not in str(report.issues) and "ConnectionError" in str(report.issues)


def test_non_session_daily_bar_is_critical(db):
    sunday = make_bar("SPY", datetime(2026, 10, 18, tzinfo=NY), "1Day")
    src = FakeBarSource({"SPY": [sunday, daily(21)]})
    result = run(db, src)
    assert "non_session_bar" in result.outcomes[0].issue_codes
    assert result.bars_written == 0


def test_minute_ingest_is_incremental(db):
    now = datetime(2026, 10, 22, 9, 36, 10, tzinfo=NY)
    src = FakeBarSource({"SPY": [minute(9, m) for m in range(30, 36)]})
    first = run(db, src, tf="1Min", now=now)
    assert first.ok and first.bars_written == 6
    # Full lookback on the first run (nothing stored yet).
    assert src.calls[0][2] == now - timedelta(days=5)

    later = datetime(2026, 10, 22, 9, 38, 5, tzinfo=NY)
    src.bars["SPY"] += [minute(9, 36), minute(9, 37)]
    second = run(db, src, tf="1Min", now=later)
    # Second run starts at the last stored bar (inclusive) and refreshes it.
    assert src.calls[1][2] == datetime(2026, 10, 22, 9, 35, tzinfo=NY)
    assert second.ok and second.bars_written == 3
    latest = latest_stored(db, ["SPY"], "1Min", "all")["SPY"]
    assert latest == datetime(2026, 10, 22, 9, 37, tzinfo=NY)


def test_minute_partial_bar_dropped_and_tolerance_applies(db):
    now = datetime(2026, 10, 22, 9, 33, 30, tzinfo=NY)
    # 9:33 is still forming; 9:32 is missing but within the 120s tolerance of 9:32.
    src = FakeBarSource({"SPY": [minute(9, 30), minute(9, 31), minute(9, 33)]})
    result = run(db, src, tf="1Min", now=now)
    assert result.bars_written == 2 and not result.stale_symbols
    strict = run(db, src, tf="1Min", now=now, minute_tolerance=timedelta(0))
    assert strict.stale_symbols == ["SPY"]


def test_ingestion_symbols_merges_watchlists_and_drops_invalid(db):
    db.add(Watchlist(name="core", symbols=["aapl", "MSFT", "BRK.B", "bad symbol!", "SPY"]))
    db.flush()
    assert ingestion_symbols(db, ["SPY", "QQQ"]) == ["AAPL", "BRK.B", "MSFT", "QQQ", "SPY"]


def test_upsert_empty_is_noop(db):
    assert upsert_bars(db, []) == 0


def test_daily_series_on_holiday_is_not_stale(db):
    # Thanksgiving 2026-11-26 is closed; the 25th is the last completed session.
    holiday_noon = datetime(2026, 11, 26, 12, tzinfo=NY)
    bar = make_bar("SPY", datetime(2026, 11, 25, tzinfo=NY), "1Day")
    result = run(db, FakeBarSource({"SPY": [bar]}), now=holiday_noon)
    assert result.ok
    assert CAL.session(date(2026, 11, 26)) is None


def test_extended_hours_minute_bars_are_not_stored(db):
    now = datetime(2026, 10, 22, 17, 0, tzinfo=NY)
    pre, post = minute(9, 29), minute(16, 5)
    session = [minute(15, m) for m in range(55, 60)]
    result = run(db, FakeBarSource({"SPY": [pre, *session, post]}), tf="1Min", now=now)
    assert result.ok and result.bars_written == 5
    stored = {b.ts.replace(tzinfo=UTC) for b in db.scalars(select(Bar)).all()}
    assert pre.ts not in stored and post.ts not in stored


def test_rest_minute_ingestion_backfills_gap_behind_streamed_bars(db):
    # REST covered up to 9:31; the stream then wrote 9:35 (missing 9:32-9:34 during a drop).
    upsert_bars(db, [minute(9, 30), minute(9, 31)])
    streamed = minute(9, 35).model_copy(update={"source": "alpaca_iex_stream"})
    upsert_bars(db, [streamed])
    now = datetime(2026, 10, 22, 9, 36, 10, tzinfo=NY)
    src = FakeBarSource({"SPY": [minute(9, m) for m in range(30, 36)]})
    result = run(db, src, tf="1Min", now=now)
    # Starts from REST coverage (9:31), not the newest streamed bar (9:35).
    assert src.calls[0][2] == datetime(2026, 10, 22, 9, 31, tzinfo=NY)
    assert result.ok and result.bars_written == 5
    assert len(db.scalars(select(Bar)).all()) == 6
