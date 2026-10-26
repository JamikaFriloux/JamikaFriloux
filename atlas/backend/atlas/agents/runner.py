"""Run the research agents in order. Research worker only (no broker credentials)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from atlas.agents.base import AgentInput, AgentSpec, latest_report, run_agent
from atlas.agents.market_intelligence import agent as market_intelligence
from atlas.agents.news_sentiment import agent as news_sentiment
from atlas.agents.operations import agent as operations
from atlas.agents.performance_analysis import agent as performance_analysis
from atlas.agents.technical_analysis import agent as technical_analysis
from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.calendar import MarketCalendar
from atlas.core.observability.logging import get_logger
from atlas.integrations.llm.base import LLMProvider

log = get_logger(__name__)

AGENTS = (
    "market_intelligence",
    "technical_analysis",
    "news_sentiment",
    "performance_analysis",
    "operations",  # last: it reports on the others
)


def run_research(
    session: Session,
    provider: LLMProvider,
    *,
    now: datetime,
    calendar: MarketCalendar,
    policy: RiskPolicy,
    symbols: Sequence[str],
    max_calls_per_day: int,
    model: str | None = None,
    only: Sequence[str] | None = None,
) -> dict[str, Any]:
    gatherers: dict[str, tuple[AgentSpec[Any], Callable[[], AgentInput]]] = {
        "market_intelligence": (
            market_intelligence.SPEC,
            lambda: market_intelligence.gather(
                session, now=now, calendar=calendar, symbols=symbols
            ),
        ),
        "technical_analysis": (
            technical_analysis.SPEC,
            lambda: technical_analysis.gather(session, now=now, calendar=calendar, symbols=symbols),
        ),
        "news_sentiment": (
            news_sentiment.SPEC,
            lambda: news_sentiment.gather(session, now=now, symbols=symbols),
        ),
        "performance_analysis": (
            performance_analysis.SPEC,
            lambda: performance_analysis.gather(session, now=now, calendar=calendar, policy=policy),
        ),
        "operations": (
            operations.SPEC,
            lambda: operations.gather(session, now=now, calendar=calendar),
        ),
    }
    results: dict[str, Any] = {}
    for name in AGENTS:
        if only is not None and name not in only:
            continue
        spec, gather = gatherers[name]
        try:
            with session.begin_nested():
                report = run_agent(
                    session,
                    spec,
                    gather(),
                    provider,
                    now=now,
                    max_calls_per_day=max_calls_per_day,
                    model=model,
                )
            results[name] = {"id": report.id, "status": report.status}
        except Exception as exc:  # one agent failing must not stop the others
            log.error("agent_failed", agent=name, error=type(exc).__name__)
            results[name] = {"status": "error", "error": type(exc).__name__}
    return results


def regime_view(session: Session) -> dict[str, Any] | None:
    """The latest regime for ``/status``: the deterministic label plus the LLM summary."""
    rep = latest_report(session, "market_intelligence")
    if rep is None:
        return None
    f = rep.features
    return {
        "regime": f.get("regime"),
        "trend": f.get("trend"),
        "volatility": f.get("volatility"),
        "benchmark": f.get("benchmark"),
        "as_of": f.get("as_of"),
        "stale": f.get("stale"),
        "report_id": rep.id,
        "created_at": rep.created_at.isoformat(),
        "summary": (rep.narrative or {}).get("summary"),
    }
