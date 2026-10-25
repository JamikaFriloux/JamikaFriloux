"""Duplicate orders, broker timeouts, lost responses and rejections."""

from decimal import Decimal

import pytest

from atlas.core.execution.broker import (
    BrokerRejected,
    BrokerUncertain,
    OrderRequest,
    SubmissionUncertain,
    submit_idempotent,
)
from tests.fakes import FakeBroker

REQ = OrderRequest("atlas-abc", "SPY", "buy", Decimal(1), Decimal("500.00"))


def _raise(exc):
    def f(*_):
        raise exc

    return f


def test_normal_submission():
    b = FakeBroker()
    o = submit_idempotent(b, REQ, base_delay=0)
    assert o.client_order_id == REQ.client_order_id and b.submit_calls == 1


def test_resubmitting_same_order_does_not_duplicate():
    b = FakeBroker()
    first = submit_idempotent(b, REQ, base_delay=0)
    second = submit_idempotent(b, REQ, base_delay=0)
    assert first == second
    assert b.submit_calls == 1 and len(b.orders) == 1


def test_timeout_after_broker_accepted_is_not_resubmitted():
    b = FakeBroker()
    b.accept_then_fail = True
    b.on_submit.append(_raise(BrokerUncertain("timeout")))
    o = submit_idempotent(b, REQ, base_delay=0)
    assert o.client_order_id == REQ.client_order_id
    assert b.submit_calls == 1 and len(b.orders) == 1


def test_timeout_before_acceptance_retries_once_with_same_id():
    b = FakeBroker()
    b.on_submit.append(_raise(BrokerUncertain("timeout")))
    o = submit_idempotent(b, REQ, base_delay=0)
    assert b.submit_calls == 2 and len(b.orders) == 1
    assert o.client_order_id == REQ.client_order_id


def test_persistent_uncertainty_raises_without_blind_resubmission():
    b = FakeBroker()
    b.on_submit.extend([_raise(BrokerUncertain("t1")), _raise(BrokerUncertain("t2"))])
    with pytest.raises(SubmissionUncertain):
        submit_idempotent(b, REQ, base_delay=0)
    assert b.submit_calls == 2  # never more than one retry


def test_lookup_outage_after_timeout_raises_uncertain():
    b = FakeBroker()
    b.on_submit.append(_raise(BrokerUncertain("timeout")))
    # first pre-check lookup ok, then every lookup after the timeout fails
    b.on_lookup.extend([lambda _: None] + [_raise(BrokerUncertain("down"))] * 4)
    with pytest.raises(SubmissionUncertain):
        submit_idempotent(b, REQ, base_delay=0)
    assert b.submit_calls == 1


def test_rejection_propagates_without_retry():
    b = FakeBroker()
    b.on_submit.append(_raise(BrokerRejected("insufficient buying power")))
    with pytest.raises(BrokerRejected):
        submit_idempotent(b, REQ, base_delay=0)
    assert b.submit_calls == 1


def test_duplicate_id_error_returns_existing_order():
    b = FakeBroker()
    b.submit_limit_order(REQ)
    # Pre-check lookup fails transiently so we reach submit and hit the duplicate.
    b.on_lookup.append(_raise(BrokerUncertain("blip")))
    o = submit_idempotent(b, REQ, base_delay=0)
    assert o.client_order_id == REQ.client_order_id and len(b.orders) == 1


def test_simultaneous_signals_distinct_ids_both_submitted():
    b = FakeBroker()
    submit_idempotent(b, REQ, base_delay=0)
    submit_idempotent(
        b, OrderRequest("atlas-def", "QQQ", "buy", Decimal(1), Decimal(400)), base_delay=0
    )
    assert len(b.orders) == 2
