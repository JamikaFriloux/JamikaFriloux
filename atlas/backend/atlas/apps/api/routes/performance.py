"""Performance: account vs SPY, and per-strategy backtest / forward-sim / paper records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.apps.api.deps import get_db, require_role
from atlas.core.backtesting.validation import params_hash
from atlas.core.models.db import Role, TrackRecord, User
from atlas.core.performance.account import account_performance
from atlas.core.performance.track_record import (
    FORWARD_SIM,
    PAPER,
    anchor_report,
    backtest_reference,
    passing_track_record,
)
from atlas.core.strategies import registry

router = APIRouter(prefix="/api/v1", tags=["performance"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _record(r: TrackRecord, *, full: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": r.id,
        "kind": r.kind,
        "strategy_id": r.strategy_id,
        "version": r.version,
        "as_of": r.as_of.isoformat(),
        "start": r.start.isoformat() if r.start else None,
        "sessions": r.sessions,
        "created_at": _iso(r.created_at),
        "anchor_report_id": r.anchor_report_id,
        "metrics": r.metrics,
        "gates": r.gates,
        "passed": r.passed,
        "note": r.note,
        "open_positions": r.open_positions,
        "trade_count": len(r.trades or []),
    }
    if full:
        out["equity_curve"] = r.equity_curve
        out["trades"] = r.trades
    return out


def _latest(db: Session, strategy_id: str, kind: str, version: str, ph: str) -> TrackRecord | None:
    return db.scalars(
        select(TrackRecord)
        .where(
            TrackRecord.strategy_id == strategy_id,
            TrackRecord.kind == kind,
            TrackRecord.version == version,
            TrackRecord.params_hash == ph,
        )
        .order_by(TrackRecord.as_of.desc(), TrackRecord.id.desc())
        .limit(1)
    ).first()


@router.get("/performance")
def performance(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    policy = request.app.state.policy
    strategies = []
    for row in registry.sync_registry(db):
        ph = params_hash(row.params)
        fwd = _latest(db, row.id, FORWARD_SIM, row.version, ph)
        paper = _latest(db, row.id, PAPER, row.version, ph)
        strategies.append(
            {
                "id": row.id,
                "version": row.version,
                "status": row.status.value,
                "backtest": backtest_reference(anchor_report(db, row)),
                "forward_sim": _record(fwd) if fwd else None,
                "paper": _record(paper) if paper else None,
                "live_candidate_record": passing_track_record(db, row.id, policy),
            }
        )
    return {
        "account": account_performance(db),
        "strategies": strategies,
        "track_record_gates": policy.policy.track_record_gates.model_dump(),
    }


@router.get("/track-records/{record_id}")
def get_track_record(
    record_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    r = db.get(TrackRecord, record_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "track record not found")
    return _record(r, full=True)
