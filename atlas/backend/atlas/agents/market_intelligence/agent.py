"""Market Intelligence: the deterministic regime plus an optional explanation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from atlas.agents.base import AgentInput, AgentSpec, Narrative
from atlas.agents.market_intelligence.regime import MIN_SESSIONS, VOL_LOOKBACK, classify
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.ingestion import last_completed_session
from atlas.core.strategies.engine import load_daily_bars

SPEC: AgentSpec[Narrative] = AgentSpec(
    name="market_intelligence",
    prompt_version="mi-1",
    system=(
        "You explain the current US equity market regime to a trader reviewing a paper-trading "
        "system. The regime label, trend and volatility class are already decided by "
        "deterministic rules; explain what the features mean and what they do not tell us."
    ),
    schema=Narrative,
)


def gather(
    session: Session,
    *,
    now: datetime,
    calendar: MarketCalendar,
    symbols: Sequence[str],
    benchmark: str = "SPY",
) -> AgentInput:
    expected = last_completed_session(calendar, now).day
    wanted = sorted({benchmark, *symbols})
    bars = load_daily_bars(session, wanted, expected, MIN_SESSIONS + VOL_LOOKBACK)
    bench = bars.pop(benchmark, [])
    features = classify(benchmark, bench, bars, expected_as_of=expected)
    as_of = bench[-1].ts.date() if bench else expected
    return AgentInput("market", as_of, features, has_data=features["regime"] != "unavailable")
