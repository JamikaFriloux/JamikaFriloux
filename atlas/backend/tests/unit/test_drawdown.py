from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import AccountSnapshot, EquityClose
from atlas.core.risk.drawdown import (
    DrawdownState,
    at_session,
    limit_dollars,
    production_state,
    record_equity_close,
    replay,
    step,
)

CAL = MarketCalendar()
S = CAL.sessions_between(date(2026, 1, 2), date(2026, 6, 30))
D = Decimal


@pytest.fixture
def pol(policy):
    return policy.policy  # 5% drawdown of a $10k budget = $500; 20-session cooldown


def test_limit_is_capped_at_the_budget(pol):
    assert limit_dollars(D(100_000), pol) == D(500)  # 5% of the $10k budget, not of $100k
    assert limit_dollars(D(8_000), pol) == D(400)  # below budget: 5% of actual equity


def test_halt_cooldown_and_reset(pol):
    closes = [(S[0], D(10_000)), (S[1], D(10_300)), (S[2], D(9_800))]  # 500 below the 10,300 peak
    state = replay(closes, pol, CAL)
    assert state == DrawdownState(peak=D(10_300), halted_on=S[2])
    # Sessions S[3]..S[22] are the 20 cooldown sessions.
    assert at_session(state, S[3], D(9_800), pol, CAL) == (D(10_300), 20)
    assert at_session(state, S[22], D(9_800), pol, CAL) == (D(10_300), 1)
    for i in range(3, 22):  # closes during the cooldown don't move the peak, even rallies
        state = step(state, S[i], D(10_500) if i == 10 else D(9_700), pol, CAL)
        assert state.halted_on == S[2] and state.peak == D(10_300)
    state = step(state, S[22], D(9_650), pol, CAL)  # 20th session's close: reset here
    assert state == DrawdownState(peak=D(9_650), halted_on=None)
    assert at_session(state, S[23], D(9_700), pol, CAL) == (D(9_700), 0)
    # A new breach is measured from the reset baseline (limit 5% of 9,650 = 482.50).
    assert step(state, S[23], D(9_200), pol, CAL).halted_on is None  # 450 down: fine
    state = step(state, S[23], D(9_150), pol, CAL)  # 500 down: halts again
    assert state.halted_on == S[23]


def test_small_dips_do_not_halt(pol):
    state = replay([(S[0], D(10_000)), (S[1], D(9_501))], pol, CAL)
    assert state.halted_on is None and at_session(state, S[2], D(9_501), pol, CAL)[1] == 0


def test_missing_reset_close_resets_to_live_equity(pol):
    state = DrawdownState(peak=D(10_300), halted_on=S[2])  # no closes recorded afterwards
    assert at_session(state, S[23], D(9_400), pol, CAL) == (D(9_400), 0)
    assert at_session(state, S[22], D(9_400), pol, CAL)[1] == 1


def _snap(db, ts, equity):
    db.add(
        AccountSnapshot(
            ts=ts.astimezone(UTC),
            source="t",
            is_paper=True,
            account_status="ACTIVE",
            equity=D(equity),
            last_equity=D(equity),
            cash=D(equity),
            buying_power=D(equity),
            long_market_value=D(0),
            trading_blocked=False,
        )
    )
    db.flush()


def test_record_equity_close_keeps_last_in_session_then_first_after_close(db, pol):
    day = date(2026, 3, 10)
    _snap(db, datetime(2026, 3, 10, 9, 0, tzinfo=NY), 1)  # before the open: ignored
    assert record_equity_close(db, CAL) is None
    for t, eq in (
        (datetime(2026, 3, 10, 11, tzinfo=NY), 10_100),
        (datetime(2026, 3, 10, 15, 59, tzinfo=NY), 10_200),
        (datetime(2026, 3, 10, 16, 1, tzinfo=NY), 10_250),
    ):
        _snap(db, t, eq)
        record_equity_close(db, CAL)
    _snap(
        db, datetime(2026, 3, 10, 20, tzinfo=NY), 99_999
    )  # later overnight snapshot: not the close
    record_equity_close(db, CAL)
    assert db.get(EquityClose, day).equity == D(10_250)
    _snap(db, datetime(2026, 3, 14, 12, tzinfo=NY), 5)  # Saturday: nothing to record
    assert record_equity_close(db, CAL) is None


def test_production_state_replays_closes_before_today(db, pol):
    for d, eq in ((S[0], 10_000), (S[1], 9_400), (S[2], 9_300)):
        db.add(EquityClose(day=d, equity=D(eq), recorded_at=datetime.now(UTC)))
    db.flush()
    assert production_state(db, S[1], pol, CAL) == DrawdownState(peak=D(10_000), halted_on=None)
    assert production_state(db, S[3], pol, CAL).halted_on == S[1]
    assert len(db.scalars(select(EquityClose)).all()) == 3


def test_policy_floor_for_cooldown(policy):
    from pydantic import ValidationError

    from atlas.core.configuration.policy import LimitsPolicy

    raw = policy.policy.limits.model_dump()
    with pytest.raises(ValidationError):
        LimitsPolicy.model_validate({**raw, "drawdown_cooldown_sessions": 0})
    assert policy.policy.limits.drawdown_cooldown_sessions == 20


def test_engine_rejects_entries_during_cooldown_but_not_exits(policy):
    from atlas.core.risk.engine import evaluate
    from tests.unit.test_risk_engine import ENTRY, EXIT, ctx

    r = evaluate(ENTRY, ctx(drawdown_cooldown_remaining=7), policy.policy, CAL)
    assert r.failed == ["drawdown"]
    assert "cooldown, 7 sessions left" in next(c.detail for c in r.checks if c.name == "drawdown")
    ex = evaluate(
        EXIT,
        ctx(drawdown_cooldown_remaining=7, positions={"AAA": D(9)}, strategy_position_qty=D(9)),
        policy.policy,
        CAL,
    )
    assert ex.approved
