"""Strategies, signals, risk decisions and orders (read models), plus strategy status changes.

The API cannot create orders. Status changes are admin-only, need password re-entry, and
promotion is gated by validation reports (see core/strategies/registry.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.apps.api.deps import client_ip, get_db, require_role
from atlas.core.models.db import (
    Order,
    RiskDecision,
    Role,
    SignalRecord,
    StrategyStatus,
    User,
    ValidationReport,
)
from atlas.core.security import audit
from atlas.core.security.auth import verify_password
from atlas.core.strategies import registry

router = APIRouter(prefix="/api/v1", tags=["trading"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _num(v: Any) -> str | None:
    return None if v is None else str(v)


@router.get("/strategies")
def list_strategies(
    db: Session = Depends(get_db), _user: User = Depends(require_role(Role.VIEWER))
) -> list[dict[str, Any]]:
    rows = registry.sync_registry(db)  # idempotent: writes only when the code changed
    counts = dict(
        db.execute(
            select(SignalRecord.strategy_id, func.count()).group_by(SignalRecord.strategy_id)
        ).all()
    )
    out = []
    for r in rows:
        strat = registry.STRATEGIES.get(r.id)
        out.append(
            {
                "id": r.id,
                "version": r.version,
                "status": r.status.value,
                "description": strat.description if strat else None,
                "lookback_sessions": strat.lookback if strat else None,
                "params": r.params,
                "updated_at": _iso(r.updated_at),
                "updated_by": r.updated_by,
                "signals": counts.get(r.id, 0),
                "can_submit_paper_orders": r.status == StrategyStatus.PAPER,
            }
        )
    return out


class StatusChange(BaseModel):
    status: StrategyStatus
    reason: str = Field(min_length=3, max_length=500)
    password: str = Field(min_length=1, max_length=256)


@router.post("/strategies/{strategy_id}/status")
def change_strategy_status(
    strategy_id: str,
    body: StatusChange,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "re-authentication failed")
    registry.sync_registry(db)
    try:
        row = registry.set_status(
            db,
            strategy_id,
            body.status,
            actor=user.username,
            reason=body.reason,
            ip_address=client_ip(request),
        )
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found") from None
    except registry.StatusChangeRefused as exc:
        db.commit()  # keep registry sync; the refused change itself wrote nothing
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    db.commit()
    return {"id": row.id, "status": row.status.value, "version": row.version}


@router.get("/signals")
def list_signals(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> list[dict[str, Any]]:
    sigs = db.scalars(
        select(SignalRecord)
        .order_by(SignalRecord.as_of.desc(), SignalRecord.created_at.desc())
        .limit(limit)
    ).all()
    latest: dict[str, RiskDecision] = {}
    if sigs:
        for d in db.scalars(
            select(RiskDecision)
            .where(RiskDecision.signal_id.in_([s.id for s in sigs]))
            .order_by(RiskDecision.id)
        ).all():
            latest[d.signal_id or ""] = d
    return [
        {
            "id": s.id,
            "strategy_id": s.strategy_id,
            "strategy_version": s.strategy_version,
            "symbol": s.symbol,
            "kind": s.kind,
            "as_of": s.as_of.isoformat(),
            "ref_price": _num(s.ref_price),
            "stop_price": _num(s.stop_price),
            "mode": s.mode,
            "status": s.status,
            "reason": s.reason,
            "decision": None
            if s.id not in latest
            else {
                "approved": latest[s.id].approved,
                "failed": latest[s.id].failed,
                "qty": _num(latest[s.id].qty),
                "limit_price": _num(latest[s.id].limit_price),
                "ts": _iso(latest[s.id].ts),
            },
        }
        for s in sigs
    ]


@router.get("/risk-decisions")
def list_risk_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    rejected_only: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> list[dict[str, Any]]:
    q = select(RiskDecision)
    if rejected_only:
        q = q.where(RiskDecision.approved.is_(False))
    rows = db.scalars(q.order_by(RiskDecision.id.desc()).limit(limit)).all()
    return [
        {
            "id": d.id,
            "ts": _iso(d.ts),
            "signal_id": d.signal_id,
            "strategy_id": d.strategy_id,
            "symbol": d.symbol,
            "kind": d.kind,
            "mode": d.mode,
            "approved": d.approved,
            "qty": _num(d.qty),
            "limit_price": _num(d.limit_price),
            "capital_base": _num(d.capital_base),
            "failed": d.failed,
            "checks": d.checks,
        }
        for d in rows
    ]


@router.get("/orders")
def list_orders(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> list[dict[str, Any]]:
    rows = db.scalars(select(Order).order_by(Order.created_at.desc()).limit(limit)).all()
    return [
        {
            "client_order_id": o.client_order_id,
            "symbol": o.symbol,
            "side": o.side,
            "type": o.order_type,
            "purpose": o.purpose,
            "qty": _num(o.qty),
            "limit_price": _num(o.limit_price),
            "stop_price": _num(o.stop_price),
            "time_in_force": o.time_in_force,
            "state": o.state.value,
            "filled_qty": _num(o.filled_qty),
            "filled_avg_price": _num(o.filled_avg_price),
            "strategy_id": o.strategy_id,
            "signal_id": o.signal_id,
            "created_at": _iso(o.created_at),
            "submitted_at": _iso(o.submitted_at),
            "last_error": o.last_error,
        }
        for o in rows
    ]


@router.post("/strategies/{strategy_id}/validate", status_code=status.HTTP_202_ACCEPTED)
def request_validation(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    if strategy_id not in registry.STRATEGIES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    dispatched = request.app.state.dispatch_validation(strategy_id, user.username)
    audit.record(
        db,
        actor=user.username,
        action="strategy.validation_requested",
        target=strategy_id,
        details={"dispatched": dispatched},
        ip_address=client_ip(request),
    )
    if not dispatched:
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "could not queue the validation job"
        )
    return {"queued": True, "strategy_id": strategy_id}


def _report_summary(r: ValidationReport, promotable_id: str | None) -> dict[str, Any]:
    full = (r.metrics or {}).get("full", {})
    return {
        "id": r.id,
        "created_at": _iso(r.created_at),
        "strategy_id": r.strategy_id,
        "version": r.version,
        "params_hash": r.params_hash,
        "passed": r.passed,
        "currently_valid_for_promotion": promotable_id == str(r.id),
        "data_start": r.data_start.isoformat(),
        "data_end": r.data_end.isoformat(),
        "symbols": len(r.symbols or []),
        "failed_gates": [g["name"] for g in r.gates if not g["passed"]],
        "headline": {
            k: full.get(k)
            for k in (
                "trades",
                "cagr_pct",
                "sharpe",
                "max_drawdown_pct",
                "profit_factor",
                "win_rate_pct",
            )
        },
        "runtime_seconds": float(r.runtime_seconds),
        "requested_by": r.requested_by,
    }


@router.get("/validation-reports")
def list_validation_reports(
    strategy_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> list[dict[str, Any]]:
    q = select(ValidationReport)
    if strategy_id:
        q = q.where(ValidationReport.strategy_id == strategy_id)
    rows = db.scalars(q.order_by(ValidationReport.id.desc()).limit(limit)).all()
    promotable = {
        sid: registry.passing_validation_report(db, sid, s.version, StrategyStatus.PAPER)
        for sid, s in registry.STRATEGIES.items()
    }
    return [_report_summary(r, promotable.get(r.strategy_id)) for r in rows]


@router.get("/validation-reports/{report_id}")
def get_validation_report(
    report_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    r = db.get(ValidationReport, report_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")
    strat = registry.STRATEGIES.get(r.strategy_id)
    promotable = (
        registry.passing_validation_report(db, r.strategy_id, strat.version, StrategyStatus.PAPER)
        if strat
        else None
    )
    return {
        **_report_summary(r, promotable),
        "params": r.params,
        "policy_sha256": r.policy_sha256,
        "symbol_list": r.symbols,
        "gates": r.gates,
        "metrics": r.metrics,
        "equity_curve": r.equity_curve,
        "caveats": r.caveats,
    }
