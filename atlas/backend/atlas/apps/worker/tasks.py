"""Research-worker tasks. This process has no brokerage credentials."""

from __future__ import annotations

from datetime import UTC, datetime

from atlas.apps.worker.celery_app import celery_app
from atlas.apps.worker.heartbeat import beat
from atlas.core.data.calendar import MarketCalendar
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
