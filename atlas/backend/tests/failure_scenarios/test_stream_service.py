import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

import fakeredis
from sqlalchemy import select

from atlas.apps.executor.stream_service import LiveDataService
from atlas.core.data.calendar import NY
from atlas.core.data.live import LiveStore, Quote
from atlas.core.models.db import Bar, ServiceHeartbeat, Watchlist
from atlas.integrations.alpaca.stream import StreamState, StreamStats
from atlas.integrations.telegram.notifier import Event
from tests.fakes import RecordingNotifier, make_bar

OPEN = datetime(2026, 10, 22, 11, 0, 30, tzinfo=NY)


class FakeStream:
    def __init__(self, **callbacks):
        self.cb = callbacks
        self.stats = StreamStats()
        self.symbols: list[str] = []
        self.fail_run: Exception | None = None

    async def set_symbols(self, symbols):
        self.symbols = list(symbols)

    def set_state(self, state):
        self.stats.state = state
        self.cb["on_state"](state, self.stats)

    async def run(self):
        if self.fail_run:
            raise self.fail_run
        self._stop = asyncio.Event()
        await self._stop.wait()

    def stop(self):
        if getattr(self, "_stop", None):
            self._stop.set()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def make_service(session_factory, clock=None, **kw):
    notifier = RecordingNotifier()
    clock = clock or Clock(OPEN)
    svc = LiveDataService(
        FakeStream,
        LiveStore(fakeredis.FakeRedis()),
        session_factory,
        default_symbols=["SPY", "QQQ"],
        max_symbols=kw.pop("max_symbols", 30),
        max_quote_age_seconds=15,
        notifier_factory=lambda: notifier,
        clock=clock,
        **kw,
    )
    return svc, notifier, clock


def quote(ts, symbol="SPY"):
    return Quote(symbol, Decimal("100"), Decimal("100.02"), Decimal(1), Decimal(1), ts)


def test_quotes_are_coalesced_into_redis(session_factory):
    svc, _, _ = make_service(session_factory)
    for i in range(5):
        svc.stream.cb["on_quote"](quote(OPEN - timedelta(seconds=5 - i)))
    asyncio.run(svc.flush())
    stored = svc.store.read()
    assert stored["SPY"].quote.ts == OPEN - timedelta(seconds=1)


def test_redis_failure_keeps_symbols_dirty_for_retry(session_factory):
    svc, _, _ = make_service(session_factory)
    svc.stream.cb["on_quote"](quote(OPEN))

    def broken(_snaps):
        raise ConnectionError("redis down")

    real_write, svc.store.write = svc.store.write, broken
    try:
        asyncio.run(svc.flush())
    except ConnectionError:
        pass
    svc.store.write = real_write
    asyncio.run(svc.flush())
    assert "SPY" in svc.store.read()


def test_bars_filtered_validated_and_stored(session_factory):
    svc, _, _ = make_service(session_factory)
    on_bar = svc.stream.cb["on_bar"]
    good = make_bar("SPY", datetime(2026, 10, 22, 10, 59, tzinfo=NY), "1Min")
    premarket = make_bar("SPY", datetime(2026, 10, 22, 9, 0, tzinfo=NY), "1Min")
    bad = make_bar("SPY", datetime(2026, 10, 22, 10, 58, tzinfo=NY), "1Min", high="1")
    for b in (good, premarket, bad):
        on_bar(b)
    asyncio.run(svc.flush_bars())
    assert svc.bars_written == 1 and svc.bars_rejected == 1
    with session_factory() as s:
        assert len(s.scalars(select(Bar)).all()) == 1


def test_symbols_benchmarks_first_and_truncated(session_factory):
    with session_factory() as s:
        s.add(Watchlist(name="w", symbols=["AAPL", "MSFT", "AMZN"]))
        s.commit()
    svc, _, _ = make_service(session_factory, max_symbols=3)
    asyncio.run(svc.refresh_symbols())
    assert svc.stream.symbols == ["SPY", "QQQ", "AAPL"]
    assert svc.dropped_symbols == ["AMZN", "MSFT"]


def _heartbeat(svc, session_factory):
    asyncio.run(svc.heartbeat())
    with session_factory() as s:
        return s.get(ServiceHeartbeat, "stream")


def test_heartbeat_status_ok_degraded_error(session_factory):
    svc, _, _ = make_service(session_factory)
    asyncio.run(svc.refresh_symbols())
    assert _heartbeat(svc, session_factory).status == "error"  # not connected yet
    svc.stream.set_state(StreamState.SUBSCRIBED)
    hb = _heartbeat(svc, session_factory)
    assert hb.status == "degraded" and hb.details["stale"] == ["SPY", "QQQ"]
    for sym in ("SPY", "QQQ"):
        svc.stream.cb["on_quote"](quote(OPEN - timedelta(seconds=2), sym))
    hb = _heartbeat(svc, session_factory)
    assert hb.status == "ok" and hb.details["market_open"] is True
    assert svc.store.read_status()["status"] == "ok"


def test_no_staleness_when_market_closed(session_factory):
    saturday = Clock(datetime(2026, 10, 24, 12, tzinfo=NY))
    svc, _, _ = make_service(session_factory, clock=saturday)
    asyncio.run(svc.refresh_symbols())
    svc.stream.set_state(StreamState.SUBSCRIBED)
    assert _heartbeat(svc, session_factory).status == "ok"


def test_disconnect_alert_after_60s_in_market_hours_then_restored(session_factory):
    svc, notifier, clock = make_service(session_factory)
    svc.stream.set_state(StreamState.SUBSCRIBED)
    svc.stream.set_state(StreamState.BACKOFF)
    clock.now = OPEN + timedelta(seconds=30)
    _heartbeat(svc, session_factory)
    assert notifier.messages == []
    clock.now = OPEN + timedelta(seconds=90)
    _heartbeat(svc, session_factory)
    _heartbeat(svc, session_factory)  # no repeat
    assert notifier.events == [Event.BROKER_DISCONNECTED]
    assert "down for 90s" in notifier.messages[0][0]
    svc.stream.set_state(StreamState.SUBSCRIBED)
    _heartbeat(svc, session_factory)
    assert "restored" in notifier.messages[-1][0] and len(notifier.messages) == 2


def test_fatal_error_alerts_once_as_critical(session_factory):
    saturday = Clock(datetime(2026, 10, 24, 12, tzinfo=NY))
    svc, notifier, _ = make_service(session_factory, clock=saturday)
    svc.stream.stats.last_error = "402: auth failed"
    svc.stream.set_state(StreamState.ERROR)
    _heartbeat(svc, session_factory)
    _heartbeat(svc, session_factory)
    assert len(notifier.messages) == 1
    text, critical = notifier.messages[0]
    assert critical and "402: auth failed" in text and "[PAPER TRADING]" in text


def test_run_stops_cleanly_and_does_final_flush(session_factory):
    svc, _, _ = make_service(session_factory, flush_interval=10)

    async def scenario():
        task = asyncio.create_task(svc.run())
        await asyncio.sleep(0.05)
        svc.stream.cb["on_quote"](quote(OPEN))
        svc.stop()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert "SPY" in svc.store.read()
    with session_factory() as s:
        assert s.get(ServiceHeartbeat, "stream") is not None


def test_loop_errors_do_not_stop_the_service(session_factory):
    svc, _, _ = make_service(session_factory, heartbeat_interval=0.01)
    calls = []

    async def failing():
        calls.append(1)
        raise RuntimeError("db down")

    svc.heartbeat = failing  # type: ignore[method-assign]

    async def scenario():
        task = asyncio.create_task(svc.run())
        await asyncio.sleep(0.1)
        assert not task.done()
        svc.stop()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert len(calls) >= 3


def test_unexpected_stream_exit_raises(session_factory):
    svc, _, _ = make_service(session_factory)
    svc.stream.fail_run = RuntimeError("bug")

    async def scenario():
        try:
            await svc.run()
        except RuntimeError as exc:
            return str(exc)
        return None

    assert asyncio.run(scenario()) == "bug"
