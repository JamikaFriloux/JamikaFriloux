from datetime import date, datetime
from decimal import Decimal

import pytest

from atlas.core.backtesting.costs import CostModel
from atlas.core.backtesting.simulator import Simulator
from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.strategies.base import Strategy, StrategyParams
from atlas.core.strategies.baselines import TrendBreakout

CAL = MarketCalendar()
DAYS = CAL.sessions_between(date(2026, 1, 2), date(2026, 3, 31))
D = Decimal


def bars_for(sym, closes, *, opens=None, lows=None, volume=1_000_000):
    out = []
    for i, (d, c) in enumerate(zip(DAYS, closes, strict=False)):
        o = D(str(opens[i])) if opens and opens[i] is not None else D(str(c))
        lo = D(str(lows[i])) if lows and lows[i] is not None else min(o, D(str(c))) - D("0.5")
        hi = max(o, D(str(c))) + D("0.5")
        out.append(
            BarRecord(
                symbol=sym,
                timeframe="1Day",
                ts=datetime(d.year, d.month, d.day, tzinfo=NY),
                open=o,
                high=hi,
                low=lo,
                close=D(str(c)),
                volume=D(volume),
                source="t",
                adjustment="all",
            )
        )
    return out


class Scripted(Strategy):
    """Enters on given sessions with a given stop; exits on given sessions."""

    id, version, description = "scripted", "1", "test"

    def __init__(self, entries=(), exits=(), stop_offset=5.0):
        self.params = StrategyParams()
        self.entries, self.exits, self.stop_offset = set(entries), set(exits), stop_offset

    @property
    def lookback(self):
        return 1

    def decide(self, symbol, bars, position):
        d = bars[-1].ts.astimezone(NY).date()
        if position is None and d in self.entries:
            return self.signal(symbol, "entry", bars, stop=float(bars[-1].close) - self.stop_offset)
        if position is not None and d in self.exits:
            return self.signal(symbol, "exit", bars)
        return None


def sim(strategy, policy):
    return Simulator(strategy, policy.policy, CAL)


def run(policy, strategy, series, raw=None):
    s = {series[0].symbol: series}
    return sim(strategy, policy).run(s, raw or s, DAYS[0], DAYS[-1])


def test_entry_next_open_then_exit_signal(policy):
    closes = [100.0] * len(DAYS)
    res = run(policy, Scripted(entries=[DAYS[25]], exits=[DAYS[30]]), bars_for("AAA", closes))
    (t,) = res.trades
    costs = CostModel.from_policy(policy.policy)
    # Signal at the close of DAYS[25]; filled at the next open: 100 * (1 + 2bps spread + 5bps slip)
    assert t.entry_date == DAYS[26] and t.entry_price == D(100) * (1 + costs.half_spread) * (
        1 + costs.slippage
    )
    # Exit at the open after DAYS[30], at 100 * (1 - 2bps - 5bps)
    assert t.exit_date == DAYS[31] and t.exit_reason == "signal"
    assert t.exit_price == D(100) * (1 - costs.half_spread - costs.slippage)
    # Sized by the production risk engine: $25 risk budget / ~5.27 risk per share -> 4 shares
    assert t.qty == 4
    assert t.fees == costs.sell_fees(t.qty, t.exit_price) and t.pnl < 0  # costs only
    assert res.equity[-1] == pytest.approx(10_000 + float(t.pnl), abs=1e-6)


def test_stop_and_gap_fills(policy):
    costs = CostModel.from_policy(policy.policy)
    slip = costs.half_spread + costs.stop_slippage
    closes = [100.0] * len(DAYS)
    lows = [None] * len(DAYS)
    lows[28] = 90.0  # trades through the 95 stop intraday
    res = run(policy, Scripted(entries=[DAYS[25]]), bars_for("AAA", closes, lows=lows))
    assert res.trades[0].exit_reason == "stop" and res.trades[0].exit_date == DAYS[28]
    assert res.trades[0].exit_price == D(95) * (1 - slip)

    opens = [None] * len(DAYS)
    opens[28] = 80.0  # gaps far below the stop: filled at the open, not the stop
    res = run(policy, Scripted(entries=[DAYS[25]]), bars_for("AAA", closes, opens=opens))
    t = res.trades[0]
    assert t.exit_reason == "gap_stop" and t.exit_price == D(80) * (1 - slip)
    assert t.r_multiple < -3  # the gap cost far more than the planned 1R


def test_participation_limits_fills(policy):
    closes = [100.0] * len(DAYS)
    # A $50k/day stock fails the $20M dollar-volume screen, so it's never tradable.
    res = run(policy, Scripted(entries=[DAYS[25]]), bars_for("AAA", closes, volume=500), raw=None)
    assert res.trades == [] and res.rejections["universe"] >= 1  # ADV too low: never eligible
    raw = {"AAA": bars_for("AAA", closes, volume=1_000_000)}  # liquid by the screen...
    thin = bars_for("AAA", closes, volume=300)  # ...but only 300 shares trade per session
    res = sim(Scripted(entries=[DAYS[25]]), policy).run({"AAA": thin}, raw, DAYS[0], DAYS[-1])
    # Risk sizing wants 4 shares; 1% participation of 300 allows 3.
    assert res.trades[0].qty == 3 and res.partial_fills == 1


def test_point_in_time_universe_uses_raw_prices(policy):
    closes = [100.0] * len(DAYS)
    cheap_raw = {"AAA": bars_for("AAA", [8.0] * len(DAYS), volume=10_000_000)}  # $8 before a split
    res = sim(Scripted(entries=[DAYS[25]]), policy).run(
        {"AAA": bars_for("AAA", closes)}, cheap_raw, DAYS[0], DAYS[-1]
    )
    assert res.trades == [] and res.rejections["universe"] == 1


def test_drawdown_limit_halts_new_entries(policy):
    # Stops cap a normal loss near the $25 risk budget, so use gaps: each opens 20 below entry
    # (4 shares x ~$20 = ~$80), breaching the $500 drawdown limit after ~7 trades.
    closes = [100.0] * len(DAYS)
    opens = [None] * len(DAYS)
    entries = DAYS[22:58:3]
    for e in entries:
        opens[DAYS.index(e) + 2] = 80.0
    res = run(policy, Scripted(entries=entries), bars_for("AAA", closes, opens=opens))
    assert res.rejections["drawdown"] >= 1 and "drawdown" in res.first_halt
    assert all(t.exit_reason == "gap_stop" for t in res.trades)
    assert len(res.trades) < len(entries)


def test_no_lookahead(policy):
    """Decisions up to a date don't change when later data changes."""
    s = TrendBreakout()
    closes = [100 + (1.5 * i if i % 15 else -12) for i in range(len(DAYS))]  # trend with pullbacks
    full = bars_for("AAA", closes)
    alt = list(full[:40]) + bars_for("AAA", [50.0] * len(DAYS))[40:]
    s.params = s.params.model_copy(
        update={"trend_n": 20, "breakout_n": 10, "exit_n": 5, "atr_n": 5}
    )
    a = sim(s, policy).run({"AAA": full}, {"AAA": full}, DAYS[0], DAYS[-1])
    b = sim(s, policy).run({"AAA": alt}, {"AAA": alt}, DAYS[0], DAYS[-1])
    assert any(t.entry_date < DAYS[40] for t in a.trades), "test needs trades before the cut"
    assert a.equity[:40] == b.equity[:40]
    assert [t for t in a.trades if t.exit_date < DAYS[40]] == [
        t for t in b.trades if t.exit_date < DAYS[40]
    ]


def test_baseline_runs_end_to_end(policy):
    closes = [100 + 1.5 * i for i in range(len(DAYS))]
    s = TrendBreakout()
    s.params = s.params.model_copy(
        update={"trend_n": 20, "breakout_n": 10, "exit_n": 5, "atr_n": 5}
    )
    res = sim(s, policy).run(
        {"AAA": bars_for("AAA", closes)}, {"AAA": bars_for("AAA", closes)}, DAYS[0], DAYS[-1]
    )
    summary = res.summary()
    assert res.trades and summary["trades"] == len(res.trades) and summary["total_return_pct"] > 0
    assert res.dates[0] == DAYS[0] and len(res.equity) == len(DAYS)


def test_drawdown_cooldown_then_trading_resumes(policy):
    """A breach blocks entries for 20 sessions; after the reset, the strategy trades again."""
    days = CAL.sessions_between(date(2026, 1, 2), date(2026, 8, 31))
    n = len(days)
    closes, opens = [100.0] * n, [None] * n
    entries = days[22 : n - 5 : 3]
    for e in entries[:8]:  # the first 8 trades gap 20 below their entry -> ~$80 losses each
        opens[days.index(e) + 2] = 80.0

    def make(sym):
        out = []
        for i, d in enumerate(days):
            o = D(str(opens[i])) if opens[i] is not None else D(str(closes[i]))
            c = D(str(closes[i]))
            out.append(
                BarRecord(
                    symbol=sym,
                    timeframe="1Day",
                    ts=datetime(d.year, d.month, d.day, tzinfo=NY),
                    open=o,
                    high=max(o, c) + D("0.5"),
                    low=min(o, c) - D("0.5"),
                    close=c,
                    volume=D(1_000_000),
                    source="t",
                    adjustment="all",
                )
            )
        return out

    s = {"AAA": make("AAA")}
    res = sim(Scripted(entries=entries), policy).run(s, s, days[0], days[-1])
    assert res.drawdown_halts, "the gap losses should breach the $500 limit"
    halt = date.fromisoformat(res.drawdown_halts[0])
    reset = date.fromisoformat(res.drawdown_resets[0])
    # The reset happens at the close of the 20th session after the halt...
    assert len([d for d in days if halt < d <= reset]) == 20
    # ...no entry fills during the cooldown, and trading resumes after the reset.
    assert not [t for t in res.trades if halt < t.entry_date <= reset]
    assert [t for t in res.trades if t.entry_date > reset]
