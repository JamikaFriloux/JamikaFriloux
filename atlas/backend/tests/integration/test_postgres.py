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
