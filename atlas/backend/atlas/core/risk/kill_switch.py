"""Emergency kill switch.

Engaging the kill switch:
  1. disables new order submissions (persisted flag, checked before every submission),
  2. cancels eligible outstanding orders at the broker,
  3. reconciles account and order state,
  4. alerts the operator,
  5. requires explicit operator authorization (admin + password re-entry) to resume.

Positions are NOT liquidated. A liquidation policy would need separate review.

Steps 2-4 run in the execution service (the only holder of broker credentials); the API only
flips the persisted flag and enqueues the follow-up job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from atlas.core.models.db import KillSwitch, utcnow
from atlas.core.observability.logging import get_logger
from atlas.core.security import audit

log = get_logger(__name__)


class KillSwitchError(RuntimeError):
    pass


def get_state(session: Session) -> KillSwitch:
    row = session.get(KillSwitch, 1)
    if row is None:
        # Missing row (should be seeded by the migration): fail closed.
        row = KillSwitch(id=1, engaged=True, reason="kill switch row missing", engaged_by="system")
        session.add(row)
        session.flush()
    return row


def is_trading_allowed(session: Session) -> bool:
    """Fail closed: any error reading the flag means trading is NOT allowed."""
    try:
        row = session.execute(select(KillSwitch).where(KillSwitch.id == 1)).scalar_one_or_none()
    except SQLAlchemyError:
        log.error("kill_switch_read_failed")
        return False
    return row is not None and not row.engaged


def engage(session: Session, *, actor: str, reason: str, ip_address: str | None = None) -> bool:
    """Engage the kill switch. Returns True if it changed state. Idempotent."""
    if not reason.strip():
        raise KillSwitchError("a reason is required")
    row = get_state(session)
    if row.engaged:
        return False
    row.engaged = True
    row.reason = reason
    row.engaged_at = utcnow()
    row.engaged_by = actor
    audit.record(
        session,
        actor=actor,
        action="kill_switch.engage",
        details={"reason": reason},
        ip_address=ip_address,
    )
    log.warning("kill_switch_engaged", actor=actor, reason=reason)
    return True


def resume(
    session: Session, *, actor: str, reason: str, authorized: bool, ip_address: str | None = None
) -> None:
    """Disengage. ``authorized`` must reflect a fresh, successful admin re-authentication."""
    if not authorized:
        raise KillSwitchError("explicit operator authorization is required to resume")
    if not reason.strip():
        raise KillSwitchError("a reason is required")
    row = get_state(session)
    if not row.engaged:
        raise KillSwitchError("kill switch is not engaged")
    row.engaged = False
    row.resumed_at = utcnow()
    row.resumed_by = actor
    audit.record(
        session,
        actor=actor,
        action="kill_switch.resume",
        details={"reason": reason},
        ip_address=ip_address,
    )
    log.warning("kill_switch_resumed", actor=actor)


class BrokerControl(Protocol):
    def cancel_all_open_orders(self) -> list[str]: ...


class Notifier(Protocol):
    def send(self, text: str, *, critical: bool = False) -> bool: ...


@dataclass
class KillSwitchReport:
    cancelled_order_ids: list[str] = field(default_factory=list)
    reconciled: bool = False
    errors: list[str] = field(default_factory=list)


def execute_engagement_actions(
    session: Session,
    broker: BrokerControl,
    reconcile: object,
    notifier: Notifier,
) -> KillSwitchReport:
    """Run steps 2-4. Each step is attempted even if an earlier one fails."""
    report = KillSwitchReport()
    try:
        report.cancelled_order_ids = broker.cancel_all_open_orders()
    except Exception as exc:  # broker errors must not stop reconciliation/alerting
        report.errors.append(f"cancel failed: {type(exc).__name__}")
    try:
        if callable(reconcile):
            reconcile()
        report.reconciled = True
    except Exception as exc:
        report.errors.append(f"reconcile failed: {type(exc).__name__}")
    row = get_state(session)
    audit.record(
        session,
        actor="system",
        action="kill_switch.actions",
        details={
            "cancelled": report.cancelled_order_ids,
            "reconciled": report.reconciled,
            "errors": report.errors,
        },
    )
    notifier.send(
        "[PAPER] KILL SWITCH ENGAGED\n"
        f"Reason: {row.reason}\nBy: {row.engaged_by}\n"
        f"Cancelled orders: {len(report.cancelled_order_ids)}\n"
        f"Reconciled: {report.reconciled}\n"
        + (f"Errors: {'; '.join(report.errors)}\n" if report.errors else "")
        + "New orders are disabled. Positions were NOT liquidated. "
        "Admin authorization is required to resume.",
        critical=True,
    )
    return report
