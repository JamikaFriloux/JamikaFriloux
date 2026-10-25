"""Bar ingestion: fetch, drop incomplete bars, validate, upsert, and record a quality report.

This module holds no credentials and imports no brokerage SDK. The bar source is injected
(the executor passes ``AlpacaMarketData``; tests pass a fake), so the same logic runs in
production and in tests.

Rules:
  * Bars for a session or minute that has not finished are never stored (they are partial),
    and neither are extended-hours minute bars (policy: regular hours only).
  * A symbol whose fetched series has any critical validation issue is not written at all;
    the report records why. Nothing is repaired silently.
  * Staleness is judged against the XNYS calendar: the newest stored bar must be the most
    recent completed daily session, or for minute bars within ``minute_tolerance`` of the
    last completed minute. A stale series is a critical issue (fail closed downstream).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.core.data.bars import TIMEFRAME_DELTA, BarRecord, DataIssue, Timeframe, validate_bars
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.calendar import Session as MarketSession
from atlas.core.models.db import Bar, DataQualityReport, Watchlist

SUPPORTED_TIMEFRAMES: tuple[Timeframe, ...] = ("1Day", "1Min")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_BATCH_SYMBOLS = 100
_UPSERT_CHUNK = 2000
_MAX_STORED_ISSUES = 50


class BarSource(Protocol):
    @property
    def source(self) -> str: ...

    def get_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        adjustment: str = "all",
    ) -> dict[str, list[BarRecord]]: ...


@dataclass(frozen=True)
class SymbolOutcome:
    symbol: str
    ok: bool
    stale: bool
    bars_fetched: int
    bars_written: int
    latest_bar_ts: datetime | None
    issue_codes: tuple[str, ...]


@dataclass
class IngestionResult:
    run_id: uuid.UUID
    timeframe: Timeframe
    outcomes: list[SymbolOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(o.ok for o in self.outcomes)

    @property
    def bars_written(self) -> int:
        return sum(o.bars_written for o in self.outcomes)

    @property
    def stale_symbols(self) -> list[str]:
        return [o.symbol for o in self.outcomes if o.stale]

    @property
    def failed_symbols(self) -> list[str]:
        return [o.symbol for o in self.outcomes if not o.ok]

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "timeframe": self.timeframe,
            "symbols": len(self.outcomes),
            "bars_written": self.bars_written,
            "failed": self.failed_symbols,
            "stale": self.stale_symbols,
        }


def _utc(dt: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip; stored values are always UTC.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _daily_bar_ts(day: date) -> datetime:
    """Alpaca stamps daily bars at midnight New York time of the session date."""
    return datetime(day.year, day.month, day.day, tzinfo=NY).astimezone(UTC)


def last_completed_session(calendar: MarketCalendar, now: datetime) -> MarketSession:
    day = now.astimezone(NY).date()
    for offset in range(0, 15):
        s = calendar.session(day - timedelta(days=offset))
        if s is not None and s.close <= now:
            return s
    raise RuntimeError("no completed session in the last 15 days")  # pragma: no cover


def expected_latest_bar(timeframe: Timeframe, now: datetime, calendar: MarketCalendar) -> datetime:
    """Open time of the newest bar that should exist and be complete at ``now``."""
    if timeframe == "1Day":
        return _daily_bar_ts(last_completed_session(calendar, now).day)
    if timeframe == "1Min":
        if calendar.is_open(now):
            current = calendar.current_or_next_session(now)
            candidate = now.astimezone(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
            if candidate >= current.open:
                return candidate
        return last_completed_session(calendar, now).close - timedelta(minutes=1)
    raise ValueError(f"unsupported ingestion timeframe {timeframe}")


def _storable(series: list[BarRecord], now: datetime, calendar: MarketCalendar) -> list[BarRecord]:
    """Bars that are complete and, for minute bars, inside regular trading hours.

    Partial bars (session/minute not finished) and extended-hours minute bars are dropped:
    policy is regular hours only, and pre/post-market prints would distort session metrics.
    """
    if not series:
        return []
    if series[0].timeframe == "1Day":
        out = []
        for b in series:
            s = calendar.session(b.ts.astimezone(NY).date())
            if s is not None and s.close <= now:
                out.append(b)
        return out
    delta = TIMEFRAME_DELTA[series[0].timeframe]
    first = min(b.ts for b in series)
    last = max(b.ts for b in series)
    regular = set(calendar.trading_minutes(first, last + delta))
    return [b for b in series if b.ts + delta <= now and b.ts in regular]


def ingestion_symbols(session: Session, defaults: Iterable[str]) -> list[str]:
    """Defaults (benchmarks) plus every watchlist symbol, normalized and de-duplicated."""
    symbols = {s.strip().upper() for s in defaults}
    for wl in session.scalars(select(Watchlist)).all():
        symbols.update(str(s).strip().upper() for s in wl.symbols or [])
    return sorted(s for s in symbols if SYMBOL_RE.match(s))


def latest_stored(
    session: Session, symbols: Sequence[str], timeframe: str, adjustment: str
) -> dict[str, datetime]:
    rows = session.execute(
        select(Bar.symbol, func.max(Bar.ts))
        .where(Bar.symbol.in_(symbols), Bar.timeframe == timeframe, Bar.adjustment == adjustment)
        .group_by(Bar.symbol)
    ).all()
    return {sym: _utc(ts) for sym, ts in rows if ts is not None}


def upsert_bars(session: Session, bars: Sequence[BarRecord]) -> int:
    """Insert bars, replacing any existing row with the same (symbol, timeframe, ts, adj)."""
    if not bars:
        return 0
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert  # type: ignore[assignment]
    else:  # pragma: no cover
        raise RuntimeError(f"upsert not implemented for {dialect}")
    now = datetime.now(UTC)
    rows = [
        {
            "symbol": b.symbol,
            "timeframe": b.timeframe,
            "ts": b.ts.astimezone(UTC),
            "adjustment": b.adjustment,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "vwap": b.vwap,
            "trade_count": b.trade_count,
            "source": b.source,
            "ingested_at": now,
        }
        for b in bars
    ]
    updatable = ("open", "high", "low", "close", "volume", "vwap", "trade_count", "source")
    for i in range(0, len(rows), _UPSERT_CHUNK):
        stmt = insert(Bar).values(rows[i : i + _UPSERT_CHUNK])
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timeframe", "ts", "adjustment"],
            set_={c: stmt.excluded[c] for c in (*updatable, "ingested_at")},
        )
        session.execute(stmt)
    return len(rows)


def _issue_json(i: DataIssue) -> dict[str, Any]:
    return {
        "severity": i.severity,
        "code": i.code,
        "ts": i.ts.isoformat() if i.ts else None,
        "message": i.message,
    }


def ingest_bars(
    session: Session,
    source: BarSource,
    symbols: Sequence[str],
    timeframe: Timeframe,
    *,
    now: datetime,
    lookback: timedelta,
    incremental: bool,
    calendar: MarketCalendar | None = None,
    minute_tolerance: timedelta = timedelta(seconds=120),
    adjustment: str = "all",
) -> IngestionResult:
    """Fetch, validate and store bars for ``symbols``; write one report row per symbol.

    ``incremental`` fetches from each batch's oldest latest-stored bar (inclusive, so the last
    stored bar is refreshed) instead of the full ``lookback`` window. Daily bars use the full
    window so split/dividend adjustments to history are picked up.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"unsupported ingestion timeframe {timeframe}")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cal = calendar or MarketCalendar()
    result = IngestionResult(run_id=uuid.uuid4(), timeframe=timeframe)
    expected = expected_latest_bar(timeframe, now, cal)
    tolerance = minute_tolerance if timeframe == "1Min" else timedelta(0)
    floor = now - lookback

    for i in range(0, len(symbols), _BATCH_SYMBOLS):
        batch = list(symbols[i : i + _BATCH_SYMBOLS])
        stored = latest_stored(session, batch, timeframe, adjustment)
        start = floor
        if incremental and len(stored) == len(batch):
            start = max(floor, min(stored.values()))
        fetch_error: str | None = None
        fetched: dict[str, list[BarRecord]] = {}
        try:
            fetched = source.get_bars(batch, timeframe, start, now, adjustment)
        except Exception as exc:
            # Only the exception type: messages from HTTP clients can contain URLs.
            fetch_error = type(exc).__name__

        for symbol in batch:
            issues: list[DataIssue] = []
            series = fetched.get(symbol, [])
            complete = _storable(series, now, cal)
            if fetch_error is not None:
                issues.append(
                    DataIssue(
                        "critical", "fetch_error", symbol, None, f"fetch failed: {fetch_error}"
                    )
                )
            elif not complete:
                issues.append(DataIssue("warning", "no_new_bars", symbol, None, "no bars returned"))
            else:
                report = validate_bars(
                    complete, now=now, calendar=cal if timeframe == "1Min" else None
                )
                issues.extend(report.issues)
            if timeframe == "1Day":
                # Checked on the full series: _storable() drops these as never closing.
                issues.extend(
                    DataIssue("critical", "non_session_bar", symbol, b.ts, "bar on non-session")
                    for b in series
                    if cal.session(b.ts.astimezone(NY).date()) is None
                )

            validation_ok = not any(x.severity == "critical" for x in issues)
            written = upsert_bars(session, complete) if validation_ok and complete else 0
            latest = stored.get(symbol)
            if written:
                newest = max(b.ts.astimezone(UTC) for b in complete)
                latest = newest if latest is None else max(latest, newest)
            stale = latest is None or latest < expected - tolerance
            if stale:
                issues.append(
                    DataIssue(
                        "critical",
                        "stale",
                        symbol,
                        latest,
                        f"latest stored bar {latest.isoformat() if latest else 'none'}, "
                        f"expected {expected.isoformat()}",
                    )
                )
            ok = not any(x.severity == "critical" for x in issues)
            session.add(
                DataQualityReport(
                    run_id=result.run_id,
                    ts=now,
                    symbol=symbol,
                    timeframe=timeframe,
                    source=source.source,
                    window_start=start,
                    window_end=now,
                    bars_fetched=len(series),
                    bars_written=written,
                    latest_bar_ts=latest,
                    expected_latest_ts=expected,
                    ok=ok,
                    stale=stale,
                    issues=[_issue_json(x) for x in issues[:_MAX_STORED_ISSUES]],
                )
            )
            result.outcomes.append(
                SymbolOutcome(
                    symbol=symbol,
                    ok=ok,
                    stale=stale,
                    bars_fetched=len(series),
                    bars_written=written,
                    latest_bar_ts=latest,
                    issue_codes=tuple(dict.fromkeys(x.code for x in issues)),
                )
            )
    session.flush()
    return result
