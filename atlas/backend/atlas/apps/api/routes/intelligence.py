"""AI research agents: reports and news. Read-only views plus a manual run trigger.

Agent output is advisory. These endpoints never change trading state.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.agents.base import CALLED, latest_report
from atlas.agents.runner import AGENTS, regime_view
from atlas.apps.api.deps import client_ip, get_db, require_role
from atlas.core.data.calendar import NY
from atlas.core.models.db import AgentReport, NewsArticle, Role, User
from atlas.core.security import audit

router = APIRouter(prefix="/api/v1", tags=["intelligence"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _report(r: AgentReport, *, full: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": r.id,
        "agent": r.agent,
        "scope": r.scope,
        "as_of": r.as_of.isoformat(),
        "created_at": _iso(r.created_at),
        "status": r.status,
        "provider": r.provider,
        "model": r.model,
        "prompt_version": r.prompt_version,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "error": r.error,
        "has_narrative": r.narrative is not None,
    }
    if full:
        out["features"] = r.features
        out["narrative"] = r.narrative
    return out


def _scope(agent: str) -> str:
    return {
        "market_intelligence": "market",
        "technical_analysis": "watchlist",
        "news_sentiment": "watchlist",
        "performance_analysis": "account",
        "operations": "system",
    }[agent]


@router.get("/intelligence")
def intelligence_overview(
    db: Session = Depends(get_db), _user: User = Depends(require_role(Role.VIEWER))
) -> dict[str, Any]:
    start = datetime.combine(datetime.now(UTC).astimezone(NY).date(), time.min, NY)
    used = db.scalars(
        select(AgentReport).where(AgentReport.created_at >= start, AgentReport.status.in_(CALLED))
    ).all()
    agents = {}
    for name in AGENTS:
        rep = latest_report(db, name, _scope(name))
        agents[name] = None if rep is None else _report(rep)
    return {
        "advisory_only": True,
        "regime": regime_view(db),
        "agents": agents,
        "llm_usage_today": {
            "calls": len(used),
            "input_tokens": sum(r.input_tokens for r in used),
            "output_tokens": sum(r.output_tokens for r in used),
        },
    }


@router.get("/intelligence/reports")
def list_reports(
    agent: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> list[dict[str, Any]]:
    q = select(AgentReport).order_by(AgentReport.created_at.desc(), AgentReport.id.desc())
    if agent is not None:
        q = q.where(AgentReport.agent == agent)
    return [_report(r, full=False) for r in db.scalars(q.limit(limit)).all()]


@router.get("/intelligence/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    r = db.get(AgentReport, report_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")
    return _report(r)


@router.post("/intelligence/run", status_code=status.HTTP_202_ACCEPTED)
def run_agents(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.OPERATOR)),
) -> dict[str, Any]:
    dispatched = request.app.state.dispatch_agents()
    audit.record(
        db,
        actor=user.username,
        action="agents.run_requested",
        target="agents",
        details={"dispatched": dispatched},
        ip_address=client_ip(request),
    )
    if not dispatched:
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "could not queue the agents job")
    return {"queued": True}


@router.get("/news")
def list_news(
    symbol: str | None = Query(default=None, pattern=r"^[A-Za-z.]{1,10}$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    """Stored articles, newest first, joined with the latest sentiment assessment (if any).

    Headlines are external text; the dashboard renders them as plain text.
    """
    q = select(NewsArticle).order_by(NewsArticle.published_at.desc(), NewsArticle.id)
    rows = db.scalars(q.limit(1000 if symbol else limit)).all()
    if symbol:
        rows = [r for r in rows if symbol.upper() in (r.symbols or [])][:limit]
    assessed: dict[str, dict[str, Any]] = {}
    rep = latest_report(db, "news_sentiment", "watchlist")
    if rep is not None and rep.narrative:
        for a in rep.narrative.get("assessments", []):
            assessed[a["article_id"]] = a
    flagged = set((rep.narrative or {}).get("injection_suspected", [])) if rep else set()
    return {
        "sentiment_report_id": rep.id if rep else None,
        "sentiment_status": rep.status if rep else None,
        "articles": [
            {
                "id": r.id,
                "published_at": _iso(r.published_at),
                "provider": r.provider,
                "headline": r.headline,
                "summary": r.summary,
                "url": r.url if (r.url or "").startswith("https://") else None,
                "symbols": r.symbols,
                "assessment": assessed.get(r.id),
                "injection_suspected": r.id in flagged,
            }
            for r in rows
        ],
    }
