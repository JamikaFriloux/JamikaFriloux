"""Alpaca real-time market data stream (read-only data WebSocket, JSON protocol).

A thin client instead of the SDK's ``StockDataStream`` so that connection state, reconnect
counts and errors are visible to the service (heartbeats, alerts) and the client can be
tested against a local fake server.

Behavior:
  * One connection (Alpaca allows one per account). Connect -> auth -> subscribe -> consume.
  * Reconnects with capped exponential backoff and jitter. Backoff resets once a session has
    delivered market data. "Connection limit exceeded" (406) waits at least 30 s so the old
    session can be reaped; auth failure (402) and insufficient subscription (409) are fatal
    for that attempt and retry only every ``fatal_backoff`` seconds, with state ``error``.
  * Watchdog: during regular trading hours, if no market data arrives for ``data_timeout``
    seconds the connection is considered mute and is replaced. Outside trading hours quiet
    is normal; WebSocket ping/pong still detects dead connections.
  * ``set_symbols`` changes subscriptions on the live connection; a reconnect resubscribes
    to the full current set.

The host is fixed to Alpaca's market-data stream; this module cannot reach a trading
endpoint. Credentials are sent only in the auth message and never logged.
"""

from __future__ import annotations

import asyncio
import enum
import json
import random
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

from atlas.core.data.bars import BarRecord
from atlas.core.data.live import Quote, Trade, parse_rfc3339
from atlas.core.observability.logging import get_logger

log = get_logger(__name__)

STREAM_HOST = "wss://stream.data.alpaca.markets/v2/"
StreamFeed = Literal["iex", "sip", "test"]
CHANNELS = ("quotes", "trades", "bars")

# https://docs.alpaca.markets/docs/streaming-market-data#error-codes
FATAL_CODES = {402: "auth failed", 409: "insufficient subscription"}
CONNECTION_LIMIT_CODE = 406
SYMBOL_LIMIT_CODE = 405


class StreamState(enum.StrEnum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    SUBSCRIBED = "subscribed"
    BACKOFF = "backoff"
    ERROR = "error"


class StreamError(Exception):
    def __init__(self, code: int | None, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.msg = msg


class MuteStreamError(Exception):
    """No market data for longer than the watchdog allows during trading hours."""


@dataclass
class StreamStats:
    state: StreamState = StreamState.STOPPED
    connected_since: datetime | None = None
    last_message_at: datetime | None = None
    last_data_at: datetime | None = None
    connects: int = 0
    reconnects: int = 0
    messages: int = 0
    last_error: str | None = None
    subscribed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        def iso(v: datetime | None) -> str | None:
            return v.isoformat() if v else None

        return {
            "state": self.state.value,
            "connected_since": iso(self.connected_since),
            "last_message_at": iso(self.last_message_at),
            "last_data_at": iso(self.last_data_at),
            "connects": self.connects,
            "reconnects": self.reconnects,
            "messages": self.messages,
            "last_error": self.last_error,
            "subscribed": len(self.subscribed),
        }


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


class AlpacaStream:
    def __init__(
        self,
        api_key_id: str,
        api_secret_key: str,
        feed: StreamFeed = "iex",
        *,
        on_quote: Callable[[Quote], None],
        on_trade: Callable[[Trade], None],
        on_bar: Callable[[BarRecord], None],
        on_state: Callable[[StreamState, StreamStats], None] | None = None,
        is_market_open: Callable[[datetime], bool] = lambda _now: False,
        data_timeout: float = 60.0,
        backoff_min: float = 1.0,
        backoff_max: float = 60.0,
        fatal_backoff: float = 300.0,
        recv_poll: float = 5.0,
        endpoint: str | None = None,
        connector: Callable[..., Any] = connect,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if feed not in ("iex", "sip", "test"):
            raise ValueError(f"unsupported stream feed {feed!r}")
        self._key = api_key_id
        self._secret = api_secret_key
        self.feed = feed
        # ``endpoint`` exists only so tests can point at a local fake server.
        self.endpoint = endpoint or STREAM_HOST + feed
        self._on_quote, self._on_trade, self._on_bar = on_quote, on_trade, on_bar
        self._on_state = on_state
        self._is_market_open = is_market_open
        self._data_timeout = data_timeout
        self._backoff_min, self._backoff_max = backoff_min, backoff_max
        self._fatal_backoff = fatal_backoff
        self._recv_poll = recv_poll
        self._connector = connector
        self._clock = clock
        self._sleep = sleep
        self._symbols: set[str] = set()
        self._ws: Any = None
        self._got_data = False
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self.stats = StreamStats()

    @property
    def bar_source(self) -> str:
        return f"alpaca_{self.feed}_stream"

    # ----- public API -------------------------------------------------------------------

    async def set_symbols(self, symbols: Iterable[str]) -> None:
        new = set(symbols)
        added, removed = sorted(new - self._symbols), sorted(self._symbols - new)
        self._symbols = new
        if self._ws is None or self.stats.state != StreamState.SUBSCRIBED:
            return  # applied on the next (re)connect
        try:
            if removed:
                await self._send({"action": "unsubscribe", **dict.fromkeys(CHANNELS, removed)})
            if added:
                await self._send({"action": "subscribe", **dict.fromkeys(CHANNELS, added)})
        except WebSocketException:
            pass  # the consume loop sees the closed connection and reconnects

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    async def run(self) -> None:
        """Run until ``stop()``. Never raises for network or protocol errors."""
        retries = 0
        while not self._stop.is_set():
            delay = 0.0
            try:
                await self._session()
            except StreamError as exc:
                self.stats.last_error = str(exc)
                if exc.code in FATAL_CODES:
                    log.error("stream_fatal", code=exc.code, msg=exc.msg)
                    self._set_state(StreamState.ERROR)
                    await self._wait(self._fatal_backoff)
                    continue
                log.warning("stream_error", code=exc.code, msg=exc.msg)
                if exc.code == CONNECTION_LIMIT_CODE:
                    delay = 30.0
            except MuteStreamError:
                self.stats.last_error = "no market data within watchdog timeout"
                log.warning("stream_mute", timeout=self._data_timeout)
            except InvalidStatus as exc:
                code = exc.response.status_code
                self.stats.last_error = f"HTTP {code}"
                log.warning("stream_http_error", status=code)
                if code == 429:
                    delay = 30.0
            except (OSError, WebSocketException, TimeoutError, ValueError) as exc:
                # Type only: messages from transport errors can include URLs.
                self.stats.last_error = type(exc).__name__
                log.warning("stream_disconnected", error=type(exc).__name__)
            finally:
                await self._close()
            if self._stop.is_set():
                break
            # A session that delivered data was healthy: start the backoff over.
            retries = 1 if self._got_data else retries + 1
            backoff = min(self._backoff_max, self._backoff_min * 2 ** (retries - 1))
            delay = max(delay, backoff * random.uniform(0.8, 1.2))  # noqa: S311
            self.stats.reconnects += 1
            self._set_state(StreamState.BACKOFF)
            await self._wait(delay)
        self._set_state(StreamState.STOPPED)

    # ----- internals --------------------------------------------------------------------

    def _set_state(self, state: StreamState) -> None:
        if state == self.stats.state:
            return
        self.stats.state = state
        if state == StreamState.SUBSCRIBED:
            self.stats.connected_since = self._clock()
        elif state != StreamState.CONNECTING:
            self.stats.connected_since = None
        if self._on_state is not None:
            self._on_state(state, self.stats)

    async def _wait(self, seconds: float) -> None:
        self._wake.clear()
        if self._stop.is_set():
            return
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        waker = asyncio.ensure_future(self._wake.wait())
        _, pending = await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    async def _close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: S110 - already tearing down
                pass

    async def _send(self, payload: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(payload))

    async def _recv(self) -> list[dict[str, Any]]:
        raw = await self._ws.recv()
        msgs = json.loads(raw)
        return msgs if isinstance(msgs, list) else [msgs]

    async def _expect(self, kind: str) -> None:
        for msg in await self._recv():
            if msg.get("T") == "error":
                raise StreamError(msg.get("code"), str(msg.get("msg", "")))
            if msg.get("T") == "success" and msg.get("msg") == kind:
                return
        raise StreamError(None, f"expected {kind!r}")

    async def _session(self) -> None:
        """One connection lifetime; returns on stop, raises on any failure."""
        self._got_data = False
        self._set_state(StreamState.CONNECTING)
        self._ws = await self._connector(
            self.endpoint, open_timeout=10, ping_interval=20, ping_timeout=20, close_timeout=5
        )
        self.stats.connects += 1
        await self._expect("connected")
        await self._send({"action": "auth", "key": self._key, "secret": self._secret})
        await self._expect("authenticated")
        symbols = sorted(self._symbols)
        if symbols:
            await self._send({"action": "subscribe", **dict.fromkeys(CHANNELS, symbols)})
        self._set_state(StreamState.SUBSCRIBED)
        log.info("stream_connected", feed=self.feed, symbols=len(symbols))
        await self._consume()

    async def _consume(self) -> None:
        started = self._clock()
        while not self._stop.is_set():
            try:
                msgs = await asyncio.wait_for(self._recv(), self._recv_poll)
            except TimeoutError:
                msgs = []
            now = self._clock()
            for msg in msgs:
                self.stats.messages += 1
                self.stats.last_message_at = now
                if self._handle(msg):
                    self._got_data = True
                    self.stats.last_data_at = now
            if self._is_market_open(now):
                last = max(self.stats.last_data_at or started, started)
                if (now - last).total_seconds() > self._data_timeout:
                    raise MuteStreamError

    def _handle(self, msg: dict[str, Any]) -> bool:
        """Dispatch one message. Returns True for market data."""
        kind = msg.get("T")
        try:
            if kind == "q":
                self._on_quote(
                    Quote(
                        symbol=msg["S"],
                        bid=_dec(msg["bp"]),
                        ask=_dec(msg["ap"]),
                        bid_size=_dec(msg["bs"]),
                        ask_size=_dec(msg["as"]),
                        ts=parse_rfc3339(msg["t"]),
                    )
                )
                return True
            if kind == "t":
                self._on_trade(
                    Trade(
                        symbol=msg["S"],
                        price=_dec(msg["p"]),
                        size=_dec(msg["s"]),
                        ts=parse_rfc3339(msg["t"]),
                    )
                )
                return True
            if kind in ("b", "u"):  # minute bar / late-trade correction of a minute bar
                self._on_bar(
                    BarRecord(
                        symbol=msg["S"],
                        timeframe="1Min",
                        ts=parse_rfc3339(msg["t"]),
                        open=_dec(msg["o"]),
                        high=_dec(msg["h"]),
                        low=_dec(msg["l"]),
                        close=_dec(msg["c"]),
                        volume=_dec(msg["v"]),
                        vwap=_dec(msg["vw"]) if msg.get("vw") is not None else None,
                        trade_count=int(msg["n"]) if msg.get("n") is not None else None,
                        source=self.bar_source,
                        # A just-completed bar is identical raw or adjusted (adjustments only
                        # rewrite history before a corporate action), so it joins the
                        # "all"-adjusted series the REST ingestion maintains.
                        adjustment="all",
                    )
                )
                return True
        except (KeyError, ValueError, ArithmeticError) as exc:
            log.warning("stream_bad_message", kind=kind, error=type(exc).__name__)
            return False
        if kind == "subscription":
            self.stats.subscribed = sorted(set(msg.get("quotes") or []))
        elif kind == "error":
            code = msg.get("code")
            if code == SYMBOL_LIMIT_CODE:
                # Keep the connection: the symbols accepted so far still stream.
                self.stats.last_error = f"{code}: {msg.get('msg')}"
                log.error("stream_symbol_limit", msg=msg.get("msg"))
            else:
                raise StreamError(code, str(msg.get("msg", "")))
        return False
