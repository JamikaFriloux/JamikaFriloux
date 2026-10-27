from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import select

from atlas.apps.executor import tasks
from atlas.core.data.calendar import NY
from atlas.core.models.db import DataQualityReport, ServiceHeartbeat
from atlas.integrations.telegram.notifier import Event
from tests.fakes import FakeBarSource, RecordingNotifier, make_bar

NOW = datetime(2026, 10, 22, 17, 0, tzinfo=NY)  # after Thursday's close


def _patched(session_factory, source, notifier):
    @contextmanager
    def scope():
        with session_factory() as s:
            yield s
            s.commit()

    def no_source():
        raise RuntimeError("no credentials")

    return (
        patch.object(tasks, "session_scope", scope),
        patch.object(tasks, "get_market_data", (lambda: source) if source else no_source),
        patch.object(tasks, "get_sip_bar_source", (lambda: source) if source else no_source),
        patch.object(tasks, "build_notifier", lambda: notifier),
    )


def _run(session_factory, source, notifier):
    p1, p2, p3, p4 = _patched(session_factory, source, notifier)
    with p1, p2, p3, p4:
        return tasks._run_ingestion("1Day", NOW)


def test_daily_task_success_records_heartbeat(session_factory):
    days = [make_bar(s, datetime(2026, 10, d, tzinfo=NY)) for s in ("SPY", "QQQ", "IWM", "DIA")
            for d in (21, 22)]  # fmt: skip
    src = FakeBarSource({})
    for b in days:
        src.bars.setdefault(b.symbol, []).append(b)
    notifier = RecordingNotifier()
    out = _run(session_factory, src, notifier)
    assert out["ok"] is True and out["bars_written"] == 8
    assert notifier.messages == []
    with session_factory() as s:
        hb = s.get(ServiceHeartbeat, "ingest_1day")
        assert hb is not None and hb.status == "ok"


def test_data_outage_alerts_and_marks_degraded(session_factory):
    src = FakeBarSource({})
    src.error = TimeoutError("read timed out")
    notifier = RecordingNotifier()
    out = _run(session_factory, src, notifier)
    assert out["ok"] is False and len(out["failed"]) == 4
    assert notifier.events == [Event.CRITICAL_ERROR]
    assert "[PAPER TRADING]" in notifier.messages[0][0]
    with session_factory() as s:
        assert s.get(ServiceHeartbeat, "ingest_1day").status == "degraded"
        reports = s.scalars(select(DataQualityReport)).all()
        # Adjusted and raw daily bars each get a report per symbol.
        assert sorted(r.adjustment for r in reports) == ["all"] * 4 + ["raw"] * 4


def test_missing_credentials_fails_safely(session_factory):
    notifier = RecordingNotifier()
    out = _run(session_factory, None, notifier)
    assert out == {"ok": False, "error": "RuntimeError"}
    with session_factory() as s:
        assert s.get(ServiceHeartbeat, "ingest_1day").status == "error"
    assert notifier.events == [Event.CRITICAL_ERROR]


def test_minute_task_skips_when_market_long_closed():
    saturday = datetime(2026, 10, 24, 12, tzinfo=NY)
    with patch.object(tasks, "datetime") as dt, patch.object(tasks, "_run_ingestion") as run:
        dt.now.return_value = saturday
        assert tasks.ingest_minute_bars.run()["skipped"] == "market closed"
        run.assert_not_called()


def test_minute_task_runs_shortly_after_close():
    just_after = datetime(2026, 10, 22, 16, 10, tzinfo=NY)
    with patch.object(tasks, "datetime") as dt, patch.object(tasks, "_run_ingestion") as run:
        dt.now.return_value = just_after
        run.return_value = {"ok": True}
        tasks.ingest_minute_bars.run()
        run.assert_called_once_with("1Min", just_after)


def _result(*outcomes):
    import uuid

    from atlas.core.data.ingestion import IngestionResult, SymbolOutcome

    r = IngestionResult(run_id=uuid.uuid4(), timeframe="1Min")
    for sym, ok, stale, critical in outcomes:
        r.outcomes.append(SymbolOutcome(sym, ok, stale, 0, 0, None, critical, critical))
    return r


BENCH = ["SPY", "QQQ", "IWM", "DIA"]
WATCH = [(s, True, False, ()) for s in ("AAPL", "MSFT", "NVDA", "AMD", "META", "TSLA")]


def test_minute_alerts_skip_a_lone_stale_symbol():
    # As seen live 2026-10-27: IVV went 3 minutes without an IEX print.
    lone = _result(*WATCH, ("IVV", False, True, ("stale",)))
    assert not lone.ok and tasks.needs_alert(lone, "1Min", BENCH) is False
    assert tasks.needs_alert(lone, "1Day", BENCH) is True  # daily bars always alert


def test_minute_alerts_fire_on_real_problems():
    assert tasks.needs_alert(_result(*WATCH), "1Min", BENCH) is False
    benchmark = _result(*WATCH, ("SPY", False, True, ("stale",)))
    assert tasks.needs_alert(benchmark, "1Min", BENCH) is True
    bad_data = _result(*WATCH, ("IVV", False, False, ("ohlc_inconsistent",)))
    assert tasks.needs_alert(bad_data, "1Min", BENCH) is True
    fetch = _result(*WATCH, ("IVV", False, True, ("fetch_error", "stale")))
    assert tasks.needs_alert(fetch, "1Min", BENCH) is True
    many = _result(*WATCH[:4], *[(s, False, True, ("stale",)) for s in ("A1", "A2")])
    assert tasks.needs_alert(many, "1Min", BENCH) is True  # 2 of 6 > 25%


def test_minute_outage_still_alerts(session_factory):
    src = FakeBarSource({})
    src.error = TimeoutError("read timed out")
    notifier = RecordingNotifier()
    p1, p2, p3, p4 = _patched(session_factory, src, notifier)
    with p1, p2, p3, p4:
        out = tasks._run_ingestion("1Min", NOW)
    assert out["ok"] is False and notifier.events == [Event.CRITICAL_ERROR]


def test_stream_default_fits_the_free_iex_subscription_limit():
    from atlas.core.configuration.settings import AtlasSettings
    from atlas.integrations.alpaca.stream import CHANNELS

    cap = AtlasSettings.model_fields["stream_max_symbols"].default
    assert cap * len(CHANNELS) <= 30
