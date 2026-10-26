"""Research-worker tasks. This process has no brokerage credentials."""

from __future__ import annotations

from datetime import UTC, datetime

from atlas.apps.worker.celery_app import celery_app
from atlas.apps.worker.heartbeat import beat
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.session import session_scope
from atlas.core.observability.logging import get_logger
from atlas.integrations.telegram.notifier import Event, build_notifier

log = get_logger(__name__)


@celery_app.task(name="atlas.worker.heartbeat")
def heartbeat() -> None:
    with session_scope() as s:
        beat(s, "worker")


@celery_app.task(name="atlas.worker.premarket_readiness")
def premarket_readiness() -> dict[str, object]:
    """Phase 1 premarket job: confirms the session calendar. Later phases add universe
    refresh, regime classification and the premarket report."""
    now = datetime.now(UTC)
    cal = MarketCalendar()
    trading_day = cal.is_trading_day(now.date())
    result: dict[str, object] = {"date": now.date().isoformat(), "trading_day": trading_day}
    if trading_day:
        s = cal.session(now.date())
        assert s is not None
        result.update(open=s.open.isoformat(), close=s.close.isoformat(), early=s.is_early_close)
        build_notifier().notify(
            Event.PREMARKET_REPORT,
            f"[PAPER TRADING] Premarket {result['date']}: session "
            f"{s.open:%H:%M}-{s.close:%H:%M} UTC" + (" (early close)" if s.is_early_close else ""),
        )
    log.info("premarket_readiness", **result)
    return result


@celery_app.task(name="atlas.worker.generate_signals")
def generate_signals() -> dict[str, object]:
    """After the close: run every active strategy on the day's stored daily bars."""
    from atlas.core.configuration.settings import get_settings
    from atlas.core.data.ingestion import last_completed_session
    from atlas.core.strategies.engine import generate_signals as run_engine

    now = datetime.now(UTC)
    cal = MarketCalendar()
    as_of = last_completed_session(cal, now).day
    if as_of != now.astimezone(NY).date():
        return {"ok": True, "skipped": "no session closed today"}
    try:
        with session_scope() as s:
            summary = run_engine(
                s, as_of=as_of, default_symbols=get_settings().ingest_default_symbols, calendar=cal
            )
            beat(s, "signals", "ok", as_of=summary["as_of"], scope=summary["scope"])
    except Exception as exc:
        log.error("generate_signals_failed", error=type(exc).__name__)
        with session_scope() as s:
            beat(s, "signals", "error", error=type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}
    log.info("signals_generated", **{k: v for k, v in summary.items() if k != "strategies"})
    return {"ok": True, **summary}


@celery_app.task(name="atlas.worker.validate_strategy", soft_time_limit=3300, time_limit=3600)
def validate_strategy(strategy_id: str, requested_by: str = "system") -> dict[str, object]:
    """Backtest validation for one strategy version; records an immutable report."""
    from atlas.core.backtesting.runner import run_validation
    from atlas.core.configuration.policy import get_policy
    from atlas.core.configuration.settings import get_settings

    try:
        with session_scope() as s:
            report = run_validation(
                s,
                strategy_id,
                policy=get_policy(),
                calendar=MarketCalendar(),
                default_symbols=get_settings().ingest_default_symbols,
                requested_by=requested_by,
            )
            result: dict[str, object] = {
                "ok": True,
                "report_id": report.id,
                "passed": report.passed,
                "runtime_seconds": float(report.runtime_seconds),
            }
    except Exception as exc:
        log.error(
            "validation_failed",
            strategy=strategy_id,
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}
    log.info("validation_complete", strategy=strategy_id, **result)
    return result
