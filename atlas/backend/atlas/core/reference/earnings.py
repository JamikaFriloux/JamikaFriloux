"""Earnings calendar storage and the entry blackout.

A provider fetch stores every report in its window plus one ``earnings_coverage`` row. The
blackout for a symbol on session ``today`` (policy ``block_entries_before_earnings_days`` = N):

  * ETF (config/instruments.yaml or a provider): never blacked out; funds don't report;
  * a stored report on ``today`` or any of the next N sessions: blacked out (whether or not
    the calendar is fresh: a known report is never ignored);
  * a classified stock with no report in that span, and a fetch younger than
    ``earnings_max_age_hours`` whose window covers the span: clear;
  * anything else (no fresh fetch, or an unclassified symbol): unknown, so the risk engine
    rejects the entry (fail closed).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.data.calendar import MarketCalendar
from atlas.core.models.db import EarningsCoverage, EarningsEvent, InstrumentReference


@dataclass(frozen=True)
class EarningsItem:
    symbol: str
    day: date
    timing: str = "unknown"  # bmo / amc / dmh / unknown


def store_calendar(
    session: Session,
    source: str,
    items: Iterable[EarningsItem],
    *,
    window_start: date,
    window_end: date,
    now: datetime,
) -> EarningsCoverage:
    """Replace ``source``'s events in the window with this fetch (dates move) and record
    coverage. Only call this with a complete, successful fetch."""
    old = session.scalars(
        select(EarningsEvent).where(
            EarningsEvent.source == source,
            EarningsEvent.day >= window_start,
            EarningsEvent.day <= window_end,
        )
    ).all()
    for row in old:
        session.delete(row)
    session.flush()
    seen: set[tuple[str, date]] = set()
    for it in items:
        if not (window_start <= it.day <= window_end) or (it.symbol, it.day) in seen:
            continue
        seen.add((it.symbol, it.day))
        session.add(
            EarningsEvent(
                symbol=it.symbol.upper(),
                day=it.day,
                timing=it.timing,
                source=source,
                fetched_at=now,
            )
        )
    cov = EarningsCoverage(
        source=source,
        fetched_at=now,
        window_start=window_start,
        window_end=window_end,
        events=len(seen),
    )
    session.add(cov)
    session.flush()
    return cov


def blackout_span(today: date, days: int, calendar: MarketCalendar) -> list[date]:
    """``today`` (if it is a session) and the next ``days`` sessions."""
    ahead = calendar.sessions_between(today, today + timedelta(days=days * 2 + 10))
    return ahead[: days + 1] if ahead and ahead[0] == today else ahead[:days]


def fresh_coverage(
    session: Session, *, start: date, end: date, now: datetime, max_age: timedelta
) -> EarningsCoverage | None:
    return session.scalars(
        select(EarningsCoverage)
        .where(
            EarningsCoverage.fetched_at >= now - max_age,
            EarningsCoverage.window_start <= start,
            EarningsCoverage.window_end >= end,
        )
        .order_by(EarningsCoverage.fetched_at.desc())
        .limit(1)
    ).first()


def blackout_lookup(
    session: Session,
    *,
    now: datetime,
    today: date,
    days: int,
    calendar: MarketCalendar,
    max_age: timedelta,
) -> Callable[[str], bool | None]:
    """Snapshot of everything the blackout needs, as a symbol -> bool | None function."""
    now = now.astimezone(UTC)
    span = blackout_span(today, days, calendar) or [today]
    kinds = dict(
        session.execute(select(InstrumentReference.symbol, InstrumentReference.asset_type)).all()
    )
    reporting = set(
        session.scalars(
            select(EarningsEvent.symbol).where(
                EarningsEvent.day >= span[0], EarningsEvent.day <= span[-1]
            )
        ).all()
    )
    covered = (
        fresh_coverage(session, start=span[0], end=span[-1], now=now, max_age=max_age) is not None
    )

    def lookup(symbol: str) -> bool | None:
        kind = kinds.get(symbol)
        if kind == "etf":
            return False
        if symbol in reporting:
            return True
        if kind == "stock" and covered:
            return False
        return None

    return lookup
