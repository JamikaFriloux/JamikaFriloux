import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pydantic import SecretStr

from atlas.core.configuration.settings import RefDataSettings
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.execution.broker import AccountInfo
from atlas.core.models.db import (
    AccountSnapshot,
    DataQualityReport,
    EarningsCoverage,
    InstrumentReference,
    KillSwitch,
    ServiceHeartbeat,
    StrategyRecord,
    StrategyStatus,
    UniverseSnapshot,
)
from atlas.scripts import check_readiness
from atlas.scripts.check_readiness import BrokerView, assess

NOW = datetime(2026, 10, 27, 11, 0, tzinfo=NY).astimezone(UTC)  # Tuesday, in session
CAL = MarketCalendar()
BENCH = ["SPY", "QQQ", "IWM", "DIA"]


def _account(**kw):
    base = dict(
        account_number="PA1",
        status="ACTIVE",
        equity=Decimal("100000"),
        last_equity=Decimal("100000"),
        cash=Decimal("100000"),
        buying_power=Decimal("100000"),
        long_market_value=Decimal("0"),
        trading_blocked=False,
        is_paper=True,
        shorting_enabled=False,
        margin_multiplier=Decimal("1"),
    )
    return AccountInfo(**{**base, **kw})


def _ref():
    return RefDataSettings(_env_file=None)  # type: ignore[call-arg]


def _levels(checks):
    return {c.name: c.level for c in checks}


def _make_ready(db, settings, monkeypatch):
    db.get(KillSwitch, 1).engaged = False
    db.add(
        StrategyRecord(id="trend_breakout", version="1.0.0", status=StrategyStatus.PAPER, params={})
    )
    monkeypatch.setattr(check_readiness, "passing_validation_report", lambda *_a: "7")
    db.add(
        AccountSnapshot(
            ts=NOW - timedelta(seconds=40),
            source="alpaca_paper",
            is_paper=True,
            account_status="ACTIVE",
            equity=Decimal("100000"),
            last_equity=Decimal("100000"),
            cash=Decimal("100000"),
            buying_power=Decimal("100000"),
            long_market_value=Decimal("0"),
            trading_blocked=False,
            shorting_enabled=False,
            margin_multiplier=Decimal("1"),
        )
    )
    for svc in ("worker", "executor", "broker", "stream"):
        db.add(ServiceHeartbeat(service=svc, last_seen=NOW - timedelta(seconds=20), status="ok"))
    db.add(
        UniverseSnapshot(
            as_of=date(2026, 10, 26), source="t", criteria={}, assets_seen=1, member_count=1
        )
    )
    run = uuid.uuid4()
    for sym in BENCH:
        db.add(
            DataQualityReport(
                run_id=run,
                ts=NOW - timedelta(hours=14),
                symbol=sym,
                timeframe="1Day",
                source="t",
                adjustment="all",
                window_start=NOW - timedelta(days=400),
                window_end=NOW,
                ok=True,
                stale=False,
            )
        )
        db.add(InstrumentReference(symbol=sym, asset_type="etf", sector="broad", source="config"))
    db.add(
        EarningsCoverage(
            source="finnhub",
            fetched_at=NOW - timedelta(hours=4),
            window_start=date(2026, 10, 27),
            window_end=date(2026, 11, 26),
        )
    )
    db.flush()
    settings.telegram_bot_token = SecretStr("t")
    settings.telegram_chat_id = "1"


def test_fresh_deployment_is_not_ready(db, settings):
    checks = assess(
        db,
        now=NOW,
        broker=BrokerView(None, error="ConnectError"),
        settings=settings,
        ref=_ref(),
        calendar=CAL,
    )
    lv = _levels(checks)
    for name in (
        "broker",
        "kill switch",
        "strategies",
        "account snapshot",
        "service worker",
        "service executor",
        "service broker",
        "universe",
        "daily bars",
        "classification",
        "earnings calendar",
        "alerts",
    ):
        assert lv[name] == "fail", name
    assert lv["service stream"] == "warn"  # REST quotes are the fallback
    assert lv["mode"] == "ok"
    assert "ConnectError" in next(c.detail for c in checks if c.name == "broker")


def test_ready_when_everything_is_in_place(db, settings, monkeypatch):
    _make_ready(db, settings, monkeypatch)
    checks = assess(
        db, now=NOW, broker=BrokerView(_account()), settings=settings, ref=_ref(), calendar=CAL
    )
    assert [c for c in checks if c.level != "ok"] == []
    assert _levels(checks)["validation trend_breakout"] == "ok"


def test_each_blocker_fails_alone(db, settings, monkeypatch):
    _make_ready(db, settings, monkeypatch)

    def run(**broker_kw):
        return _levels(
            assess(
                db,
                now=NOW,
                broker=BrokerView(_account(**broker_kw)),
                settings=settings,
                ref=_ref(),
                calendar=CAL,
            )
        )

    assert run(shorting_enabled=True)["broker"] == "fail"
    assert run(margin_multiplier=Decimal("4"))["broker"] == "fail"
    assert run(trading_blocked=True)["broker"] == "fail"

    monkeypatch.setattr(check_readiness, "passing_validation_report", lambda *_a: None)
    assert run()["validation trend_breakout"] == "fail"

    db.get(StrategyRecord, "trend_breakout").status = StrategyStatus.RESEARCH
    lv = run()
    assert lv["strategies"] == "fail" and "validation trend_breakout" not in lv

    db.get(ServiceHeartbeat, "executor").last_seen = NOW - timedelta(minutes=10)
    db.get(ServiceHeartbeat, "stream").status = "error"
    lv = run()
    assert lv["service executor"] == "fail" and lv["service stream"] == "warn"

    db.get(KillSwitch, 1).engaged = True
    assert run()["kill switch"] == "fail"


def test_main_prints_result_and_exit_code(session_factory, settings, monkeypatch, capsys):
    from contextlib import contextmanager

    @contextmanager
    def scope():
        with session_factory() as s:
            yield s

    monkeypatch.setattr(check_readiness, "session_scope", scope)
    monkeypatch.setattr(check_readiness, "read_broker", lambda: BrokerView(None, error="x"))
    monkeypatch.setattr(check_readiness, "get_settings", lambda: settings)
    assert check_readiness.main() == 2
    out = capsys.readouterr().out
    assert "FAIL  kill switch" in out and "RESULT NOT READY" in out


def test_universe_is_only_due_once_its_session_opens(db, settings, monkeypatch):
    _make_ready(db, settings, monkeypatch)  # snapshot as_of 2026-10-26 (Monday)

    def universe(now):
        checks = assess(
            db, now=now, broker=BrokerView(_account()), settings=settings, ref=_ref(), calendar=CAL
        )
        return next(c for c in checks if c.name == "universe")

    # Tuesday in session: trades on Monday's snapshot.
    assert universe(NOW).level == "ok"
    # Tuesday evening: Tuesday's snapshot isn't due until 06:45 Wednesday.
    evening = universe(datetime(2026, 10, 27, 18, 0, tzinfo=NY).astimezone(UTC))
    assert evening.level == "warn" and "06:45" in evening.detail
    # Wednesday premarket, still before the open: not missing yet.
    assert universe(datetime(2026, 10, 28, 7, 0, tzinfo=NY).astimezone(UTC)).level == "warn"
    # Wednesday after the open without Tuesday's snapshot: entries would be refused.
    missing = universe(datetime(2026, 10, 28, 10, 0, tzinfo=NY).astimezone(UTC))
    assert missing.level == "fail" and "2026-10-27" in missing.detail
