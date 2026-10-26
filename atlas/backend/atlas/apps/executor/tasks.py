"""Execution-service tasks (queue: ``execution``).

This is the ONLY process that loads ``BrokerSettings``. The gateway is created lazily so that
importing this module elsewhere (e.g. for task registration in the research worker) never
touches credentials; such a process would fail at gateway creation because it has no
ALPACA_* environment variables.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
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
from atlas.core.data.universe import (
    UniverseBuildError,
    UniverseCriteria,
    build_universe_snapshot,
)
from atlas.core.execution.broker import BrokerGateway
from atlas.core.execution.pipeline import ExecutionDeps, process_pending_signals
from atlas.core.execution.protection import (
    cancel_orphan_stops,
    ensure_protection,
    protective_stop_ids,
)
from atlas.core.execution.reconciliation import reconcile
from atlas.core.models.session import session_scope
from atlas.core.observability.logging import get_logger
from atlas.core.risk import kill_switch
from atlas.core.risk.engine import QuoteState
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
        # Consolidated (SIP) daily bars; the free plan serves SIP only up to 15 minutes ago.
        now = now - timedelta(minutes=16)
    else:
        lookback, incremental = timedelta(days=settings.ingest_minute_lookback_days), True
    tolerance = timedelta(seconds=get_policy().policy.data_quality.max_bar_age_seconds)
    service = f"ingest_{timeframe.lower()}"
    try:
        source = get_sip_bar_source() if timeframe == "1Day" else get_market_data()
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


@lru_cache(maxsize=1)
def get_sip_bar_source() -> BarSource:
    """Consolidated (SIP) bars. IEX alone is a few percent of volume and its highs/lows come
    only from IEX prints, so daily bars (strategies, universe) use the consolidated tape."""
    from atlas.integrations.alpaca.market_data import AlpacaMarketData

    return AlpacaMarketData.from_settings(BrokerSettings(), feed="sip")  # type: ignore[call-arg]


@celery_app.task(name="atlas.execution.refresh_universe", soft_time_limit=840, time_limit=900)
def refresh_universe(force: bool = False) -> dict[str, object]:
    now = datetime.now(UTC)
    try:
        gateway = get_gateway()
        source = get_sip_bar_source()
        with session_scope() as s:
            snap, created = build_universe_snapshot(
                s,
                gateway,  # type: ignore[arg-type]
                source,
                UniverseCriteria.from_policy(get_policy().policy),
                now=now,
                force=force,
            )
            summary: dict[str, object] = {
                "snapshot_id": snap.id,
                "as_of": snap.as_of.isoformat(),
                "members": snap.member_count,
                "assets_seen": snap.assets_seen,
                "created": created,
            }
            beat(s, "universe", "ok", **summary)
    except Exception as exc:
        # Our own build errors carry a safe reason; anything else is logged by type only.
        reason = str(exc)[:200] if isinstance(exc, UniverseBuildError) else type(exc).__name__
        log.error("universe_refresh_failed", error=reason)
        with session_scope() as s:
            beat(s, "universe", "error", error=type(exc).__name__)
        build_notifier().notify(
            Event.CRITICAL_ERROR,
            f"[PAPER TRADING] Universe refresh failed ({type(exc).__name__}); "
            "the previous snapshot stays in use.",
        )
        return {"ok": False, "error": type(exc).__name__}
    log.info("universe_refreshed", **summary)
    return {"ok": True, **summary}


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
            orphans = cancel_orphan_stops(s, gateway)
            if orphans:
                log.warning("orphan_stops_cancelled", orders=orphans)
            protection = ensure_protection(s, gateway, datetime.now(UTC))
            for act in protection:
                log.info(
                    "protective_stop",
                    symbol=act.symbol,
                    strategy=act.strategy_id,
                    qty=str(act.qty),
                    stop=str(act.stop_price),
                    outcome=act.outcome,
                )
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
            s,
            gateway,
            reconcile=lambda: reconcile(s, gateway),
            notifier=build_notifier(),
            keep_client_order_ids=protective_stop_ids(s),
        )
    return {"cancelled": result.cancelled_order_ids, "errors": result.errors}


def quote_provider() -> Callable[[str], QuoteState | None]:
    """Latest quote: the stream's Redis cache if fresh, else Alpaca's REST latest quote."""
    import redis

    from atlas.core.data.live import LiveStore

    settings = get_settings()
    max_age = get_policy().policy.data_quality.max_quote_age_seconds
    store = LiveStore(redis.Redis.from_url(settings.redis_url, socket_timeout=2))
    md = get_market_data()

    def quote_for(symbol: str) -> QuoteState | None:
        try:
            snap = store.read([symbol]).get(symbol)
        except Exception:
            snap = None
        if snap is not None and snap.quote is not None:
            age = (datetime.now(UTC) - snap.quote.ts).total_seconds()
            if age <= max_age:
                return QuoteState(bid=snap.quote.bid, ask=snap.quote.ask, ts=snap.quote.ts)
        try:
            return md.latest_quote(symbol)  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning("latest_quote_failed", symbol=symbol, error=type(exc).__name__)
            return None

    return quote_for


@celery_app.task(name="atlas.execution.execute_signals", soft_time_limit=240, time_limit=300)
def execute_signals() -> dict[str, object]:
    now = datetime.now(UTC)
    cal = MarketCalendar()
    if not cal.is_open(now):
        return {"ok": True, "skipped": "market closed"}
    try:
        deps = ExecutionDeps(gateway=get_gateway(), quote_for=quote_provider())
        with session_scope() as s:
            outcomes = process_pending_signals(
                s, deps, now=now, policy=get_policy().policy, calendar=cal
            )
            summary = Counter(f"{o.mode}:{o.status}" for o in outcomes)
            beat(s, "execution", "ok", **dict(summary))
    except Exception as exc:
        log.error("execute_signals_failed", error=type(exc).__name__)
        with session_scope() as s:
            beat(s, "execution", "error", error=type(exc).__name__)
        build_notifier().notify(
            Event.CRITICAL_ERROR,
            f"[PAPER TRADING] Signal execution failed: {type(exc).__name__}",
        )
        return {"ok": False, "error": type(exc).__name__}
    for o in outcomes:
        if o.mode == "paper" and o.status in ("ORDERED", "REJECTED"):
            build_notifier().notify(
                Event.ORDER_SUBMITTED,
                f"[PAPER TRADING] {o.kind} {o.symbol}: {o.status}"
                + (f" ({', '.join(o.failed)})" if o.failed else ""),
            )
    return {"ok": True, **dict(summary)}
