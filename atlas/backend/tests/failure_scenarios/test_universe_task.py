from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select

from atlas.apps.executor import tasks
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.ingestion import last_completed_session
from atlas.core.data.universe import UniverseCriteria
from atlas.core.models.db import ServiceHeartbeat, UniverseSnapshot
from atlas.integrations.telegram.notifier import Event
from tests.fakes import FakeAssetSource, FakeBarSource, RecordingNotifier, daily_series, make_asset


def _run(session_factory, assets, bars, notifier):
    @contextmanager
    def scope():
        with session_factory() as s:
            yield s
            s.commit()

    loose = UniverseCriteria(min_price=Decimal(10), min_adv_usd=Decimal(1), min_members=1)
    with (
        patch.object(tasks, "session_scope", scope),
        patch.object(tasks, "get_gateway", lambda: assets),
        patch.object(tasks, "get_sip_bar_source", lambda: bars),
        patch.object(tasks, "build_notifier", lambda: notifier),
        patch.object(tasks.UniverseCriteria, "from_policy", lambda _p: loose),
    ):
        return tasks.refresh_universe.run()


def test_refresh_universe_success(session_factory):
    cal = MarketCalendar()
    as_of = last_completed_session(cal, datetime.now(UTC)).day
    days = cal.sessions_between(as_of - timedelta(days=45), as_of)[-20:]
    bars = FakeBarSource({"AAA": daily_series("AAA", days)})
    notifier = RecordingNotifier()
    out = _run(session_factory, FakeAssetSource([make_asset("AAA")]), bars, notifier)
    assert out["ok"] is True and out["members"] == 1 and out["created"] is True
    assert notifier.messages == []
    with session_factory() as s:
        assert s.get(ServiceHeartbeat, "universe").status == "ok"


def test_refresh_universe_failure_alerts_and_keeps_previous(session_factory):
    assets = FakeAssetSource([make_asset("AAA")])
    assets.error = ConnectionError("down")
    notifier = RecordingNotifier()
    out = _run(session_factory, assets, FakeBarSource({}), notifier)
    assert out == {"ok": False, "error": "UniverseBuildError"}
    assert notifier.events == [Event.CRITICAL_ERROR]
    assert "previous snapshot stays in use" in notifier.messages[0][0]
    with session_factory() as s:
        assert s.get(ServiceHeartbeat, "universe").status == "error"
        assert s.scalars(select(UniverseSnapshot)).all() == []
