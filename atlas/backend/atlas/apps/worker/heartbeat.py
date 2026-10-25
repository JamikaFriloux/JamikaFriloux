from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from atlas.core.models.db import ServiceHeartbeat, utcnow


def beat(session: Session, service: str, status: str = "ok", **details: Any) -> None:
    row = session.get(ServiceHeartbeat, service)
    if row is None:
        row = ServiceHeartbeat(service=service)
        session.add(row)
    row.last_seen = utcnow()
    row.status = status
    row.details = details
