"""Account-level paper performance from recorded session-close equity, versus SPY.

Uses ``equity_closes`` (written after every broker sync) and stored adjusted SPY daily bars for
the same sessions. Deposits and withdrawals are not tracked: a paper account reset shows up as
a return. Metrics are for the whole paper account, which may hold more than the policy budget
ATLAS sizes against.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.backtesting.metrics import daily_returns, max_drawdown_pct, summarize
from atlas.core.data.calendar import NY
from atlas.core.models.db import Bar, EquityClose

BENCHMARK = "SPY"


def _corr_beta(a: list[float], b: list[float]) -> tuple[float | None, float | None]:
    n = len(a)
    if n < 3:
        return None, None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / (n - 1)
    va = sum((x - ma) ** 2 for x in a) / (n - 1)
    vb = sum((y - mb) ** 2 for y in b) / (n - 1)
    if va <= 0 or vb <= 0:
        return None, None
    return round(cov / math.sqrt(va * vb), 3), round(cov / vb, 3)


def benchmark_closes(session: Session, days: list[date]) -> dict[date, float]:
    if not days:
        return {}
    start = datetime.combine(days[0], datetime.min.time(), NY)
    end = datetime.combine(days[-1] + timedelta(days=1), datetime.min.time(), NY)
    rows = session.execute(
        select(Bar.ts, Bar.close).where(
            Bar.symbol == BENCHMARK,
            Bar.timeframe == "1Day",
            Bar.adjustment == "all",
            Bar.ts >= start,
            Bar.ts < end,
        )
    ).all()
    out = {}
    for ts, close in rows:
        ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        out[ts.astimezone(NY).date()] = float(close)
    return out


def account_performance(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(EquityClose.day, EquityClose.equity).order_by(EquityClose.day)
    ).all()
    days = [d for d, _ in rows]
    equity = [float(e) for _, e in rows]
    out: dict[str, Any] = {
        "sessions": len(days),
        "curve": [[d.isoformat(), round(e, 2)] for d, e in zip(days, equity, strict=True)],
        "benchmark": BENCHMARK,
    }
    if len(days) < 2:
        out["metrics"] = None
        out["note"] = "needs at least two recorded session closes"
        return out
    out["metrics"] = summarize(days, equity, [])
    spy = benchmark_closes(session, days)
    both = [d for d in days if d in spy]
    out["benchmark_curve"] = [[d.isoformat(), round(spy[d], 4)] for d in both]
    if len(both) >= 2:
        eq_by_day = dict(zip(days, equity, strict=True))
        a = daily_returns([eq_by_day[d] for d in both])
        b = daily_returns([spy[d] for d in both])
        corr, beta = _corr_beta(a, b)
        acct_ret = eq_by_day[both[-1]] / eq_by_day[both[0]] - 1
        spy_ret = spy[both[-1]] / spy[both[0]] - 1
        out["comparison"] = {
            "start": both[0].isoformat(),
            "end": both[-1].isoformat(),
            "account_return_pct": round(acct_ret * 100, 2),
            "benchmark_return_pct": round(spy_ret * 100, 2),
            "excess_return_pct": round((acct_ret - spy_ret) * 100, 2),
            "benchmark_max_drawdown_pct": round(max_drawdown_pct([spy[d] for d in both]), 2),
            "correlation": corr,
            "beta": beta,
            "missing_benchmark_sessions": len(days) - len(both),
        }
    else:
        out["comparison"] = None
    return out
