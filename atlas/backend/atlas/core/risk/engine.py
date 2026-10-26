"""Deterministic risk engine with final authority over every order (CLAUDE.md rule 4).

``evaluate`` is a pure function of (signal, context, policy, calendar). It runs every check
and records each outcome, so a rejection always says exactly why, then sizes the order. No
agent or LLM can call around it, and nothing here can be changed at runtime: limits come
only from ``config/policy.yaml`` (bounded by ``HARD_LIMITS``).

Capital base. Percentage limits and sizing use ``min(broker equity, policy starting
equity)``. If the paper account holds more than the policy's budget, ATLAS still behaves as
an account of the policy's size; if it holds less, the smaller real equity applies.

Fail closed (rule 6). Missing or stale inputs reject entries: no fresh account snapshot, no
fresh two-sided quote, stale universe, and data sources ATLAS does not have yet:
  * earnings dates: with ``block_entries_before_earnings_days > 0`` and no earnings calendar,
    entries are rejected ("earnings calendar unavailable");
  * sectors: unknown sectors are pooled as one sector, so ``max_sector_exposure_pct`` caps
    the combined exposure of all holdings whose sector is unknown.

Exits reduce risk, so only the kill switch, account problems, a closed market or a missing
price can stop them; loss and position limits never do.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Literal

from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.calendar import MarketCalendar
from atlas.core.models.db import StrategyStatus
from atlas.core.strategies.base import CENT, Signal

ACCOUNT_MAX_AGE = timedelta(minutes=3)  # broker sync runs every minute
CLOCK_SKEW = timedelta(seconds=2)  # timestamps further in the future are bad data
BPS = Decimal(10_000)


@dataclass(frozen=True)
class AccountState:
    equity: Decimal
    last_equity: Decimal  # broker's previous-close equity
    cash: Decimal
    long_market_value: Decimal
    trading_blocked: bool
    as_of: datetime
    shorting_enabled: bool | None = None  # None: unknown


@dataclass(frozen=True)
class QuoteState:
    bid: Decimal
    ask: Decimal
    ts: datetime


@dataclass(frozen=True)
class OpenOrderState:
    symbol: str
    side: str
    purpose: str | None
    qty: Decimal
    limit_price: Decimal | None


@dataclass(frozen=True)
class RiskContext:
    now: datetime
    mode: Literal["paper", "shadow"]
    kill_switch_engaged: bool
    strategy_status: StrategyStatus
    account: AccountState | None
    high_water_mark: Decimal | None  # highest broker equity seen
    positions: Mapping[str, Decimal]  # broker positions: symbol -> qty
    open_orders: tuple[OpenOrderState, ...]
    entries_submitted_today: int
    universe_members: frozenset[str] | None
    universe_stale: bool
    quote: QuoteState | None
    strategy_position_qty: Decimal = Decimal(0)  # what this strategy holds in the symbol
    earnings_blackout: bool | None = None  # None: no earnings data available
    sector_known: bool = False  # no sector data source yet


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class RiskResult:
    approved: bool
    qty: Decimal | None
    limit_price: Decimal | None
    capital_base: Decimal | None
    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]

    def checks_json(self) -> list[dict[str, Any]]:
        return [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks]


def _floor(x: Decimal) -> Decimal:
    return x.to_integral_value(rounding=ROUND_FLOOR)


def _cents_up(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_CEILING)


def _cents_down(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_FLOOR)


def capital_base(policy: RiskPolicy, account: AccountState) -> Decimal:
    return min(account.equity, Decimal(str(policy.account.starting_equity_usd)))


def evaluate(
    signal: Signal, ctx: RiskContext, policy: RiskPolicy, calendar: MarketCalendar
) -> RiskResult:
    checks: list[Check] = []

    def check(name: str, passed: bool, detail: str = "") -> bool:
        checks.append(Check(name, passed, detail))
        return passed

    # ----- common ---------------------------------------------------------------------
    check(
        "kill_switch",
        not ctx.kill_switch_engaged,
        "engaged: no new orders" if ctx.kill_switch_engaged else "armed",
    )
    if ctx.mode == "paper":
        check(
            "strategy_status",
            ctx.strategy_status == StrategyStatus.PAPER,
            f"status {ctx.strategy_status.value}; PAPER required to submit",
        )
    else:
        check(
            "strategy_status",
            True,
            f"shadow evaluation ({ctx.strategy_status.value}); never ordered",
        )
    acct = ctx.account
    fresh_acct = acct is not None and -CLOCK_SKEW <= ctx.now - acct.as_of <= ACCOUNT_MAX_AGE
    check(
        "account_snapshot",
        fresh_acct,
        "no broker snapshot"
        if acct is None
        else f"snapshot age {(ctx.now - acct.as_of).total_seconds():.0f}s",
    )
    check(
        "account_not_blocked",
        acct is not None and not acct.trading_blocked,
        "broker reports trading blocked" if acct and acct.trading_blocked else "",
    )
    market_open = calendar.is_open(ctx.now)
    q = ctx.quote
    quote_ok = (
        q is not None
        and q.bid > 0
        and q.ask >= q.bid
        and timedelta(0) - timedelta(seconds=2)
        <= ctx.now - q.ts
        <= timedelta(seconds=policy.data_quality.max_quote_age_seconds)
    )
    quote_detail = (
        "no quote"
        if q is None
        else (f"bid {q.bid} ask {q.ask} age {(ctx.now - q.ts).total_seconds():.1f}s")
    )

    if signal.kind == "exit":
        return _evaluate_exit(
            signal, ctx, policy, checks, check, market_open, quote_ok, quote_detail
        )

    # ----- entries ----------------------------------------------------------------------
    sp = policy.session
    if market_open:
        since_open = calendar.minutes_since_open(ctx.now) or 0.0
        to_close = calendar.minutes_to_close(ctx.now) or 0.0
        check(
            "entry_window",
            since_open >= sp.no_new_positions_minutes_after_open
            and to_close >= sp.no_new_positions_minutes_before_close,
            f"{since_open:.0f} min after open, {to_close:.0f} min before close",
        )
    else:
        check("entry_window", False, "market closed")
    # Long-only enforced at the broker too: a protective stop that outlives its position
    # would otherwise open a short. Entries need shorting disabled on the account.
    check(
        "broker_long_only",
        acct is not None and acct.shorting_enabled is False,
        "unknown"
        if acct is None or acct.shorting_enabled is None
        else ("broker account allows shorting" if acct.shorting_enabled else "shorting disabled"),
    )
    members = ctx.universe_members
    check(
        "universe",
        members is not None and signal.symbol in members and not ctx.universe_stale,
        "no universe snapshot"
        if members is None
        else (
            "snapshot stale"
            if ctx.universe_stale
            else ("member" if signal.symbol in members else "not in universe")
        ),
    )
    days = sp.block_entries_before_earnings_days
    if days == 0:
        check("earnings_blackout", True, "disabled by policy")
    elif ctx.earnings_blackout is None:
        check("earnings_blackout", False, "earnings calendar unavailable (fail closed)")
    else:
        check(
            "earnings_blackout",
            not ctx.earnings_blackout,
            f"earnings within {days} sessions" if ctx.earnings_blackout else "clear",
        )
    check("quote", quote_ok, quote_detail)
    spread_bps = None
    if q is not None and q.bid > 0 and q.ask >= q.bid:
        spread_bps = (q.ask - q.bid) / ((q.ask + q.bid) / 2) * BPS
    check(
        "spread",
        spread_bps is not None and spread_bps <= Decimal(str(policy.instruments.max_spread_bps)),
        "unavailable"
        if spread_bps is None
        else f"{spread_bps:.1f} bps (max {policy.instruments.max_spread_bps})",
    )
    held = ctx.positions.get(signal.symbol, Decimal(0))
    pending = [o for o in ctx.open_orders if o.symbol == signal.symbol]
    check(
        "no_existing_exposure",
        held == 0 and not pending,
        f"position {held}, open orders {len(pending)}",
    )

    cap = capital_base(policy, acct) if acct is not None else None
    lim = policy.limits
    if acct is not None and cap is not None:
        start_cap = min(acct.last_equity, Decimal(str(policy.account.starting_equity_usd)))
        day_pl = acct.equity - acct.last_equity
        max_loss = start_cap * Decimal(str(lim.max_daily_loss_pct)) / 100
        check("daily_loss", day_pl > -max_loss, f"day P/L {day_pl:.2f}, limit -{max_loss:.2f}")
        hwm = max(ctx.high_water_mark or acct.equity, acct.equity)
        dd = hwm - acct.equity
        max_dd = (
            min(hwm, Decimal(str(policy.account.starting_equity_usd)))
            * Decimal(str(lim.max_drawdown_pct))
            / 100
        )
        check("drawdown", dd < max_dd, f"drawdown {dd:.2f} from {hwm:.2f}, limit {max_dd:.2f}")
    else:
        check("daily_loss", False, "no account data")
        check("drawdown", False, "no account data")
    open_entries = [o for o in ctx.open_orders if o.side == "buy"]
    n_positions = sum(1 for v in ctx.positions.values() if v > 0) + len(
        {o.symbol for o in open_entries if ctx.positions.get(o.symbol, Decimal(0)) <= 0}
    )
    check(
        "concurrent_positions",
        n_positions < lim.max_concurrent_positions,
        f"{n_positions} held or pending (max {lim.max_concurrent_positions})",
    )
    check(
        "trades_today",
        ctx.entries_submitted_today < lim.max_new_trades_per_day,
        f"{ctx.entries_submitted_today} entries today (max {lim.max_new_trades_per_day})",
    )

    # ----- sizing -----------------------------------------------------------------------
    qty: Decimal | None = None
    limit_price: Decimal | None = None
    if acct is not None and cap is not None and q is not None and q.ask > 0 and signal.stop_price:
        offset = Decimal(str(policy.execution.limit_offset_bps)) / BPS
        limit_price = _cents_up(q.ask * (1 + offset))
        slip = Decimal(str(policy.execution.stop_slippage_assumption_bps)) / BPS
        risk_per_share = limit_price - signal.stop_price * (1 - slip)
        if not check(
            "stop_below_entry",
            signal.stop_price < limit_price,
            f"stop {signal.stop_price}, limit {limit_price}",
        ):
            risk_per_share = Decimal(0)
        open_buy_notional = sum(
            (o.qty * (o.limit_price or Decimal(0)) for o in open_entries), Decimal(0)
        )
        exposure = acct.long_market_value + open_buy_notional
        pct = lambda v: cap * Decimal(str(v)) / 100  # noqa: E731
        caps: dict[str, Decimal] = {
            "risk_per_trade": _floor(pct(lim.max_risk_per_trade_pct) / risk_per_share)
            if risk_per_share > 0
            else Decimal(0),
            "position_allocation": _floor(pct(lim.max_position_allocation_pct) / limit_price),
            "order_notional": _floor(Decimal(str(lim.max_order_notional_usd)) / limit_price),
            "gross_exposure": _floor((pct(lim.max_gross_exposure_pct) - exposure) / limit_price),
            "cash_buffer": _floor(
                (acct.cash - Decimal(str(lim.min_cash_buffer_usd)) - open_buy_notional)
                / limit_price
            ),
        }
        # Every holding's sector is unknown, so they all share one sector budget.
        caps["sector_exposure"] = _floor(
            (pct(lim.max_sector_exposure_pct) - exposure) / limit_price
        )
        qty = max(min(caps.values()), Decimal(0))
        binding = min(caps, key=lambda k: caps[k])
        check(
            "size",
            qty >= 1,
            f"{qty} shares at {limit_price} (binding: {binding}; "
            + ", ".join(f"{k} {v}" for k, v in caps.items())
            + ")",
        )
    else:
        check("size", False, "missing account, quote or stop")

    approved = all(c.passed for c in checks)
    return RiskResult(approved, qty, limit_price, cap, checks)


def _evaluate_exit(
    signal: Signal,
    ctx: RiskContext,
    policy: RiskPolicy,
    checks: list[Check],
    check: Callable[..., bool],
    market_open: bool,
    quote_ok: bool,
    quote_detail: str,
) -> RiskResult:
    check("market_open", market_open, "regular session" if market_open else "market closed")
    check("quote", quote_ok, quote_detail)
    broker_qty = ctx.positions.get(signal.symbol, Decimal(0))
    qty = min(ctx.strategy_position_qty, broker_qty)
    check(
        "position_held",
        qty > 0,
        f"strategy holds {ctx.strategy_position_qty}, broker holds {broker_qty}",
    )
    pending = [o for o in ctx.open_orders if o.symbol == signal.symbol and o.purpose == "exit"]
    check("no_pending_exit", not pending, f"{len(pending)} exit orders open")
    limit_price = None
    q = ctx.quote
    if q is not None and q.bid > 0:
        offset = Decimal(str(policy.execution.limit_offset_bps)) / BPS
        limit_price = _cents_down(q.bid * (1 - offset))
    cap = capital_base(policy, ctx.account) if ctx.account is not None else None
    approved = all(c.passed for c in checks)
    return RiskResult(approved, qty if qty > 0 else None, limit_price, cap, checks)
