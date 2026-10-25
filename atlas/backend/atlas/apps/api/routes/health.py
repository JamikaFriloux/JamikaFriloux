from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select, text

from atlas.core.models.db import ServiceHeartbeat

router = APIRouter(tags=["health"])

HEARTBEAT_STALE_AFTER = timedelta(minutes=3)
# Services that heartbeat continuously (every 15-60 s). Scheduled jobs (ingestion, universe)
# heartbeat only when they run, so an old heartbeat is normal for them and not "stale".
CONTINUOUS_SERVICES = frozenset({"worker", "executor", "broker", "stream"})


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
        services: dict[str, str] = {}
        for b in beats:
            seen = b.last_seen if b.last_seen.tzinfo else b.last_seen.replace(tzinfo=UTC)
            stale = b.service in CONTINUOUS_SERVICES and now - seen >= HEARTBEAT_STALE_AFTER
            # Report what the service itself said (ok / degraded / error), not just that it
            # is alive: a connected-but-failing stream must not read as "ok".
            services[b.service] = "stale" if stale else b.status
        checks["services"] = services
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
