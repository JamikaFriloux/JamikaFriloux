"""Event-driven daily simulator that reuses the production strategy and risk-engine code.

Per session ``d`` (mirroring the live schedule):
  1. Open (+5 min, the policy entry window): act on signals from the previous close.
     Exits first, then entries. Each goes through ``risk.engine.evaluate`` with a context
     built from simulated state and a synthetic quote around ``d``'s open. Approved orders
     are limit orders priced exactly as in production; they fill only if the modeled price
     (open +/- half spread +/- slippage) is within the limit, and at most
     ``max_participation`` of the session's volume (the rest of a DAY order is cancelled).
  2. Intraday: protective stops. If the open gaps through the stop, the fill is the open
     (less spread and stop slippage); else if the low reaches it, the fill is the stop less
     spread and stop slippage.
  3. Close: mark to market, then run ``Strategy.generate`` on bars up to ``d``.

The universe for ``d`` is point-in-time: the production ``liquidity_screen`` applied to raw
(unadjusted) bars up to the previous session. Prices for trading and P&L use adjusted bars.

Known simplifications (recorded as caveats in every report): the symbol list itself comes
from today (survivorship bias); earnings blackouts and sectors aren't simulated because
there is no historical data for them; one strategy per simulated account.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from atlas.core.backtesting.costs import CostModel
from atlas.core.backtesting.metrics import Trade, summarize
from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.bars import BarRecord, validate_bars
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.universe import AssetInfo, UniverseCriteria, liquidity_screen
from atlas.core.models.db import StrategyStatus
from atlas.core.risk.drawdown import DrawdownState, at_session
from atlas.core.risk.drawdown import step as dd_step
from atlas.core.risk.engine import AccountState, QuoteState, RiskContext, evaluate
from atlas.core.strategies.base import OpenPosition, Signal, Strategy

CAVEATS = [
    "survivorship_bias: symbols are today's benchmarks/watchlists, not the historical universe",
    "earnings_blackout_not_simulated: no historical earnings calendar (production fails closed)",
    "sectors_unknown: all holdings share one sector budget, as in production",
    "daily_bars_only: fills modeled from session open/low/volume, not intraday quotes",
]


@dataclass
class SimPosition:
    qty: Decimal
    entry_price: Decimal
    stop_price: Decimal
    entry_date: date


@dataclass
class BacktestResult:
    strategy_id: str
    version: str
    params: dict[str, Any]
    dates: list[date] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    exposed_days: int = 0
    signals: int = 0
    rejections: Counter[str] = field(default_factory=Counter)
    first_halt: dict[str, str] = field(default_factory=dict)  # check -> first date it blocked
    unfilled: int = 0
    partial_fills: int = 0
    skipped_bad_windows: int = 0
    drawdown_halts: list[str] = field(default_factory=list)  # sessions whose close halted entries
    drawdown_resets: list[str] = field(default_factory=list)  # sessions whose close reset the HWM

    def summary(self) -> dict[str, Any]:
        return summarize(self.dates, self.equity, self.trades, self.exposed_days)

    def window(self, start: date, end: date) -> dict[str, Any] | None:
        """Metrics for [start, end), from the full run's path (no reset at the boundary)."""
        idx = [i for i, d in enumerate(self.dates) if start <= d < end]
        if len(idx) < 2:
            return None
        lo, hi = idx[0], idx[-1] + 1
        trades = [t for t in self.trades if start <= t.exit_date < end]
        return summarize(self.dates[lo:hi], self.equity[lo:hi], trades)


def _d(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=NY)


def _floor(x: Decimal) -> Decimal:
    return x.to_integral_value(rounding=ROUND_FLOOR)


class Simulator:
    def __init__(self, strategy: Strategy, policy: RiskPolicy, calendar: MarketCalendar):
        self.strategy = strategy
        self.policy = policy
        self.cal = calendar
        self.costs = CostModel.from_policy(policy)
        self.criteria = UniverseCriteria.from_policy(policy)

    # ----- point-in-time universe -----------------------------------------------------------
    def eligibility(
        self, raw: Mapping[str, Sequence[BarRecord]], sessions: Sequence[date]
    ) -> dict[date, frozenset[str]]:
        """Symbols passing the production liquidity screen as of each session's close."""
        out: dict[date, set[str]] = {d: set() for d in sessions}
        n = self.criteria.lookback_sessions
        for sym, series in raw.items():
            asset = AssetInfo(sym, sym, "NYSE", "us_equity", "active", True)
            by_day = {b.ts.astimezone(NY).date(): i for i, b in enumerate(series)}
            for d in sessions:
                i = by_day.get(d)
                if i is None:
                    continue
                window = series[max(0, i - n + 1) : i + 1]
                res = liquidity_screen(
                    asset, window, self.criteria, as_of=d, now=_d(d) + timedelta(hours=20)
                )
                if not isinstance(res, str):
                    out[d].add(sym)
        return {d: frozenset(s) for d, s in out.items()}

    # ----- main loop --------------------------------------------------------------------------
    def run(
        self,
        bars: Mapping[str, Sequence[BarRecord]],
        raw: Mapping[str, Sequence[BarRecord]],
        start: date,
        end: date,
        capital: Decimal | None = None,
        eligible: Mapping[date, frozenset[str]] | None = None,
    ) -> BacktestResult:
        """``eligible`` (from ``eligibility``) can be passed in to share it across runs."""
        strat = self.strategy
        sessions = self.cal.sessions_between(start, end)
        if eligible is None:
            eligible = self.eligibility(raw, sessions)
        index = {
            s: {b.ts.astimezone(NY).date(): i for i, b in enumerate(series)}
            for s, series in bars.items()
        }
        # Validate each series once; a window containing a bad bar is skipped that day, which is
        # what validating every window (as production does) would decide.
        bad: dict[str, list[int]] = {}
        for sym, series in bars.items():
            if not series:
                continue
            report = validate_bars(list(series), now=series[-1].ts + timedelta(days=1))
            bad[sym] = sorted(
                index[sym][iss.ts.astimezone(NY).date()]
                for iss in report.issues
                if iss.severity == "critical"
                and iss.ts is not None
                and iss.ts.astimezone(NY).date() in index[sym]
            )
        cash = (
            capital
            if capital is not None
            else Decimal(str(self.policy.account.starting_equity_usd))
        )
        positions: dict[str, SimPosition] = {}
        pending: list[Signal] = []
        res = BacktestResult(strat.id, strat.version, strat.params.model_dump())
        prev_close_equity = cash
        dd_state = DrawdownState()
        prior_universe: frozenset[str] = frozenset()

        def bar(sym: str, d: date) -> BarRecord | None:
            i = index.get(sym, {}).get(d)
            return bars[sym][i] if i is not None else None

        for d in sessions:
            session = self.cal.session(d)
            assert session is not None
            now = session.open + timedelta(
                minutes=self.policy.session.no_new_positions_minutes_after_open
            )
            # ---------- open: exits, then entries ----------
            opens = {s: b.open for s in positions if (b := bar(s, d)) is not None}
            entries_today = 0
            for sig in sorted(pending, key=lambda s: (s.kind != "exit", s.symbol)):
                b = bar(sig.symbol, d)
                if b is None:
                    continue  # no session data: the order could not have traded
                bid, ask = self.costs.quote(b.open)
                long_mv = sum(
                    (p.qty * opens.get(s, p.entry_price) for s, p in positions.items()), Decimal(0)
                )
                equity_now = cash + long_mv
                hwm, cooldown_left = at_session(dd_state, d, equity_now, self.policy, self.cal)
                ctx = RiskContext(
                    now=now,
                    mode="paper",
                    kill_switch_engaged=False,
                    strategy_status=StrategyStatus.PAPER,
                    account=AccountState(
                        equity=equity_now,
                        last_equity=prev_close_equity,
                        cash=cash,
                        long_market_value=long_mv,
                        trading_blocked=False,
                        as_of=now,
                        shorting_enabled=False,
                    ),
                    high_water_mark=hwm,
                    drawdown_cooldown_remaining=cooldown_left,
                    positions={s: p.qty for s, p in positions.items()},
                    open_orders=(),
                    entries_submitted_today=entries_today,
                    universe_members=prior_universe,
                    universe_stale=False,
                    quote=QuoteState(bid=bid, ask=ask, ts=now - timedelta(seconds=1)),
                    strategy_position_qty=positions[sig.symbol].qty
                    if sig.symbol in positions
                    else Decimal(0),
                    earnings_blackout=False,  # not simulated (caveat)
                )
                decision = evaluate(sig, ctx, self.policy, self.cal)
                if not decision.approved:
                    for name in decision.failed:
                        res.rejections[name] += 1
                        res.first_halt.setdefault(name, d.isoformat())
                    continue
                assert decision.qty is not None and decision.limit_price is not None
                cap = self.costs.participation_cap(b.volume)
                qty = min(decision.qty, cap)
                if sig.kind == "exit":
                    px = b.open * (1 - self.costs.half_spread - self.costs.slippage)
                    if px < decision.limit_price or qty < 1:
                        res.unfilled += 1
                        continue
                    if qty < decision.qty:
                        res.partial_fills += 1
                    cash += self._close(res, sig.symbol, positions, qty, px, d, "signal")
                else:
                    entries_today += 1  # production counts submitted entries
                    px = ask * (1 + self.costs.slippage)
                    if px > decision.limit_price or qty < 1:
                        res.unfilled += 1
                        continue
                    if qty < decision.qty:
                        res.partial_fills += 1
                    assert sig.stop_price is not None
                    cash -= qty * px
                    positions[sig.symbol] = SimPosition(qty, px, sig.stop_price, d)
            pending = []
            # ---------- intraday: protective stops ----------
            for sym in list(positions):
                b = bar(sym, d)
                if b is None:
                    continue
                pos = positions[sym]
                slip = self.costs.half_spread + self.costs.stop_slippage
                if b.open <= pos.stop_price and pos.entry_date != d:
                    cash += self._close(
                        res, sym, positions, pos.qty, b.open * (1 - slip), d, "gap_stop"
                    )
                elif b.low <= pos.stop_price:
                    cash += self._close(
                        res, sym, positions, pos.qty, pos.stop_price * (1 - slip), d, "stop"
                    )
            # ---------- close: mark, then generate signals ----------
            closes = {s: b.close for s in positions if (b := bar(s, d)) is not None}
            equity = cash + sum(
                (p.qty * closes.get(s, p.entry_price) for s, p in positions.items()), Decimal(0)
            )
            res.dates.append(d)
            res.equity.append(float(equity))
            res.exposed_days += 1 if positions else 0
            prev_close_equity = equity
            before = dd_state
            dd_state = dd_step(dd_state, d, equity, self.policy, self.cal)
            if dd_state.halted_on == d:
                res.drawdown_halts.append(d.isoformat())
            elif before.halted_on is not None and dd_state.halted_on is None:
                res.drawdown_resets.append(d.isoformat())
            prior_universe = eligible.get(d, frozenset())
            windows = {}
            for sym, series in bars.items():
                i = index[sym].get(d)
                if i is None:
                    continue
                lo = max(0, i - strat.lookback + 1)
                marks = bad.get(sym, [])
                k = bisect_left(marks, lo)
                if k < len(marks) and marks[k] <= i:
                    res.skipped_bad_windows += 1
                    continue
                windows[sym] = series[lo : i + 1]
            held = {
                s: OpenPosition(
                    p.qty,
                    p.entry_price,
                    p.entry_date,
                    max(len(self.cal.sessions_between(p.entry_date, d)) - 1, 0),
                )
                for s, p in positions.items()
            }
            signals, _ = strat.generate(d, windows, held, trusted=True)
            # Entries only for symbols in the universe known after this close; exits always.
            pending = [s for s in signals if s.kind == "exit" or s.symbol in prior_universe]
            for s in signals:
                if s.kind == "entry" and s.symbol not in prior_universe:
                    res.rejections["universe"] += 1
                    res.first_halt.setdefault("universe", d.isoformat())
            res.signals += len(pending)

        # Close what's left at the last close so trade statistics are complete.
        if res.dates:
            last = res.dates[-1]
            for sym in list(positions):
                b = bar(sym, last)
                px = (b.close if b else positions[sym].entry_price) * (1 - self.costs.half_spread)
                cash += self._close(
                    res, sym, positions, positions[sym].qty, px, last, "end_of_test"
                )
        return res

    def _close(
        self,
        res: BacktestResult,
        sym: str,
        positions: dict[str, SimPosition],
        qty: Decimal,
        px: Decimal,
        d: date,
        reason: str,
    ) -> Decimal:
        pos = positions[sym]
        fees = self.costs.sell_fees(qty, px)
        res.trades.append(
            Trade(
                sym,
                pos.entry_date,
                d,
                qty,
                pos.entry_price,
                px,
                fees,
                reason,
                pos.entry_price - pos.stop_price,
            )
        )
        if qty >= pos.qty:
            del positions[sym]
        else:
            pos.qty -= qty
        return qty * px - fees
