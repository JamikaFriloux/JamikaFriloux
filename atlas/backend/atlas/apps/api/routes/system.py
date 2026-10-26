from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.apps.api.deps import client_ip, get_db, require_role
from atlas.core.execution.state_machine import OPEN_BROKER_STATES
from atlas.core.models.db import (
    AccountSnapshot,
    AuditLog,
    DataQualityReport,
    Order,
    Position,
    Role,
    ServiceHeartbeat,
    User,
)
from atlas.core.risk import kill_switch
from atlas.core.security.auth import verify_password

router = APIRouter(prefix="/api/v1", tags=["system"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _kill_switch_view(db: Session) -> dict[str, Any]:
    ks = kill_switch.get_state(db)
    return {
        "engaged": ks.engaged,
        "reason": ks.reason,
        "engaged_at": _iso(ks.engaged_at),
        "engaged_by": ks.engaged_by,
        "resumed_at": _iso(ks.resumed_at),
        "resumed_by": ks.resumed_by,
    }


@router.get("/status")
def system_status(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    policy = request.app.state.policy
    snap = db.scalar(select(AccountSnapshot).order_by(AccountSnapshot.ts.desc()).limit(1))
    # Baseline for total P/L: the account's equity at ATLAS's first broker sync (real data;
    # the policy's starting equity is a sizing budget and may differ from the paper account).
    first = db.scalar(select(AccountSnapshot).order_by(AccountSnapshot.ts.asc()).limit(1))
    open_orders = db.scalar(
        select(func.count()).select_from(Order).where(Order.state.in_(OPEN_BROKER_STATES))
    )
    positions = db.scalars(select(Position).order_by(Position.symbol)).all()
    beats = db.scalars(select(ServiceHeartbeat)).all()
    limits = policy.policy.limits
    return {
        "trading_mode": "PAPER",
        "server_time": datetime.now(UTC).isoformat(),
        "kill_switch": _kill_switch_view(db),
        "trading_allowed": kill_switch.is_trading_allowed(db),
        "account": None
        if snap is None
        else {
            "as_of": _iso(snap.ts),
            "source": snap.source,
            "status": snap.account_status,
            "equity": str(snap.equity),
            "cash": str(snap.cash),
            "buying_power": str(snap.buying_power),
            "long_market_value": str(snap.long_market_value),
            "day_pl": str(snap.equity - snap.last_equity),
            "total_pl": str(snap.equity - first.equity) if first is not None else None,
            "total_pl_since": _iso(first.ts) if first is not None else None,
            "capital_base": str(
                min(snap.equity, Decimal(str(policy.policy.account.starting_equity_usd)))
            ),
            "shorting_enabled": snap.shorting_enabled,
            "trading_blocked": snap.trading_blocked,
        },
        "positions": [
            {
                "symbol": p.symbol,
                "qty": str(p.qty),
                "avg_entry_price": str(p.avg_entry_price),
                "market_value": str(p.market_value),
                "unrealized_pl": str(p.unrealized_pl),
                "synced_at": _iso(p.synced_at),
            }
            for p in positions
        ],
        "open_orders": open_orders or 0,
        "market_regime": None,  # produced by the Market Intelligence agent (Phase 5)
        "services": [
            {"service": b.service, "status": b.status, "last_seen": _iso(b.last_seen)}
            for b in beats
        ],
        "policy": {
            "sha256": policy.sha256,
            "version": policy.policy.version,
            "limits": limits.model_dump(),
        },
    }


class EngageRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ResumeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    password: str = Field(min_length=1, max_length=256)


@router.get("/kill-switch")
def get_kill_switch(
    db: Session = Depends(get_db), _user: User = Depends(require_role(Role.VIEWER))
) -> dict[str, Any]:
    return _kill_switch_view(db)


@router.post("/kill-switch/engage")
def engage_kill_switch(
    body: EngageRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.OPERATOR)),
) -> dict[str, Any]:
    changed = kill_switch.engage(
        db, actor=user.username, reason=body.reason, ip_address=client_ip(request)
    )
    # Commit BEFORE dispatching follow-up work so the flag is visible to the executor first.
    db.commit()
    dispatched = False
    if changed:
        dispatched = request.app.state.dispatch_kill_switch_actions()
    return {"changed": changed, "follow_up_dispatched": dispatched, **_kill_switch_view(db)}


@router.post("/kill-switch/resume")
def resume_kill_switch(
    body: ResumeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "re-authentication failed")
    try:
        kill_switch.resume(
            db,
            actor=user.username,
            reason=body.reason,
            authorized=True,
            ip_address=client_ip(request),
        )
    except kill_switch.KillSwitchError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return _kill_switch_view(db)


@router.get("/audit")
def audit_log(
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN)),
) -> list[dict[str, Any]]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).all()
    return [
        {
            "id": r.id,
            "ts": _iso(r.ts),
            "actor": r.actor,
            "action": r.action,
            "target": r.target,
            "details": r.details,
        }
        for r in rows
    ]


@router.get("/data/quality")
def data_quality(
    db: Session = Depends(get_db), _user: User = Depends(require_role(Role.VIEWER))
) -> list[dict[str, Any]]:
    """Latest ingestion report for each symbol and timeframe."""
    latest = (
        select(
            DataQualityReport.symbol,
            DataQualityReport.timeframe,
            func.max(DataQualityReport.id).label("id"),
        )
        .group_by(DataQualityReport.symbol, DataQualityReport.timeframe)
        .subquery()
    )
    rows = db.scalars(
        select(DataQualityReport)
        .join(latest, DataQualityReport.id == latest.c.id)
        .order_by(DataQualityReport.symbol, DataQualityReport.timeframe)
    ).all()
    return [
        {
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "checked_at": _iso(r.ts),
            "source": r.source,
            "ok": r.ok,
            "stale": r.stale,
            "latest_bar_ts": _iso(r.latest_bar_ts),
            "expected_latest_ts": _iso(r.expected_latest_ts),
            "bars_written": r.bars_written,
            "issues": r.issues,
        }
        for r in rows
    ]
