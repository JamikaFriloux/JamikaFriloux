from datetime import UTC, datetime, timedelta
from decimal import Decimal

import fakeredis
import pytest

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.live import (
    LiveCache,
    LiveSnapshot,
    LiveStore,
    Quote,
    Trade,
    fresh_quote,
    parse_rfc3339,
)

CAL = MarketCalendar()
OPEN = datetime(2026, 10, 22, 11, 0, tzinfo=NY)


def quote(ts, bid="100.00", ask="100.02", symbol="SPY"):
    return Quote(symbol, Decimal(bid), Decimal(ask), Decimal(3), Decimal(4), ts)


def trade(ts, price="100.01", symbol="SPY"):
    return Trade(symbol, Decimal(price), Decimal(10), ts)


def test_parse_rfc3339_nanoseconds_and_z():
    ts = parse_rfc3339("2026-10-22T15:00:01.123456789Z")
    assert ts == datetime(2026, 10, 22, 15, 0, 1, 123456, tzinfo=UTC)
    assert parse_rfc3339("2026-10-22T15:00:01Z").tzinfo is not None
    with pytest.raises(ValueError):
        parse_rfc3339("2026-10-22T15:00:01")


def test_cache_ignores_out_of_order_and_tracks_dirty():
    cache = LiveCache()
    cache.apply_quote(quote(OPEN, bid="101"), OPEN)
    cache.apply_quote(quote(OPEN - timedelta(seconds=1), bid="99"), OPEN)
    cache.apply_trade(trade(OPEN), OPEN)
    snap = cache.get("SPY")
    assert snap is not None and snap.quote.bid == Decimal("101") and snap.trade is not None
    assert [s.symbol for s in cache.drain_dirty()] == ["SPY"]
    assert cache.drain_dirty() == []
    cache.mark_dirty(["SPY", "UNKNOWN"])
    assert [s.symbol for s in cache.drain_dirty()] == ["SPY"]


def test_stale_symbols():
    cache = LiveCache()
    cache.apply_quote(quote(OPEN - timedelta(seconds=5)), OPEN)
    cache.apply_quote(quote(OPEN - timedelta(seconds=30), symbol="QQQ"), OPEN)
    assert cache.stale_symbols(["SPY", "QQQ", "IWM"], OPEN, 15) == ["QQQ", "IWM"]


def test_store_round_trip():
    store = LiveStore(fakeredis.FakeRedis())
    snap = LiveSnapshot("SPY", quote(OPEN), trade(OPEN), received_at=OPEN)
    store.write([snap, LiveSnapshot("QQQ", trade=trade(OPEN, symbol="QQQ"))])
    out = store.read()
    assert set(out) == {"SPY", "QQQ"}
    assert out["SPY"] == snap
    assert out["QQQ"].quote is None and out["QQQ"].trade.price == Decimal("100.01")
    assert store.read(["NONE"]) == {}
    store.write_status({"status": "ok"})
    assert store.read_status() == {"status": "ok"}


def test_fresh_quote_rules():
    def check(q, now=OPEN, max_age=15):
        return fresh_quote(LiveSnapshot("SPY", q), now=now, max_age_seconds=max_age, calendar=CAL)

    assert check(quote(OPEN - timedelta(seconds=3))) is not None
    assert check(quote(OPEN - timedelta(seconds=16))) is None  # too old
    assert check(quote(OPEN + timedelta(seconds=5))) is None  # from the future
    assert check(quote(OPEN, bid="0")) is None  # one-sided
    assert check(quote(OPEN, bid="100.05", ask="100.00")) is None  # crossed
    closed = datetime(2026, 10, 24, 11, 0, tzinfo=NY)  # Saturday
    assert check(quote(closed), now=closed) is None
    assert fresh_quote(None, now=OPEN, max_age_seconds=15, calendar=CAL) is None
    assert fresh_quote(LiveSnapshot("SPY"), now=OPEN, max_age_seconds=15, calendar=CAL) is None
