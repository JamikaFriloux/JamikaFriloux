"""Live quotes and trades: in-memory latest-value cache, Redis store, and freshness checks.

The streaming service (executor) writes the latest quote/trade per symbol to Redis; the API
and, later, the trading engine read it. Nothing here holds credentials or talks to a broker.

Freshness is judged from the exchange timestamp, not from when we received the message, so a
backlog or a stalled connection cannot make an old quote look current. ``fresh_quote`` is the
only accessor trading code should use: it returns None (do not trade) unless the market is
open and the quote is recent, two-sided and not crossed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from atlas.core.data.calendar import MarketCalendar

_FRACTION = re.compile(r"(\.\d{6})\d+")
_KEY_PREFIX = "atlas:live:q:"
_SYMBOLS_KEY = "atlas:live:symbols"
_STATUS_KEY = "atlas:live:status"
_KEY_TTL_SECONDS = 7 * 24 * 3600
# Exchange clocks and ours can disagree slightly; anything further in the future is bad data.
_MAX_CLOCK_SKEW = timedelta(seconds=2)


def parse_rfc3339(value: str) -> datetime:
    """Parse Alpaca's RFC 3339 timestamps (nanosecond precision, ``Z`` suffix) to aware UTC."""
    ts = datetime.fromisoformat(_FRACTION.sub(r"\1", value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value!r}")
    return ts.astimezone(UTC)


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    ts: datetime


@dataclass(frozen=True)
class Trade:
    symbol: str
    price: Decimal
    size: Decimal
    ts: datetime


@dataclass(frozen=True)
class LiveSnapshot:
    symbol: str
    quote: Quote | None = None
    trade: Trade | None = None
    received_at: datetime | None = None

    def quote_age(self, now: datetime) -> float | None:
        return None if self.quote is None else (now - self.quote.ts).total_seconds()

    def to_redis(self) -> dict[str, str]:
        out: dict[str, str] = {"symbol": self.symbol}
        if self.quote is not None:
            q = self.quote
            out.update(
                bid=str(q.bid),
                ask=str(q.ask),
                bid_size=str(q.bid_size),
                ask_size=str(q.ask_size),
                quote_ts=q.ts.isoformat(),
            )
        if self.trade is not None:
            t = self.trade
            out.update(last=str(t.price), last_size=str(t.size), trade_ts=t.ts.isoformat())
        if self.received_at is not None:
            out["received_at"] = self.received_at.isoformat()
        return out

    @classmethod
    def from_redis(cls, raw: dict[Any, Any]) -> LiveSnapshot:
        d = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
        quote = trade = None
        if "quote_ts" in d:
            quote = Quote(
                symbol=d["symbol"],
                bid=Decimal(d["bid"]),
                ask=Decimal(d["ask"]),
                bid_size=Decimal(d["bid_size"]),
                ask_size=Decimal(d["ask_size"]),
                ts=datetime.fromisoformat(d["quote_ts"]),
            )
        if "trade_ts" in d:
            trade = Trade(
                symbol=d["symbol"],
                price=Decimal(d["last"]),
                size=Decimal(d["last_size"]),
                ts=datetime.fromisoformat(d["trade_ts"]),
            )
        received = d.get("received_at")
        return cls(
            symbol=d["symbol"],
            quote=quote,
            trade=trade,
            received_at=datetime.fromisoformat(received) if received else None,
        )


class LiveCache:
    """Latest quote/trade per symbol. Messages that arrive out of order are ignored."""

    def __init__(self) -> None:
        self._data: dict[str, LiveSnapshot] = {}
        self._dirty: set[str] = set()

    def apply_quote(self, quote: Quote, received_at: datetime) -> None:
        cur = self._data.get(quote.symbol) or LiveSnapshot(quote.symbol)
        if cur.quote is not None and quote.ts < cur.quote.ts:
            return
        self._data[quote.symbol] = replace(cur, quote=quote, received_at=received_at)
        self._dirty.add(quote.symbol)

    def apply_trade(self, trade: Trade, received_at: datetime) -> None:
        cur = self._data.get(trade.symbol) or LiveSnapshot(trade.symbol)
        if cur.trade is not None and trade.ts < cur.trade.ts:
            return
        self._data[trade.symbol] = replace(cur, trade=trade, received_at=received_at)
        self._dirty.add(trade.symbol)

    def get(self, symbol: str) -> LiveSnapshot | None:
        return self._data.get(symbol)

    def snapshots(self) -> list[LiveSnapshot]:
        return [self._data[s] for s in sorted(self._data)]

    def mark_dirty(self, symbols: Iterable[str]) -> None:
        self._dirty.update(s for s in symbols if s in self._data)

    def drain_dirty(self) -> list[LiveSnapshot]:
        out = [self._data[s] for s in sorted(self._dirty)]
        self._dirty.clear()
        return out

    def stale_symbols(self, symbols: list[str], now: datetime, max_age: float) -> list[str]:
        stale = []
        for s in symbols:
            snap = self._data.get(s)
            age = snap.quote_age(now) if snap else None
            if age is None or age > max_age:
                stale.append(s)
        return stale


class LiveStore:
    """Redis-backed latest values, shared between the stream service and readers."""

    def __init__(self, redis_client: Any) -> None:
        self._r = redis_client

    def write(self, snapshots: list[LiveSnapshot]) -> None:
        if not snapshots:
            return
        pipe = self._r.pipeline(transaction=False)
        for snap in snapshots:
            key = _KEY_PREFIX + snap.symbol
            pipe.hset(key, mapping=snap.to_redis())
            pipe.expire(key, _KEY_TTL_SECONDS)
            pipe.sadd(_SYMBOLS_KEY, snap.symbol)
        pipe.execute()

    def read(self, symbols: list[str] | None = None) -> dict[str, LiveSnapshot]:
        if symbols is None:
            members = self._r.smembers(_SYMBOLS_KEY)
            symbols = sorted(m.decode() if isinstance(m, bytes) else m for m in members)
        if not symbols:
            return {}
        pipe = self._r.pipeline(transaction=False)
        for s in symbols:
            pipe.hgetall(_KEY_PREFIX + s)
        out = {}
        for s, raw in zip(symbols, pipe.execute(), strict=True):
            if raw:
                out[s] = LiveSnapshot.from_redis(raw)
        return out

    def write_status(self, status: dict[str, str]) -> None:
        self._r.hset(_STATUS_KEY, mapping=status)
        self._r.expire(_STATUS_KEY, _KEY_TTL_SECONDS)

    def read_status(self) -> dict[str, str]:
        raw = self._r.hgetall(_STATUS_KEY) or {}
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }


def fresh_quote(
    snapshot: LiveSnapshot | None,
    *,
    now: datetime,
    max_age_seconds: float,
    calendar: MarketCalendar,
) -> Quote | None:
    """The quote if it is safe to act on, else None (fail closed)."""
    if snapshot is None or snapshot.quote is None:
        return None
    q = snapshot.quote
    if not calendar.is_open(now):
        return None
    age = now - q.ts
    if age > timedelta(seconds=max_age_seconds) or age < -_MAX_CLOCK_SKEW:
        return None
    if q.bid <= 0 or q.ask <= 0 or q.ask < q.bid:
        return None
    return q
