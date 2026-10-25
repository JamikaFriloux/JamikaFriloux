"""Execution-service tasks (queue: ``execution``).

This is the ONLY process that loads ``BrokerSettings``. The gateway is created lazily so that
importing this module elsewhere (e.g. for task registration in the research worker) never
touches credentials; such a process would fail at gateway creation because it has no
ALPACA_* environment variables.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from celery import Task

from atlas.apps.worker.celery_app import celery_app
from atlas.apps.worker.heartbeat import beat
from atlas.core.configuration.policy import get_policy
from atlas.core.configuration.settings import BrokerSettings, get_settings
from atlas.core.data.bars import Timeframe
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.ingestion import (
    BarSource,
    IngestionResult,
    ingest_bars,
    ingestion_symbols,
    last_completed_session,
)
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


@lru_cache(maxsize=1)
def get_market_data() -> BarSource:
    from atlas.integrations.alpaca.market_data import AlpacaMarketData

    return AlpacaMarketData.from_settings(BrokerSettings())  # type: ignore[call-arg]


def _run_ingestion(timeframe: Timeframe, now: datetime) -> dict[str, object]:
    settings = get_settings()
    if timeframe == "1Day":
        lookback, incremental = timedelta(days=settings.ingest_daily_lookback_days), False
    else:
        lookback, incremental = timedelta(days=settings.ingest_minute_lookback_days), True
    tolerance = timedelta(seconds=get_policy().policy.data_quality.max_bar_age_seconds)
    service = f"ingest_{timeframe.lower()}"
    try:
        source = get_market_data()
        with session_scope() as s:
            result: IngestionResult = ingest_bars(
                s,
                source,
                ingestion_symbols(s, settings.ingest_default_symbols),
                timeframe,
                now=now,
                lookback=lookback,
                incremental=incremental,
                minute_tolerance=tolerance,
            )
            summary = result.summary()
            beat(s, service, "ok" if result.ok else "degraded", **summary)
    except Exception as exc:
        log.error("ingestion_failed", timeframe=timeframe, error=type(exc).__name__)
        with session_scope() as s:
            beat(s, service, "error", error=type(exc).__name__)
        build_notifier().notify(
            Event.CRITICAL_ERROR,
            f"[PAPER TRADING] {timeframe} bar ingestion failed: {type(exc).__name__}",
        )
        return {"ok": False, "error": type(exc).__name__}
    log.info("ingestion_complete", **summary)
    if not result.ok:
        build_notifier().notify(
            Event.CRITICAL_ERROR,
            f"[PAPER TRADING] {timeframe} data quality: failed={result.failed_symbols[:10]} "
            f"stale={result.stale_symbols[:10]}",
        )
    return {"ok": result.ok, **summary}


@celery_app.task(name="atlas.execution.ingest_daily_bars")
def ingest_daily_bars() -> dict[str, object]:
    return _run_ingestion("1Day", datetime.now(UTC))


@celery_app.task(name="atlas.execution.ingest_minute_bars")
def ingest_minute_bars() -> dict[str, object]:
    now = datetime.now(UTC)
    cal = MarketCalendar()
    # Run during the session and for 30 minutes after the close to pick up the final bars.
    if not cal.is_open(now) and now - last_completed_session(cal, now).close > timedelta(
        minutes=30
    ):
        return {"ok": True, "skipped": "market closed"}
    return _run_ingestion("1Min", now)


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
