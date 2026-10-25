"""Audit trail helper. Writes in the caller's transaction so actions and their audit
records commit (or roll back) together."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from atlas.core.models.db import AuditLog
from atlas.core.observability.logging import get_logger, redact_mapping

log = get_logger(__name__)


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        target=target,
        details=redact_mapping(details or {}),
        ip_address=ip_address,
    )
    session.add(entry)
    log.info("audit", actor=actor, action=action, target=target)
    return entry
