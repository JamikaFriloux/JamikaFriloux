"""Technical Analysis: an indicator snapshot of every ingested symbol, one report per day.

Indicators are computed here from stored daily bars; the LLM only highlights what stands out.
The narrative may mention only symbols from the snapshot (checked in code).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from atlas.agents.base import AgentInput, AgentSpec
from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.ingestion import last_completed_session
from atlas.core.indicators import atr, rolling_max, rolling_min, rsi, sma
from atlas.core.strategies.engine import load_daily_bars
from atlas.integrations.llm.base import LLMSchemaError

LOOKBACK = 260


class SymbolNote(BaseModel):
    symbol: str
    note: str = Field(max_length=400)


class TechnicalNarrative(BaseModel):
    summary: str = Field(max_length=1500)
    notable: list[SymbolNote] = Field(max_length=10)
    data_gaps: list[str] = Field(max_length=5)


def check(output: TechnicalNarrative, features: dict[str, Any]) -> None:
    known = {row["symbol"] for row in features.get("symbols", [])}
    unknown = sorted({n.symbol for n in output.notable} - known)
    if unknown:
        raise LLMSchemaError(f"narrative names symbols not in the snapshot: {unknown}")


SPEC: AgentSpec[TechnicalNarrative] = AgentSpec(
    name="technical_analysis",
    prompt_version="ta-1",
    system=(
        "You review a table of technical indicators for a watchlist of US stocks and ETFs. "
        "Point out the few symbols whose readings stand out (extended trends, oversold or "
        "overbought RSI, unusual volatility, symbols at range extremes) and say why, using "
        "only the given values. Do not predict prices."
    ),
    schema=TechnicalNarrative,
    check=check,
)


def _pct(a: float, b: float | None) -> float | None:
    return None if b is None or b == 0 else round(100 * (a / b - 1), 2)


def snapshot(symbol: str, bars: Sequence[BarRecord]) -> dict[str, Any] | None:
    if len(bars) < 21:
        return None
    c = [float(b.close) for b in bars]
    h = [float(b.high) for b in bars]
    lo = [float(b.low) for b in bars]
    s20, s50, s200 = sma(c, 20)[-1], sma(c, 50)[-1], sma(c, 200)[-1]
    a14, r14 = atr(h, lo, c, 14)[-1], rsi(c, 14)[-1]
    hi20, lo20 = rolling_max(h, 20)[-1], rolling_min(lo, 20)[-1]
    close = c[-1]
    if s50 is None or s200 is None:
        trend = "insufficient_history"
    elif close > s50 > s200:
        trend = "up"
    elif close < s50 < s200:
        trend = "down"
    else:
        trend = "mixed"
    return {
        "symbol": symbol,
        "as_of": bars[-1].ts.date().isoformat(),
        "close": round(close, 2),
        "trend": trend,
        "vs_sma20_pct": _pct(close, s20),
        "vs_sma50_pct": _pct(close, s50),
        "vs_sma200_pct": _pct(close, s200),
        "rsi14": None if r14 is None else round(r14, 1),
        "atr14_pct": None if a14 is None else round(100 * a14 / close, 2),
        "return_20d_pct": _pct(close, c[-21]),
        "from_20d_high_pct": _pct(close, hi20),
        "from_20d_low_pct": _pct(close, lo20),
    }


def gather(
    session: Session, *, now: datetime, calendar: MarketCalendar, symbols: Sequence[str]
) -> AgentInput:
    expected: date = last_completed_session(calendar, now).day
    bars = load_daily_bars(session, list(symbols), expected, LOOKBACK)
    rows, missing, stale = [], [], []
    for sym in sorted(bars):
        snap = snapshot(sym, bars[sym])
        if snap is None:
            missing.append(sym)
            continue
        if snap["as_of"] != expected.isoformat():
            stale.append(sym)
        rows.append(snap)
    features = {
        "expected_session": expected.isoformat(),
        "symbols": rows,
        "missing_history": missing,
        "stale": stale,
    }
    return AgentInput("watchlist", expected, features, has_data=bool(rows))
