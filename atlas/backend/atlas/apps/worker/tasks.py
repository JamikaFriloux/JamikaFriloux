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


@celery_app.task(name="atlas.worker.run_agents", soft_time_limit=840, time_limit=900)
def run_agents(only: list[str] | None = None) -> dict[str, object]:
    """Research agents (advisory only): deterministic features plus an optional LLM narrative."""
    from atlas.agents.runner import run_research
    from atlas.core.configuration.policy import get_policy
    from atlas.core.configuration.settings import LLMSettings, get_settings
    from atlas.core.data.ingestion import ingestion_symbols
    from atlas.integrations.llm.anthropic_provider import build_provider
    from atlas.integrations.llm.base import DisabledProvider, LLMError, LLMProvider

    llm = LLMSettings()
    provider: LLMProvider
    try:
        provider = build_provider(llm)
    except LLMError as exc:  # e.g. provider=anthropic without a key: features only
        log.warning("llm_unavailable", error=str(exc))
        provider = DisabledProvider()
    now = datetime.now(UTC)
    with session_scope() as s:
        symbols = ingestion_symbols(s, get_settings().ingest_default_symbols)
        results = run_research(
            s,
            provider,
            now=now,
            calendar=MarketCalendar(),
            policy=get_policy().policy,
            symbols=symbols,
            max_calls_per_day=llm.max_calls_per_day,
            model=llm.model,
            only=only,
        )
        errors = [k for k, v in results.items() if v["status"] == "error"]
        beat(s, "agents", "error" if errors else "ok", provider=provider.name, failed=errors)
    log.info("agents_run", **{k: v["status"] for k, v in results.items()})
    return {"ok": not errors, "agents": results}


@celery_app.task(name="atlas.worker.update_track_records", soft_time_limit=840, time_limit=900)
def update_track_records() -> dict[str, object]:
    """After the close: forward-simulated and paper track records for every strategy."""
    from atlas.core.configuration.policy import get_policy
    from atlas.core.data.ingestion import last_completed_session
    from atlas.core.performance.track_record import update_track_records as run_update
    from atlas.core.strategies.registry import STRATEGIES, sync_registry

    now = datetime.now(UTC)
    cal = MarketCalendar()
    as_of = last_completed_session(cal, now).day
    try:
        with session_scope() as s:
            rows = sync_registry(s)
            summary = run_update(
                s,
                strategies=STRATEGIES,
                rows=rows,
                policy=get_policy(),
                calendar=cal,
                as_of=as_of,
                now=now,
            )
            beat(s, "track_records", "ok", as_of=as_of.isoformat(), strategies=len(summary))
    except Exception as exc:
        log.error("track_records_failed", error=type(exc).__name__, detail=str(exc)[:200])
        with session_scope() as s:
            beat(s, "track_records", "error", error=type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}
    log.info("track_records_updated", as_of=as_of.isoformat(), strategies=list(summary))
    return {"ok": True, "as_of": as_of.isoformat(), "strategies": summary}
