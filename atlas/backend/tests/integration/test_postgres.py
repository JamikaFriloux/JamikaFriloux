"""PostgreSQL integration tests. Run with ATLAS_TEST_DATABASE_URL pointing at a disposable DB."""

import os
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from atlas.core.models.db import AccountSnapshot
from atlas.core.risk import kill_switch
from atlas.core.security import audit

URL = os.environ.get("ATLAS_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="ATLAS_TEST_DATABASE_URL not set"),
]


@pytest.fixture(scope="module")
def engine():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "..", "migrations")
    )
    cfg.attributes["url"] = URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(URL)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    s = sessionmaker(bind=engine)()
    yield s
    s.rollback()
    s.close()


def test_kill_switch_seeded_engaged(session):
    assert kill_switch.is_trading_allowed(session) is False


def test_audit_log_is_append_only(engine):
    with sessionmaker(bind=engine)() as s:
        audit.record(s, actor="t", action="test.append")
        s.commit()
    with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("UPDATE audit_log SET actor='x'"))
        conn.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("DELETE FROM audit_log"))
        conn.rollback()


def test_non_paper_snapshot_rejected_by_database(session):
    session.add(
        AccountSnapshot(
            source="x",
            is_paper=False,
            account_status="ACTIVE",
            equity=Decimal(1),
            last_equity=Decimal(1),
            cash=Decimal(1),
            buying_power=Decimal(1),
            long_market_value=Decimal(0),
            trading_blocked=False,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_kill_switch_singleton_enforced(engine):
    with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text("INSERT INTO kill_switch (id, engaged, version) VALUES (2, false, 0)")
            )
        conn.rollback()


def test_bar_upsert_on_conflict_and_quality_report(engine):
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from atlas.core.data.calendar import NY, MarketCalendar
    from atlas.core.data.ingestion import ingest_bars
    from atlas.core.models.db import Bar, DataQualityReport
    from tests.fakes import FakeBarSource, make_bar

    now = datetime(2026, 10, 22, 17, 0, tzinfo=NY)
    days = [make_bar("PGTST", datetime(2026, 10, d, tzinfo=NY)) for d in (21, 22)]
    src = FakeBarSource({"PGTST": days})
    with sessionmaker(bind=engine)() as s:
        for close in ("100", "101.25"):
            src.bars["PGTST"][-1] = make_bar(
                "PGTST", datetime(2026, 10, 22, tzinfo=NY), close=close
            )
            result = ingest_bars(
                s,
                src,
                ["PGTST"],
                "1Day",
                now=now,
                lookback=timedelta(days=30),
                incremental=False,
                calendar=MarketCalendar(),
            )
            assert result.ok
        rows = s.scalars(select(Bar).where(Bar.symbol == "PGTST").order_by(Bar.ts)).all()
        assert len(rows) == 2 and rows[-1].close == Decimal("101.25")
        reports = s.scalars(select(DataQualityReport).where(DataQualityReport.symbol == "PGTST"))
        assert [r.ok for r in reports] == [True, True]
        s.rollback()


def test_universe_snapshots_are_immutable_but_deletable(engine):
    from datetime import date

    from atlas.core.models.db import UniverseMember, UniverseSnapshot

    with sessionmaker(bind=engine)() as s:
        snap = UniverseSnapshot(as_of=date(2026, 10, 23), source="t", criteria={}, assets_seen=1,
                                member_count=1, exclusions={})  # fmt: skip
        s.add(snap)
        s.flush()
        s.add(UniverseMember(snapshot_id=snap.id, symbol="AAA", name="A", exchange="NYSE",
                             last_close=Decimal(1), adv_usd=Decimal(1), sessions=20,
                             fractionable=True, shortable=False, easy_to_borrow=False))  # fmt: skip
        s.commit()
        snap_id = snap.id
    with engine.connect() as conn:
        for sql in (
            "UPDATE universe_snapshots SET member_count = 99",
            "UPDATE universe_members SET adv_usd = 0",
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                conn.execute(text(sql))
            conn.rollback()
        conn.execute(text("DELETE FROM universe_snapshots WHERE id = :i"), {"i": snap_id})
        left = conn.execute(
            text("SELECT count(*) FROM universe_members WHERE snapshot_id = :i"), {"i": snap_id}
        ).scalar()
        assert left == 0  # members cascade with their snapshot
        conn.commit()


def test_validation_reports_are_immutable(engine):
    from datetime import date

    from atlas.core.models.db import ValidationReport

    with sessionmaker(bind=engine)() as s:
        r = ValidationReport(
            strategy_id="x",
            version="1",
            params={},
            params_hash="h" * 16,
            target_status="PAPER",
            policy_sha256="p" * 64,
            passed=False,
            data_start=date(2020, 1, 1),
            data_end=date(2026, 1, 1),
            symbols=[],
            gates=[],
            metrics={},
            equity_curve=[],
            caveats=[],
            runtime_seconds=Decimal(1),
        )
        s.add(r)
        s.commit()
    with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="immutable"):
            conn.execute(text("UPDATE validation_reports SET passed = true"))
        conn.rollback()
