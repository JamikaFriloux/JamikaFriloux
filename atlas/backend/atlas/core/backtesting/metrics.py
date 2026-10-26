"""Performance metrics from an equity curve and a trade list. Pure functions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

TRADING_DAYS = 252


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_date: date
    exit_date: date
    qty: Decimal
    entry_price: Decimal
    exit_price: Decimal
    fees: Decimal
    exit_reason: str  # signal / stop / gap_stop / end_of_test
    risk_per_share: Decimal  # entry - stop at entry

    @property
    def pnl(self) -> Decimal:
        return (self.exit_price - self.entry_price) * self.qty - self.fees

    @property
    def return_pct(self) -> float:
        return float(self.pnl / (self.entry_price * self.qty)) * 100

    @property
    def r_multiple(self) -> float | None:
        if self.risk_per_share <= 0:
            return None
        return float(self.pnl / (self.risk_per_share * self.qty))


def daily_returns(equity: Sequence[float]) -> list[float]:
    return [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]


def max_drawdown_pct(equity: Sequence[float]) -> float:
    peak, worst = -math.inf, 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return -worst * 100


def summarize(
    dates: Sequence[date], equity: Sequence[float], trades: Sequence[Trade], exposed_days: int = 0
) -> dict[str, Any]:
    """Metrics for one span. Sharpe/Sortino are annualized from daily returns (rf = 0)."""
    n_days = len(equity)
    rets = daily_returns(equity)
    mean = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    downside = [min(r, 0.0) for r in rets]
    dvar = sum(r * r for r in downside) / len(downside) if downside else 0.0
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9) if n_days > 1 else 0.0
    total = equity[-1] / equity[0] - 1 if n_days > 1 and equity[0] > 0 else 0.0
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    gross_win, gross_loss = float(sum(wins, Decimal(0))), float(-sum(losses, Decimal(0)))
    rs = [r for t in trades if (r := t.r_multiple) is not None]
    return {
        "start": dates[0].isoformat() if dates else None,
        "end": dates[-1].isoformat() if dates else None,
        "years": round(years, 2),
        "start_equity": round(equity[0], 2) if equity else None,
        "end_equity": round(equity[-1], 2) if equity else None,
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(((1 + total) ** (1 / years) - 1) * 100, 2)
        if years > 0 and total > -1
        else None,
        "volatility_pct": round(math.sqrt(var * TRADING_DAYS) * 100, 2),
        "sharpe": round(mean / math.sqrt(var) * math.sqrt(TRADING_DAYS), 3) if var > 0 else 0.0,
        "sortino": round(mean / math.sqrt(dvar) * math.sqrt(TRADING_DAYS), 3) if dvar > 0 else 0.0,
        "max_drawdown_pct": round(max_drawdown_pct(equity), 2),
        "exposure_pct": round(exposed_days / n_days * 100, 1) if n_days else 0.0,
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "profit_factor": round(gross_win / gross_loss, 3)
        if gross_loss > 0
        else (None if not wins else math.inf),
        "net_pnl": round(float(sum((t.pnl for t in trades), Decimal(0))), 2),
        "expectancy_per_trade": round(
            float(sum((t.pnl for t in trades), Decimal(0))) / len(trades), 2
        )
        if trades
        else None,
        "avg_return_pct": round(sum(t.return_pct for t in trades) / len(trades), 3)
        if trades
        else None,
        "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
        "fees": round(float(sum((t.fees for t in trades), Decimal(0))), 2),
    }
