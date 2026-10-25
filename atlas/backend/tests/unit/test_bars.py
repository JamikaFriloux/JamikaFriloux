from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from atlas.core.data.bars import BarRecord, validate_bars
from atlas.core.data.calendar import NY, MarketCalendar

T0 = datetime(2026, 10, 26, 10, 0, tzinfo=NY)


def bar(i=0, o="100", h="101", l="99", c="100.5", v="1000", ts=None, tf="1Min"):  # noqa: E741
    return BarRecord(
        symbol="SPY",
        timeframe=tf,
        ts=ts or T0 + timedelta(minutes=i),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal(v),
        source="test",
        adjustment="all",
    )


def codes(report):
    return {i.code for i in report.issues}


def test_clean_series_passes():
    bars = [bar(i) for i in range(5)]
    r = validate_bars(
        bars, now=T0 + timedelta(minutes=6), max_age=timedelta(minutes=2), calendar=MarketCalendar()
    )
    assert r.ok and not r.issues


def test_naive_timestamp_rejected_at_model():
    with pytest.raises(ValidationError):
        BarRecord(
            symbol="SPY",
            timeframe="1Min",
            ts=datetime(2026, 1, 1),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
            source="t",
            adjustment="all",
        )


@pytest.mark.parametrize(
    ("bars", "code"),
    [
        ([], "empty"),
        ([bar(0), bar(0)], "duplicate_ts"),
        ([bar(1), bar(0)], "non_monotonic"),
        ([bar(0, h="99.5")], "ohlc_inconsistent"),
        ([bar(0, l="100.6")], "ohlc_inconsistent"),
        ([bar(0, o="0", l="0")], "non_positive_price"),
        ([bar(0, v="-1")], "negative_volume"),
        ([bar(0, ts=T0 + timedelta(days=1))], "future_ts"),
    ],
)
def test_critical_issues(bars, code):
    r = validate_bars(bars, now=T0 + timedelta(minutes=10))
    assert code in codes(r) and not r.ok


def test_stale_data_is_critical():
    r = validate_bars([bar(0)], now=T0 + timedelta(minutes=30), max_age=timedelta(minutes=2))
    assert "stale" in codes(r) and not r.ok


def test_missing_minutes_warn_only():
    r = validate_bars([bar(0), bar(5)], now=T0 + timedelta(minutes=6), calendar=MarketCalendar())
    assert "missing_bars" in codes(r) and r.ok


def test_sudden_gap_flagged_as_warning():
    r = validate_bars(
        [bar(0), bar(1, o="160", h="161", l="159", c="160")], now=T0 + timedelta(minutes=5)
    )
    assert "extreme_move" in codes(r) and r.ok
