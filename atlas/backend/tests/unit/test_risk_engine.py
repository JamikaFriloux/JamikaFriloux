from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import StrategyStatus
from atlas.core.risk.engine import (
    AccountState,
    OpenOrderState,
    QuoteState,
    RiskContext,
    evaluate,
)
from atlas.core.strategies.base import Signal

CAL = MarketCalendar()
NOW = datetime(2026, 10, 22, 11, 0, tzinfo=NY)  # Thursday, mid-session
D = Decimal
ENTRY = Signal("trend_breakout", "1.0.0", "AAA", "entry", date(2026, 10, 21), D("100"), D("98"))
EXIT = Signal("trend_breakout", "1.0.0", "AAA", "exit", date(2026, 10, 21), D("100"))


def ctx(**kw):
    base = RiskContext(
        now=NOW,
        mode="paper",
        kill_switch_engaged=False,
        strategy_status=StrategyStatus.PAPER,
        account=AccountState(
            equity=D(100_000),
            last_equity=D(100_000),
            cash=D(100_000),
            long_market_value=D(0),
            trading_blocked=False,
            as_of=NOW - timedelta(seconds=30),
            shorting_enabled=False,
        ),
        high_water_mark=D(100_000),
        positions={},
        open_orders=(),
        entries_submitted_today=0,
        universe_members=frozenset({"AAA", "BBB"}),
        universe_stale=False,
        quote=QuoteState(bid=D("99.98"), ask=D("100.00"), ts=NOW - timedelta(seconds=1)),
        earnings_blackout=False,
    )
    return replace(base, **kw)


@pytest.fixture(autouse=True)
def _policy(policy):
    global POLICY
    POLICY = policy.policy


def ev(signal=ENTRY, **kw):
    return evaluate(signal, ctx(**kw), POLICY, CAL)


def test_baseline_entry_is_approved_and_sized():
    r = ev()
    assert r.approved, r.failed
    # capital base = min(100k equity, 10k policy) = 10k; limit = 100.00 * 1.0005 = 100.05
    assert r.capital_base == D(10_000) and r.limit_price == D("100.05")
    # risk: 25 / (100.05 - 98 * 0.998) = 11; allocation 10% -> 1000 / 100.05 = 9 (binding)
    assert r.qty == D(9)
    size = next(c for c in r.checks if c.name == "size")
    assert "binding: position_allocation" in size.detail and "risk_per_trade 11" in size.detail


@pytest.mark.parametrize(
    ("kw", "failed"),
    [
        ({"kill_switch_engaged": True}, "kill_switch"),
        ({"strategy_status": StrategyStatus.RESEARCH}, "strategy_status"),
        ({"account": None}, "account_snapshot"),
        ({"universe_members": frozenset({"BBB"})}, "universe"),
        ({"universe_members": None}, "universe"),
        ({"universe_stale": True}, "universe"),
        ({"earnings_blackout": None}, "earnings_blackout"),  # no earnings data: fail closed
        ({"earnings_blackout": True}, "earnings_blackout"),
        ({"quote": None}, "quote"),
        ({"positions": {"AAA": D(5)}}, "no_existing_exposure"),
        ({"entries_submitted_today": 5}, "trades_today"),
    ],
)
def test_single_rule_rejections(kw, failed):
    r = ev(**kw)
    assert not r.approved and failed in r.failed


def test_stale_account_snapshot_and_blocked_account():
    old = ctx().account
    assert "account_snapshot" in ev(account=replace(old, as_of=NOW - timedelta(minutes=4))).failed
    assert ev(account=replace(old, trading_blocked=True)).failed == ["account_not_blocked"]
    assert "account_snapshot" in ev(account=replace(old, as_of=NOW + timedelta(minutes=1))).failed


def test_quote_freshness_spread_and_crossing():
    fresh = ctx().quote
    assert "quote" in ev(quote=replace(fresh, ts=NOW - timedelta(seconds=16))).failed
    assert "quote" in ev(quote=replace(fresh, ts=NOW + timedelta(seconds=5))).failed
    wide = ev(quote=replace(fresh, bid=D("99.60"), ask=D("100.00")))  # ~40 bps > 25
    assert wide.failed == ["spread"]
    crossed = ev(quote=replace(fresh, bid=D("100.10"), ask=D("100.00")))
    assert {"quote", "spread"} <= set(crossed.failed)


def test_entry_window_edges():
    early = datetime(2026, 10, 22, 9, 33, tzinfo=NY)
    late = datetime(2026, 10, 22, 15, 50, tzinfo=NY)
    for t in (early, late):
        r = ev(
            now=t,
            account=replace(ctx().account, as_of=t),
            quote=replace(ctx().quote, ts=t - timedelta(seconds=1)),
        )
        assert r.failed == ["entry_window"], (t, r.failed)
    closed = datetime(2026, 10, 24, 11, 0, tzinfo=NY)
    r = ev(
        now=closed,
        account=replace(ctx().account, as_of=closed),
        quote=replace(ctx().quote, ts=closed),
    )
    assert r.failed == ["entry_window"]


def test_daily_loss_and_drawdown_limits():
    acct = ctx().account
    # daily limit = 1% of min(last_equity, 10k) = 100
    assert ev(account=replace(acct, equity=D(99_899), last_equity=D(100_000))).failed == [
        "daily_loss"
    ]
    assert ev(account=replace(acct, equity=D(99_901), last_equity=D(100_000))).approved
    # drawdown limit = 5% of min(hwm, 10k) = 500 (in dollars, regardless of account size)
    r = ev(
        high_water_mark=D(100_500), account=replace(acct, equity=D(100_000), last_equity=D(100_000))
    )
    assert r.failed == ["drawdown"]


def test_concurrent_positions_counts_pending_entries():
    held = {s: D(1) for s in ("B1", "B2", "B3", "B4")}
    pending = (OpenOrderState("B5", "buy", "entry", D(1), D(10)),)
    assert ev(positions=held, open_orders=pending).failed == ["concurrent_positions"]
    assert ev(positions=held).approved


def test_exposure_caps_bind_sizing():
    acct = ctx().account
    # Sector budget (unknown sectors pooled) = 25% of 10k = 2500; 2450 already held -> 0 shares
    r = ev(account=replace(acct, long_market_value=D(2450)), positions={"BBB": D(10)})
    assert r.failed == ["size"] and "binding: sector_exposure" in r.checks[-1].detail
    # Cash buffer: 100 cash buffer, 600 cash -> floor(500 / 100.05) = 4 shares
    r = ev(account=replace(acct, cash=D(600)))
    assert r.approved and r.qty == D(4)


def test_risk_per_trade_binds_with_wide_stop():
    wide = replace(ENTRY, stop_price=D("90"))  # ~10.2 risk/share -> floor(25 / 10.23) = 2
    r = ev(wide)
    assert r.approved and r.qty == D(2) and "binding: risk_per_trade" in r.checks[-1].detail


def test_stop_at_or_above_entry_rejected():
    r = ev(replace(ENTRY, stop_price=D("101")))
    assert "stop_below_entry" in r.failed and not r.approved


def test_shadow_mode_records_would_be_decision():
    r = ev(mode="shadow", strategy_status=StrategyStatus.RESEARCH)
    assert r.approved and "shadow" in r.checks[1].detail


def test_policy_without_earnings_rule_passes_check(policy):
    pol = policy.policy.model_copy(
        update={
            "session": policy.policy.session.model_copy(
                update={"block_entries_before_earnings_days": 0}
            )
        }
    )
    r = evaluate(ENTRY, ctx(earnings_blackout=None), pol, CAL)
    assert r.approved and any(c.detail == "disabled by policy" for c in r.checks)


# ---------- exits ----------
def test_exit_sizes_to_strategy_holding_and_prices_off_bid():
    r = ev(EXIT, positions={"AAA": D(9)}, strategy_position_qty=D(9))
    assert r.approved and r.qty == D(9) and r.limit_price == D("99.93")  # 99.98 * 0.9995 down


def test_exit_not_blocked_by_loss_limits_or_universe():
    acct = replace(ctx().account, equity=D(90_000), last_equity=D(100_000))
    r = ev(
        EXIT,
        account=acct,
        positions={"AAA": D(9)},
        strategy_position_qty=D(9),
        universe_members=frozenset(),
        earnings_blackout=None,
        quote=replace(ctx().quote, bid=D("90"), ask=D("100")),
    )  # very wide spread
    assert r.approved, r.failed


def test_exit_blocked_by_kill_switch_and_needs_a_position():
    assert (
        "kill_switch"
        in ev(
            EXIT, kill_switch_engaged=True, positions={"AAA": D(9)}, strategy_position_qty=D(9)
        ).failed
    )
    assert ev(EXIT, positions={}, strategy_position_qty=D(9)).failed == ["position_held"]
    # Never sell more than the broker holds.
    r = ev(EXIT, positions={"AAA": D(4)}, strategy_position_qty=D(9))
    assert r.approved and r.qty == D(4)
    dup = (OpenOrderState("AAA", "sell", "exit", D(9), D(99)),)
    assert ev(
        EXIT, positions={"AAA": D(9)}, strategy_position_qty=D(9), open_orders=dup
    ).failed == ["no_pending_exit"]


def test_entries_require_shorting_disabled_at_broker():
    acct = ctx().account
    assert ev(account=replace(acct, shorting_enabled=True)).failed == ["broker_long_only"]
    assert ev(account=replace(acct, shorting_enabled=None)).failed == ["broker_long_only"]
    # Exits are risk-reducing and don't depend on it.
    r = ev(
        EXIT,
        account=replace(acct, shorting_enabled=True),
        positions={"AAA": D(9)},
        strategy_position_qty=D(9),
    )
    assert r.approved
