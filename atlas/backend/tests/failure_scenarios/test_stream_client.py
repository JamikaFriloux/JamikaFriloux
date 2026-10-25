"""AlpacaStream against a local fake of Alpaca's market-data WebSocket protocol."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

from atlas.integrations.alpaca.stream import AlpacaStream, StreamState

KEY, SECRET = "PKTESTKEY", "test-secret-value"
QUOTE = {"T": "q", "S": "SPY", "bp": 100.0, "ap": 100.02, "bs": 3, "as": 4,
         "t": "2026-10-22T15:00:01.123456789Z"}  # fmt: skip
TRADE = {"T": "t", "S": "SPY", "p": 100.01, "s": 10, "t": "2026-10-22T15:00:01.2Z"}
BAR = {"T": "b", "S": "SPY", "o": 100, "h": 101, "l": 99.5, "c": 100.5, "v": 12345,
       "t": "2026-10-22T15:00:00Z", "n": 42, "vw": 100.2}  # fmt: skip

Script = Callable[[ServerConnection, int], Awaitable[None]]


class FakeAlpaca:
    def __init__(self, script: Script | None = None, auth_error: dict | None = None):
        self.script = script
        self.auth_error = auth_error
        self.connections = 0
        self.received: list[list[dict[str, Any]]] = []
        self.subs: set[str] = set()

    async def handler(self, ws: ServerConnection) -> None:
        self.connections += 1
        n = self.connections
        msgs: list[dict[str, Any]] = []
        self.received.append(msgs)
        await ws.send(json.dumps([{"T": "success", "msg": "connected"}]))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                msgs.append(msg)
                if msg["action"] == "auth":
                    if self.auth_error:
                        await ws.send(json.dumps([{"T": "error", **self.auth_error}]))
                        continue
                    await ws.send(json.dumps([{"T": "success", "msg": "authenticated"}]))
                elif msg["action"] in ("subscribe", "unsubscribe"):
                    change = set(msg.get("quotes", []))
                    self.subs = self.subs | change if msg["action"] == "subscribe" else (
                        self.subs - change
                    )  # fmt: skip
                    s = sorted(self.subs)
                    await ws.send(
                        json.dumps([{"T": "subscription", "trades": s, "quotes": s, "bars": s}])
                    )
                    if self.script and msg["action"] == "subscribe":
                        await self.script(ws, n)
        except Exception:  # noqa: S110 - client went away
            pass


class Recorder:
    def __init__(self) -> None:
        self.quotes: list = []
        self.trades: list = []
        self.bars: list = []
        self.states: list[StreamState] = []
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        await asyncio.sleep(0.01)


async def _with_stream(
    fake: FakeAlpaca,
    until: Callable[[AlpacaStream, Recorder], bool],
    *,
    symbols=("SPY",),
    wait_s: float = 5.0,
    during: Callable[[AlpacaStream], Awaitable[None]] | None = None,
    **kw: Any,
) -> tuple[AlpacaStream, Recorder]:
    rec = Recorder()
    async with serve(fake.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        stream = AlpacaStream(
            KEY,
            SECRET,
            "iex",
            endpoint=f"ws://127.0.0.1:{port}",
            on_quote=rec.quotes.append,
            on_trade=rec.trades.append,
            on_bar=rec.bars.append,
            on_state=lambda s, _st: rec.states.append(s),
            sleep=rec.sleep,
            recv_poll=0.05,
            **kw,
        )
        await stream.set_symbols(symbols)
        task = asyncio.create_task(stream.run())
        try:
            async with asyncio.timeout(wait_s):
                while not until(stream, rec):  # noqa: ASYNC110 - polling a predicate
                    await asyncio.sleep(0.01)
                if during is not None:
                    await during(stream)
        finally:
            stream.stop()
            await asyncio.wait_for(task, 5)
    return stream, rec


def run(coro):
    return asyncio.run(coro)


def test_connects_authenticates_subscribes_and_parses_market_data():
    async def push(ws, _n):
        await ws.send(json.dumps([QUOTE, TRADE, BAR]))

    fake = FakeAlpaca(push)
    stream, rec = run(_with_stream(fake, lambda _s, r: len(r.bars) == 1))
    first = fake.received[0]
    assert first[0] == {"action": "auth", "key": KEY, "secret": SECRET}
    assert first[1] == {"action": "subscribe", "quotes": ["SPY"], "trades": ["SPY"],
                        "bars": ["SPY"]}  # fmt: skip
    q, t, b = rec.quotes[0], rec.trades[0], rec.bars[0]
    assert q.bid == Decimal("100.0") and q.ask_size == Decimal(4) and q.ts.microsecond == 123456
    assert t.price == Decimal("100.01")
    assert b.timeframe == "1Min" and b.source == "alpaca_iex_stream" and b.trade_count == 42
    assert rec.states[:2] == [StreamState.CONNECTING, StreamState.SUBSCRIBED]
    assert rec.states[-1] == StreamState.STOPPED
    assert stream.stats.subscribed == ["SPY"] and stream.stats.messages >= 4
    assert SECRET not in json.dumps(stream.stats.as_dict())


def test_reconnects_after_drop_and_resubscribes_current_symbols():
    async def drop_first(ws, n):
        await ws.send(json.dumps([QUOTE]))
        if n == 1:
            await ws.close()

    fake = FakeAlpaca(drop_first)
    stream, rec = run(_with_stream(fake, lambda _s, r: len(r.quotes) >= 2))
    assert fake.connections == 2 and stream.stats.reconnects == 1
    assert fake.received[1][1]["quotes"] == ["SPY"]
    # The dropped session had delivered data, so backoff restarts at the minimum (1 s +/-20%).
    assert 0.8 <= rec.delays[0] <= 1.2


def test_backoff_grows_while_connections_keep_failing():
    async def drop_immediately(ws, _n):
        await ws.close()

    fake = FakeAlpaca(drop_immediately)
    _, rec = run(_with_stream(fake, lambda _s, r: len(r.delays) >= 4))
    assert rec.delays[3] > rec.delays[0] * 4  # 1, 2, 4, 8 s with jitter


def test_set_symbols_updates_live_subscription():
    fake = FakeAlpaca()

    async def change(stream):
        await stream.set_symbols(["SPY", "QQQ"])
        await stream.set_symbols(["QQQ"])
        await asyncio.sleep(0.2)

    run(_with_stream(fake, lambda s, _r: s.stats.state == StreamState.SUBSCRIBED, during=change))
    actions = [(m["action"], m.get("quotes")) for m in fake.received[0][1:]]
    assert actions == [("subscribe", ["SPY"]), ("subscribe", ["QQQ"]), ("unsubscribe", ["SPY"])]
    assert fake.subs == {"QQQ"}


def test_auth_failure_is_fatal_state_with_slow_retry():
    fake = FakeAlpaca(auth_error={"code": 402, "msg": "auth failed"})
    stream, rec = run(
        _with_stream(fake, lambda s, _r: s.stats.state == StreamState.ERROR, fatal_backoff=300)
    )
    assert rec.delays[0] == 300
    assert stream.stats.last_error == "402: auth failed"


def test_connection_limit_waits_at_least_30_seconds():
    fake = FakeAlpaca(auth_error={"code": 406, "msg": "connection limit exceeded"})
    _, rec = run(_with_stream(fake, lambda _s, r: len(r.delays) >= 1))
    assert rec.delays[0] >= 30


def test_watchdog_replaces_mute_connection_during_market_hours():
    fake = FakeAlpaca()
    stream, _ = run(
        _with_stream(
            fake,
            lambda _s, _r: fake.connections >= 2,
            is_market_open=lambda _now: True,
            data_timeout=0.2,
        )
    )
    assert "watchdog" in (stream.stats.last_error or "")


def test_quiet_connection_is_kept_when_market_closed():
    fake = FakeAlpaca()

    async def wait(_stream):
        await asyncio.sleep(0.5)

    run(
        _with_stream(
            fake,
            lambda s, _r: s.stats.state == StreamState.SUBSCRIBED,
            during=wait,
            is_market_open=lambda _now: False,
            data_timeout=0.1,
        )
    )
    assert fake.connections == 1


def test_symbol_limit_error_keeps_connection_and_bad_messages_are_skipped():
    async def push(ws, _n):
        await ws.send(json.dumps([{"T": "error", "code": 405, "msg": "symbol limit exceeded"}]))
        await ws.send(json.dumps([{"T": "q", "S": "SPY"}, QUOTE]))  # first lacks fields

    fake = FakeAlpaca(push)
    stream, _ = run(_with_stream(fake, lambda _s, r: len(r.quotes) == 1))
    assert fake.connections == 1 and "405" in (stream.stats.last_error or "")


def test_unsupported_feed_rejected():
    with pytest.raises(ValueError):
        AlpacaStream(KEY, SECRET, "delayed_sip", on_quote=print, on_trade=print, on_bar=print)  # type: ignore[arg-type]
