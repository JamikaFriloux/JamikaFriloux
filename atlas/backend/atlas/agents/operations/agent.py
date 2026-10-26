"""Operations: a health digest of services, data quality, universe, news and agents."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.agents.base import AgentInput, AgentSpec, Narrative
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.universe import current_universe, is_stale
from atlas.core.models.db import AgentReport, DataQualityReport, NewsArticle, ServiceHeartbeat
from atlas.core.observability.heartbeats import CONTINUOUS_SERVICES, HEARTBEAT_STALE_AFTER
from atlas.core.risk import kill_switch

WINDOW = timedelta(hours=24)

SPEC: AgentSpec[Narrative] = AgentSpec(
    name="operations",
    prompt_version="op-1",
    system=(
        "You write the operations digest of a paper-trading system: which services are "
        "healthy, which data is missing or stale, and what an operator should look at first. "
        "Use only the given records and be specific about what is unknown."
    ),
    schema=Narrative,
)


def _aware(dt: datetime | None) -> datetime | None:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=UTC))


def gather(session: Session, *, now: datetime, calendar: MarketCalendar) -> AgentInput:
    now = now.astimezone(UTC)  # stored timestamps are UTC
    services = []
    for b in session.scalars(select(ServiceHeartbeat).order_by(ServiceHeartbeat.service)).all():
        seen = _aware(b.last_seen)
        assert seen is not None
        age = int((now - seen).total_seconds())
        details = b.details or {}
        continuous = b.service in CONTINUOUS_SERVICES
        services.append(
            {
                "service": b.service,
                "status": b.status,
                "continuous": continuous,
                "age_seconds": age,
                # Scheduled jobs only beat when they run: report when, not "stale".
                "stale": continuous and now - seen >= HEARTBEAT_STALE_AFTER,
                "last_run": None if continuous else seen.isoformat(timespec="minutes"),
                "error": details.get("error") or details.get("last_error"),
            }
        )
    dq = session.scalars(
        select(DataQualityReport).where(DataQualityReport.ts >= now - WINDOW)
    ).all()
    failing = sorted({f"{r.symbol}/{r.timeframe}" for r in dq if not r.ok})
    stale = sorted({f"{r.symbol}/{r.timeframe}" for r in dq if r.stale})
    issue_codes: Counter[str] = Counter(
        str(i.get("code", "unknown")) for r in dq for i in (r.issues or [])
    )
    uni = current_universe(session)
    news_last = _aware(session.scalar(select(func.max(NewsArticle.fetched_at))))
    agents = Counter(
        session.scalars(
            select(AgentReport.status).where(AgentReport.created_at >= now - WINDOW)
        ).all()
    )
    ks = kill_switch.get_state(session)
    features: dict[str, Any] = {
        "now": now,
        "market_open": calendar.is_open(now),
        "session_date": now.astimezone(NY).date(),
        "kill_switch": {"engaged": ks.engaged, "reason": ks.reason},
        "services": services,
        "data_quality_24h": {
            "reports": len(dq),
            "failing": failing[:15],
            "failing_count": len(failing),
            "stale": stale[:15],
            "stale_count": len(stale),
            "issue_codes": dict(issue_codes.most_common(8)),
        },
        "universe": None
        if uni is None
        else {
            "as_of": uni.as_of,
            "members": uni.member_count,
            "stale": is_stale(uni, now, calendar),
        },
        "news_last_fetched": news_last,
        "agent_reports_24h": dict(agents),
    }
    # The clock changes every run; hash on the state, not on ``now``.
    hashed = {k: v for k, v in features.items() if k != "now"}
    hashed["services"] = [{k: v for k, v in s.items() if k != "age_seconds"} for s in services]
    return AgentInput("system", now.astimezone(NY).date(), hashed, meta={"now": now.isoformat()})
