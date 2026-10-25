"""NYSE trading calendar (holidays, early closes, DST) via exchange_calendars (XNYS).

All inputs/outputs are timezone-aware. Naive datetimes are rejected rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")


class NaiveDatetimeError(ValueError):
    pass


def _require_aware(ts: datetime) -> pd.Timestamp:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise NaiveDatetimeError("timezone-aware datetime required")
    return pd.Timestamp(ts).tz_convert("UTC")


@dataclass(frozen=True)
class Session:
    day: date
    open: datetime  # UTC
    close: datetime  # UTC

    @property
    def is_early_close(self) -> bool:
        return self.close.astimezone(NY).hour < 16


@lru_cache(maxsize=1)
def _calendar() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS")


class MarketCalendar:
    def __init__(self) -> None:
        self._cal = _calendar()

    def is_trading_day(self, day: date) -> bool:
        return bool(self._cal.is_session(pd.Timestamp(day)))

    def session(self, day: date) -> Session | None:
        ts = pd.Timestamp(day)
        if not self._cal.is_session(ts):
            return None
        return Session(
            day=day,
            open=self._cal.session_open(ts).to_pydatetime(),
            close=self._cal.session_close(ts).to_pydatetime(),
        )

    def is_open(self, ts: datetime) -> bool:
        """True only during regular trading hours."""
        t = _require_aware(ts)
        return bool(self._cal.is_open_on_minute(t, ignore_breaks=True))

    def current_or_next_session(self, ts: datetime) -> Session:
        t = _require_aware(ts)
        day = t.tz_convert(NY).date()
        for offset in range(0, 15):
            s = self.session(day + timedelta(days=offset))
            if s is not None and s.close > t.to_pydatetime():
                return s
        raise RuntimeError("no session found within 15 days")  # pragma: no cover

    def minutes_since_open(self, ts: datetime) -> float | None:
        if not self.is_open(ts):
            return None
        s = self.current_or_next_session(ts)
        return (ts - s.open).total_seconds() / 60

    def minutes_to_close(self, ts: datetime) -> float | None:
        if not self.is_open(ts):
            return None
        s = self.current_or_next_session(ts)
        return (s.close - ts).total_seconds() / 60

    def sessions_between(self, start: date, end: date) -> list[date]:
        return [
            d.date() for d in self._cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
        ]

    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]:
        """Regular-session minute open times in [start, end)."""
        s, e = _require_aware(start), _require_aware(end)
        minutes = self._cal.minutes_in_range(s, e - pd.Timedelta(minutes=1))
        return [m.to_pydatetime() for m in minutes]


def compare_with_broker_calendar(
    local: MarketCalendar, broker_sessions: list[tuple[date, datetime, datetime]]
) -> list[str]:
    """Cross-check broker-reported sessions (e.g. Alpaca /calendar) against XNYS.

    Returns human-readable discrepancies; an empty list means they agree.
    """
    issues = []
    for day, open_, close in broker_sessions:
        s = local.session(day)
        if s is None:
            issues.append(f"{day}: broker reports a session, XNYS does not")
        elif s.open != open_ or s.close != close:
            issues.append(
                f"{day}: open/close mismatch broker={open_}/{close} xnys={s.open}/{s.close}"
            )
    return issues
