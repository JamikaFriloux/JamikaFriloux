from datetime import UTC, date, datetime

import pytest

from atlas.core.data.calendar import (
    NY,
    MarketCalendar,
    NaiveDatetimeError,
    compare_with_broker_calendar,
)

cal = MarketCalendar()


def test_holidays_and_weekends():
    assert not cal.is_trading_day(date(2026, 11, 26))  # Thanksgiving
    assert not cal.is_trading_day(date(2026, 12, 25))  # Christmas
    assert not cal.is_trading_day(date(2026, 10, 24))  # Saturday
    assert cal.is_trading_day(date(2026, 10, 26))


def test_early_close_day_after_thanksgiving():
    s = cal.session(date(2026, 11, 27))
    assert s is not None and s.is_early_close
    assert s.close.astimezone(NY).hour == 13


def test_dst_shifts_utc_open():
    summer = cal.session(date(2026, 7, 1))
    winter = cal.session(date(2026, 12, 1))
    assert summer.open.astimezone(UTC).hour == 13 and summer.open.astimezone(UTC).minute == 30
    assert winter.open.astimezone(UTC).hour == 14
    assert summer.open.astimezone(NY).hour == winter.open.astimezone(NY).hour == 9


def test_is_open_regular_hours_only():
    assert cal.is_open(datetime(2026, 10, 26, 10, 0, tzinfo=NY))
    assert not cal.is_open(datetime(2026, 10, 26, 8, 0, tzinfo=NY))  # premarket
    assert not cal.is_open(datetime(2026, 10, 26, 16, 30, tzinfo=NY))  # after hours
    assert not cal.is_open(datetime(2026, 11, 26, 11, 0, tzinfo=NY))  # holiday


def test_naive_datetimes_rejected():
    with pytest.raises(NaiveDatetimeError):
        cal.is_open(datetime(2026, 10, 26, 10, 0))


def test_minutes_to_close_and_since_open():
    t = datetime(2026, 10, 26, 15, 45, tzinfo=NY)
    assert cal.minutes_to_close(t) == 15
    assert cal.minutes_since_open(datetime(2026, 10, 26, 9, 35, tzinfo=NY)) == 5
    assert cal.minutes_to_close(datetime(2026, 10, 26, 17, 0, tzinfo=NY)) is None


def test_next_session_from_weekend():
    s = cal.current_or_next_session(datetime(2026, 10, 24, 12, 0, tzinfo=NY))
    assert s.day == date(2026, 10, 26)


def test_broker_calendar_cross_check():
    s = cal.session(date(2026, 10, 26))
    assert compare_with_broker_calendar(cal, [(s.day, s.open, s.close)]) == []
    issues = compare_with_broker_calendar(cal, [(date(2026, 11, 26), s.open, s.close)])
    assert issues and "XNYS does not" in issues[0]
