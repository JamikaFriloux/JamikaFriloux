"""Bar data model and deterministic data-quality validation.

Validation never repairs data silently. It reports issues; callers decide (and for trading,
any ``critical`` issue means: do not trade on this data).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from atlas.core.data.calendar import MarketCalendar

Timeframe = Literal["1Min", "5Min", "15Min", "1Hour", "1Day"]
TIMEFRAME_DELTA = {
    "1Min": timedelta(minutes=1),
    "5Min": timedelta(minutes=5),
    "15Min": timedelta(minutes=15),
    "1Hour": timedelta(hours=1),
    "1Day": timedelta(days=1),
}


class BarRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    ts: datetime  # bar open time, timezone-aware
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Decimal | None = None
    trade_count: int | None = None
    source: str
    adjustment: Literal["raw", "split", "dividend", "all"]

    @field_validator("ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("bar timestamp must be timezone-aware")
        return v


@dataclass(frozen=True)
class DataIssue:
    severity: Literal["critical", "warning"]
    code: str
    symbol: str
    ts: datetime | None
    message: str


@dataclass
class ValidationReport:
    issues: list[DataIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "critical" for i in self.issues)

    def add(self, *args: object) -> None:
        self.issues.append(DataIssue(*args))  # type: ignore[arg-type]


def validate_bars(
    bars: list[BarRecord],
    *,
    now: datetime,
    max_age: timedelta | None = None,
    calendar: MarketCalendar | None = None,
    max_abs_return: float = 0.5,
) -> ValidationReport:
    """Validate one symbol/timeframe series sorted by ts.

    Checks: ordering, duplicates, OHLC consistency, non-positive prices, negative volume,
    future timestamps, intraday gaps against the exchange calendar, extreme moves, staleness.
    """
    report = ValidationReport()
    if not bars:
        report.add("critical", "empty", "?", None, "no bars returned")
        return report
    symbol = bars[0].symbol
    seen: set[datetime] = set()
    prev: BarRecord | None = None
    for b in bars:
        if b.symbol != symbol or b.timeframe != bars[0].timeframe:
            report.add("critical", "mixed_series", b.symbol, b.ts, "mixed symbols/timeframes")
        if b.ts in seen:
            report.add("critical", "duplicate_ts", symbol, b.ts, "duplicate timestamp")
        seen.add(b.ts)
        if prev is not None and b.ts <= prev.ts:
            report.add("critical", "non_monotonic", symbol, b.ts, "timestamps not increasing")
        if b.ts > now:
            report.add("critical", "future_ts", symbol, b.ts, "bar timestamp is in the future")
        if min(b.open, b.high, b.low, b.close) <= 0:
            report.add("critical", "non_positive_price", symbol, b.ts, "price <= 0")
        if b.high < max(b.open, b.close, b.low) or b.low > min(b.open, b.close, b.high):
            report.add("critical", "ohlc_inconsistent", symbol, b.ts, "high/low inconsistent")
        if b.volume < 0:
            report.add("critical", "negative_volume", symbol, b.ts, "volume < 0")
        if prev is not None and prev.close > 0:
            ret = abs(float(b.close / prev.close) - 1)
            if ret > max_abs_return:
                # Could be a real gap, a halt reopening, or an unadjusted split.
                report.add("warning", "extreme_move", symbol, b.ts, f"close-to-close {ret:.1%}")
        prev = b

    tf = bars[0].timeframe
    if calendar is not None and tf == "1Min":
        expected = calendar.trading_minutes(bars[0].ts, bars[-1].ts + TIMEFRAME_DELTA[tf])
        missing = sorted(set(expected) - seen)
        if missing:
            # Thinly traded symbols legitimately have empty minutes on IEX; flag, don't fail.
            report.add(
                "warning",
                "missing_bars",
                symbol,
                missing[0],
                f"{len(missing)} missing minute bars in session",
            )

    if max_age is not None:
        age = now - (bars[-1].ts + TIMEFRAME_DELTA[tf])
        if age > max_age:
            report.add("critical", "stale", symbol, bars[-1].ts, f"latest bar is {age} old")
    return report
