from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from atlas.core.models.db import AuditLog, KillSwitch
from atlas.core.risk import kill_switch
from tests.fakes import FakeBroker, RecordingNotifier


def _disengage(db):
    db.get(KillSwitch, 1).engaged = False
    db.flush()


def test_fresh_deployment_starts_engaged(db):
    assert kill_switch.is_trading_allowed(db) is False


def test_engage_blocks_trading_and_is_idempotent(db):
    _disengage(db)
    assert kill_switch.is_trading_allowed(db)
    assert kill_switch.engage(db, actor="op", reason="test") is True
    assert kill_switch.engage(db, actor="op", reason="again") is False
    assert not kill_switch.is_trading_allowed(db)
    actions = db.scalars(select(AuditLog.action)).all()
    assert actions.count("kill_switch.engage") == 1


def test_engage_requires_reason(db):
    with pytest.raises(kill_switch.KillSwitchError):
        kill_switch.engage(db, actor="op", reason="  ")


def test_resume_requires_explicit_authorization(db):
    with pytest.raises(kill_switch.KillSwitchError):
        kill_switch.resume(db, actor="admin", reason="ok", authorized=False)
    assert not kill_switch.is_trading_allowed(db)
    kill_switch.resume(db, actor="admin", reason="verified config", authorized=True)
    assert kill_switch.is_trading_allowed(db)


def test_missing_row_fails_closed(db):
    db.delete(db.get(KillSwitch, 1))
    db.flush()
    assert kill_switch.is_trading_allowed(db) is False
    assert kill_switch.get_state(db).engaged is True


def test_database_error_fails_closed():
    session = MagicMock()
    session.execute.side_effect = OperationalError("SELECT", {}, Exception("db down"))
    assert kill_switch.is_trading_allowed(session) is False


def test_engagement_actions_cancel_reconcile_alert(db):
    broker = FakeBroker()
    from decimal import Decimal

    from atlas.core.execution.broker import OrderRequest

    broker.submit_limit_order(OrderRequest("c1", "SPY", "buy", Decimal(1), Decimal(1)))
    notifier = RecordingNotifier()
    reconciled = []
    report = kill_switch.execute_engagement_actions(
        db, broker, lambda: reconciled.append(1), notifier
    )
    assert len(report.cancelled_order_ids) == 1
    assert report.reconciled and reconciled
    text, critical = notifier.messages[0]
    assert critical and "KILL SWITCH" in text and "NOT liquidated" in text and "[PAPER]" in text


def test_engagement_actions_continue_after_cancel_failure(db):
    broker = FakeBroker()
    broker.cancel_error = TimeoutError()
    notifier = RecordingNotifier()
    report = kill_switch.execute_engagement_actions(db, broker, lambda: None, notifier)
    assert report.errors and report.reconciled
    assert notifier.messages, "operator must still be alerted"
