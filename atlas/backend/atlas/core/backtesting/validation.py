"""Strategy validation: the evidence required to promote a strategy version to PAPER.

All numbers come from the event-driven simulator, i.e. from the production strategy, sizing
and risk-engine code, net of costs. Gates (``policy.yaml`` ``promotion_gates``):

  history        backtest span >= min_history_years
  trades         full-span trades >= min_trades
  profit_factor  full-span profit factor >= min_profit_factor
  sharpe         full-span Sharpe >= min_sharpe
  drawdown       full-span max drawdown <= max_drawdown_pct
  holdout        the last ``holdout_years`` on their own: trades and Sharpe minimums
  walk_forward   share of consecutive ``walk_forward_window_months`` windows with a positive
                 return >= min_profitable_windows_pct
  stability      share of one-at-a-time parameter neighbours (+/-10%) with positive net P&L
                 >= min_stable_neighbors_pct (guards against a lucky parameter choice)
  bootstrap      lower bound of the mean trade return at ``bootstrap_confidence`` > 0

The baselines use fixed, textbook parameters chosen before seeing this data, so the whole
span is out-of-sample for them except for literature knowledge; the holdout and walk-forward
gates test that the edge persists recently and isn't concentrated in one period. Every
report carries the simulator's caveats (e.g. survivorship bias) so they are never hidden.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from atlas.core.backtesting.costs import CostModel
from atlas.core.backtesting.simulator import CAVEATS, BacktestResult, Simulator
from atlas.core.configuration.policy import LoadedPolicy
from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.strategies.base import Strategy


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    value: Any
    threshold: Any
    detail: str = ""


@dataclass
class ValidationOutcome:
    strategy_id: str
    version: str
    params: dict[str, Any]
    params_hash: str
    passed: bool
    gates: list[Gate]
    data_start: date
    data_end: date
    symbols: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0


def params_hash(params: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(params), sort_keys=True).encode()).hexdigest()[:16]


def neighbor_params(strategy: Strategy, rel_step: float = 0.10) -> list[tuple[str, Strategy]]:
    """Variants changing one numeric parameter by +/- ``rel_step`` (ints by at least 1)."""
    out: list[tuple[str, Strategy]] = []
    base = strategy.params.model_dump()
    for name, value in base.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        step = max(1, round(value * rel_step)) if isinstance(value, int) else value * rel_step
        for sign in (-1, 1):
            new = value + sign * step
            new = round(new, 6) if isinstance(new, float) else new
            try:
                params = type(strategy.params).model_validate({**base, name: new})
            except ValueError:
                continue  # outside the parameter's allowed range
            variant = type(strategy)()
            variant.params = params
            out.append((f"{name}={new}", variant))
    return out


def bootstrap_lower_bound(
    values: Sequence[float], samples: int, confidence: float, seed: str
) -> float | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311 - seeded so reports are reproducible
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(samples))
    return means[int((1 - confidence) * samples)]


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, min(d.day, 28))


def validate_strategy(
    strategy: Strategy,
    policy: LoadedPolicy,
    calendar: MarketCalendar,
    bars: Mapping[str, Sequence[BarRecord]],
    raw: Mapping[str, Sequence[BarRecord]],
    *,
    end: date,
) -> ValidationOutcome:
    t0 = time.monotonic()
    g = policy.policy.promotion_gates
    first = min((s[0].ts.astimezone(NY).date() for s in bars.values() if s), default=end)
    sessions = calendar.sessions_between(first, end)
    # Warm-up: the first decision needs ``lookback`` sessions of history.
    start = sessions[min(strategy.lookback, len(sessions) - 1)] if sessions else end
    sim = Simulator(strategy, policy.policy, calendar)
    eligible = sim.eligibility(raw, calendar.sessions_between(start, end))
    base = sim.run(bars, raw, start, end, eligible=eligible)
    full = base.summary()
    years = full["years"]

    holdout_start = date(end.year - int(g.holdout_years), end.month, min(end.day, 28))
    holdout = base.window(holdout_start, end + timedelta(days=1)) or {}

    windows = []
    w_start = start
    while w_start < end:
        w_end = min(_add_months(w_start, g.walk_forward_window_months), end + timedelta(days=1))
        m = base.window(w_start, w_end)
        if m is not None:
            windows.append(m)
        w_start = w_end
    profitable = sum(1 for m in windows if m["total_return_pct"] > 0)
    wf_pct = profitable / len(windows) * 100 if windows else 0.0

    neighbors = []
    for label, variant in neighbor_params(strategy):
        r = Simulator(variant, policy.policy, calendar).run(
            bars, raw, start, end, eligible=eligible
        )
        s = r.summary()
        neighbors.append(
            {"change": label, "net_pnl": s["net_pnl"], "sharpe": s["sharpe"], "trades": s["trades"]}
        )
    stable = sum(1 for n in neighbors if n["net_pnl"] > 0)
    stable_pct = stable / len(neighbors) * 100 if neighbors else 0.0

    trade_returns = [t.return_pct for t in base.trades]
    lb = bootstrap_lower_bound(
        trade_returns,
        g.bootstrap_samples,
        g.bootstrap_confidence,
        seed=f"{strategy.id}:{strategy.version}",
    )

    def gate(name: str, passed: bool, value: Any, threshold: Any, detail: str = "") -> Gate:
        return Gate(name, bool(passed), value, threshold, detail)

    pf = full["profit_factor"]
    gates = [
        gate("history", years >= g.min_history_years, years, f">= {g.min_history_years} years"),
        gate("trades", full["trades"] >= g.min_trades, full["trades"], f">= {g.min_trades}"),
        gate(
            "profit_factor",
            pf is not None and pf >= g.min_profit_factor,
            pf,
            f">= {g.min_profit_factor}",
        ),
        gate("sharpe", full["sharpe"] >= g.min_sharpe, full["sharpe"], f">= {g.min_sharpe}"),
        gate(
            "drawdown",
            full["max_drawdown_pct"] <= g.max_drawdown_pct,
            full["max_drawdown_pct"],
            f"<= {g.max_drawdown_pct}%",
        ),
        gate(
            "holdout_trades",
            holdout.get("trades", 0) >= g.holdout_min_trades,
            holdout.get("trades", 0),
            f">= {g.holdout_min_trades} in the last {g.holdout_years:g} years",
        ),
        gate(
            "holdout_sharpe",
            holdout.get("sharpe", 0.0) >= g.holdout_min_sharpe
            and holdout.get("total_return_pct", 0.0) > 0,
            holdout.get("sharpe"),
            f">= {g.holdout_min_sharpe} with a positive return",
        ),
        gate(
            "walk_forward",
            wf_pct >= g.min_profitable_windows_pct,
            round(wf_pct, 1),
            f">= {g.min_profitable_windows_pct}% of {g.walk_forward_window_months}-month windows",
            f"{profitable}/{len(windows)} windows profitable",
        ),
        gate(
            "stability",
            stable_pct >= g.min_stable_neighbors_pct,
            round(stable_pct, 1),
            f">= {g.min_stable_neighbors_pct}% of neighbours profitable",
            f"{stable}/{len(neighbors)}",
        ),
        gate(
            "bootstrap",
            lb is not None and lb > 0,
            None if lb is None else round(lb, 4),
            f"{g.bootstrap_confidence:.0%} lower bound of mean trade return > 0%",
        ),
    ]
    caveats = list(CAVEATS)
    if "drawdown" in base.first_halt:
        caveats.append(
            f"drawdown_halt: the {policy.policy.limits.max_drawdown_pct}% drawdown limit blocked "
            f"new entries from {base.first_halt['drawdown']} (production behaves the same)"
        )
    step = max(1, len(base.dates) // 400)
    curve = [
        (d.isoformat(), round(v, 2))
        for d, v in zip(base.dates[::step], base.equity[::step], strict=True)
    ]
    if base.dates and (not curve or curve[-1][0] != base.dates[-1].isoformat()):
        curve.append((base.dates[-1].isoformat(), round(base.equity[-1], 2)))
    params = strategy.params.model_dump()
    return ValidationOutcome(
        strategy_id=strategy.id,
        version=strategy.version,
        params=params,
        params_hash=params_hash(params),
        passed=all(x.passed for x in gates),
        gates=gates,
        data_start=start,
        data_end=end,
        symbols=sorted(bars),
        metrics={
            "full": full,
            "holdout": holdout,
            "windows": windows,
            "neighbors": neighbors,
            "bootstrap_lower_bound_pct": lb,
            "rejections": dict(base.rejections),
            "first_halt": base.first_halt,
            "signals": base.signals,
            "unfilled": base.unfilled,
            "partial_fills": base.partial_fills,
            "skipped_bad_windows": base.skipped_bad_windows,
            "exit_reasons": _count([t.exit_reason for t in base.trades]),
            "cost_model": {
                k: str(v) for k, v in CostModel.from_policy(policy.policy).__dict__.items()
            },
        },
        equity_curve=curve,
        caveats=caveats,
        runtime_seconds=round(time.monotonic() - t0, 1),
    )


def _count(items: Sequence[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


__all__ = ["BacktestResult", "Gate", "ValidationOutcome", "neighbor_params", "validate_strategy"]
