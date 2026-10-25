from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select, text

from atlas.core.models.db import ServiceHeartbeat

router = APIRouter(tags=["health"])

HEARTBEAT_STALE_AFTER = timedelta(minutes=3)


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(request: Request, response: Response) -> dict[str, object]:
    checks: dict[str, object] = {}
    ok = True
    try:
        with request.app.state.session_factory() as s:
            s.execute(text("SELECT 1"))
            beats = s.scalars(select(ServiceHeartbeat)).all()
        checks["database"] = "ok"
        now = datetime.now(UTC)
        checks["services"] = {
            b.service: (
                "ok"
                if now - (b.last_seen if b.last_seen.tzinfo else b.last_seen.replace(tzinfo=UTC))
                < HEARTBEAT_STALE_AFTER
                else "stale"
            )
            for b in beats
        }
    except Exception:
        checks["database"] = "unavailable"
        ok = False
    redis = request.app.state.redis
    if redis is None:
        checks["redis"] = "not_configured"
    else:
        try:
            redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
            ok = False
    checks["policy_sha256"] = request.app.state.policy.sha256
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", "checks": checks}
