"""Deterministic market regime from benchmark daily bars.

The regime label comes only from this code; the LLM may explain it but never sets it.

  * trend: ``up`` when close > SMA200 and SMA50 > SMA200, ``down`` when both are below,
    otherwise ``mixed``;
  * volatility: 20-session realised volatility (annualised), ranked against its own last
    252 sessions: ``high`` at/above the 80th percentile or above 30%, ``low`` at/below the
    20th, otherwise ``normal``;
  * breadth: share of the other stored symbols closing above their SMA50 (context only).

  label            trend   volatility
  risk_on          up      low/normal
  volatile_uptrend up      high
  transition       mixed   any
  downtrend        down    low/normal
  risk_off         down    high
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from atlas.core.data.bars import BarRecord
from atlas.core.indicators import sma

MIN_SESSIONS = 200 + 20  # SMA200 plus a 20-session slope
VOL_WINDOW = 20
VOL_LOOKBACK = 252
HIGH_VOL_ABS = 0.30


def realised_vol(closes: Sequence[float], n: int = VOL_WINDOW) -> list[float | None]:
    """Annualised stdev of daily log returns over ``n`` sessions, aligned with ``closes``."""
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    out: list[float | None] = [None] * len(closes)
    for i in range(n, len(closes)):
        window = rets[i - n : i]
        mean = sum(window) / n
        var = sum((r - mean) ** 2 for r in window) / (n - 1)
        out[i] = math.sqrt(var) * math.sqrt(252)
    return out


def percentile_rank(history: Sequence[float], value: float) -> float:
    """Share of ``history`` at or below ``value``, in percent."""
    return 100.0 * sum(1 for h in history if h <= value) / len(history)


def label(trend: str, vol: str) -> str:
    if trend == "up":
        return "volatile_uptrend" if vol == "high" else "risk_on"
    if trend == "down":
        return "risk_off" if vol == "high" else "downtrend"
    return "transition"


def classify(
    benchmark: str,
    bars: Sequence[BarRecord],
    others: Mapping[str, Sequence[BarRecord]],
    *,
    expected_as_of: date,
) -> dict[str, Any]:
    """Features for the regime report; ``regime`` is ``unavailable`` without enough data."""
    if len(bars) < MIN_SESSIONS:
        return {
            "benchmark": benchmark,
            "regime": "unavailable",
            "reason": f"{len(bars)} daily bars stored, {MIN_SESSIONS} needed",
        }
    closes = [float(b.close) for b in bars]
    as_of = bars[-1].ts.date()
    s50, s200 = sma(closes, 50), sma(closes, 200)
    close, ma50, ma200, ma50_prev = closes[-1], s50[-1], s200[-1], s50[-21]
    assert ma50 is not None and ma200 is not None and ma50_prev is not None
    if close > ma200 and ma50 > ma200:
        trend = "up"
    elif close < ma200 and ma50 < ma200:
        trend = "down"
    else:
        trend = "mixed"

    vols = realised_vol(closes)
    vol_now = vols[-1]
    assert vol_now is not None
    history = [v for v in vols[-VOL_LOOKBACK:] if v is not None]
    vol_pct = percentile_rank(history, vol_now)
    if vol_pct >= 80 or vol_now > HIGH_VOL_ABS:
        vol = "high"
    elif vol_pct <= 20:
        vol = "low"
    else:
        vol = "normal"

    high_252 = max(closes[-VOL_LOOKBACK:])
    above = counted = 0
    for series in others.values():
        if len(series) < 50 or series[-1].ts.date() != as_of:
            continue  # only symbols with a full SMA50 and a bar for the same session
        c = [float(b.close) for b in series]
        m = sma(c, 50)[-1]
        assert m is not None
        counted += 1
        above += c[-1] > m

    return {
        "benchmark": benchmark,
        "regime": label(trend, vol),
        "trend": trend,
        "volatility": vol,
        "as_of": as_of.isoformat(),
        "stale": as_of < expected_as_of,
        "close": round(close, 2),
        "sma50": round(ma50, 2),
        "sma200": round(ma200, 2),
        "close_vs_sma200_pct": round(100 * (close / ma200 - 1), 2),
        "sma50_slope_20d_pct": round(100 * (ma50 / ma50_prev - 1), 2),
        "realised_vol_20d_pct": round(100 * vol_now, 2),
        "vol_percentile_1y": round(vol_pct, 1),
        "drawdown_from_1y_high_pct": round(100 * (close / high_252 - 1), 2),
        "breadth_above_sma50_pct": round(100 * above / counted, 1) if counted else None,
        "breadth_symbols": counted,
        "sessions_used": len(bars),
    }
