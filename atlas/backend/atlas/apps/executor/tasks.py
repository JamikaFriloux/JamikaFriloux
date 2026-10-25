"""Execution-service tasks (queue: ``execution``).

This is the ONLY process that loads ``BrokerSettings``. The gateway is created lazily so that
importing this module elsewhere (e.g. for task registration in the research worker) never
touches credentials; such a process would fail at gateway creation because it has no
ALPACA_* environment variables.
"""

from __future__ import annotations

from functools import lru_cache

from celery import Task

from atlas.apps.worker.celery_app import celery_app
from atlas.apps.worker.heartbeat import beat
from atlas.core.configuration.settings import BrokerSettings
from atlas.core.execution.broker import BrokerGateway
from atlas.core.execution.reconciliation import reconcile
from atlas.core.models.session import session_scope
from atlas.core.observability.logging import get_logger
from atlas.core.risk import kill_switch
from atlas.integrations.telegram.notifier import Event, build_notifier

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_gateway() -> BrokerGateway:
    from atlas.integrations.alpaca.trading import AlpacaPaperGateway

    return AlpacaPaperGateway.from_settings(BrokerSettings())  # type: ignore[call-arg]


@celery_app.task(name="atlas.execution.heartbeat")
def heartbeat() -> None:
    with session_scope() as s:
        beat(s, "executor")


@celery_app.task(name="atlas.execution.broker_sync")
def broker_sync() -> dict[str, object]:
    try:
        gateway = get_gateway()
        with session_scope() as s:
            report = reconcile(s, gateway)
            beat(
                s,
                "broker",
                "ok" if report.clean else "discrepancy",
                discrepancies=report.discrepancies[:20],
            )
    except Exception as exc:
        log.error("broker_sync_failed", error=type(exc).__name__)
        with session_scope() as s:
            beat(s, "broker", "error", error=type(exc).__name__)
        build_notifier().notify(
            Event.BROKER_DISCONNECTED,
            f"[PAPER TRADING] Broker sync failed: {type(exc).__name__}",
        )
        return {"ok": False, "error": type(exc).__name__}
    return {
        "ok": report.clean,
        "positions": report.positions,
        "discrepancies": report.discrepancies,
    }


@celery_app.task(
    name="atlas.execution.kill_switch_actions",
    bind=True,
    max_retries=20,
    retry_backoff=True,
    retry_backoff_max=300,
)
def kill_switch_actions(self: Task) -> dict[str, object]:
    # New orders are already blocked by the persisted flag; this task cancels and reconciles.
    # If the broker is unreachable it alerts and retries rather than being silently dropped.
    try:
        gateway = get_gateway()
    except Exception as exc:
        if self.request.retries == 0:
            build_notifier().send(
                "[PAPER] KILL SWITCH ENGAGED but the executor cannot reach the broker "
                f"({type(exc).__name__}). New orders are blocked; open-order cancellation "
                "will be retried.",
                critical=True,
            )
        raise self.retry(exc=exc) from exc
    with session_scope() as s:
        result = kill_switch.execute_engagement_actions(
            s, gateway, reconcile=lambda: reconcile(s, gateway), notifier=build_notifier()
        )
    return {"cancelled": result.cancelled_order_ids, "errors": result.errors}
