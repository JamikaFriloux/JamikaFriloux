"""Strategy track records and the PAPER -> LIVE_CANDIDATE gate.

Two records per strategy, recomputed after each close and stored in ``track_records``:

  * ``forward_sim``: the validation simulator (same strategy, risk engine, costs and symbols
    as the anchoring validation report) run only on sessions after that report's data ended.
    Nothing in it was seen when the strategy was validated, so it is an out-of-sample forward
    test. It runs for every strategy, including RESEARCH ones that never place orders.
  * ``paper``: round trips from the strategy's own filled paper orders since its latest
    promotion to PAPER (current version only), judged against ``track_record_gates``.

Promotion to LIVE_CANDIDATE needs a passing ``paper`` record for the exact version, parameters
and policy, no older than ``record_max_age_days``. LIVE_CANDIDATE keeps paper trading; nothing
in this deployment can submit a live order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.core.backtesting.metrics import Trade, max_drawdown_pct, summarize
from atlas.core.backtesting.runner import load_history
from atlas.core.backtesting.simulator import Simulator
from atlas.core.backtesting.validation import params_hash
from atlas.core.configuration.policy import LoadedPolicy, TrackRecordGatesPolicy
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import (
    AuditLog,
    Bar,
    StrategyRecord,
    StrategyStatus,
    TrackRecord,
    ValidationReport,
)
from atlas.core.performance.ledger import build_ledger
from atlas.core.strategies.base import Strategy

FORWARD_SIM = "forward_sim"
PAPER = "paper"
TRADING_STATUSES = frozenset({StrategyStatus.PAPER, StrategyStatus.LIVE_CANDIDATE})
REFERENCE_KEYS = (
    "trades",
    "sharpe",
    "profit_factor",
    "win_rate_pct",
    "avg_r",
    "avg_return_pct",
    "max_drawdown_pct",
    "net_pnl",
)


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    value: Any
    threshold: str
    detail: str = ""


def _finite(v: Any) -> Any:
    """JSON can't hold inf/nan; record them as strings so nothing is silently dropped."""
    if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
        return str(v)
    if isinstance(v, dict):
        return {k: _finite(x) for k, x in v.items()}
    return v


def trade_json(t: Trade) -> dict[str, Any]:
    return {
        "symbol": t.symbol,
        "entry_date": t.entry_date.isoformat(),
        "exit_date": t.exit_date.isoformat(),
        "qty": str(t.qty),
        "entry_price": str(t.entry_price),
        "exit_price": str(t.exit_price),
        "fees": str(t.fees),
        "pnl": str(t.pnl.quantize(Decimal("0.01"))),
        "return_pct": round(t.return_pct, 3),
        "r_multiple": None if t.r_multiple is None else round(t.r_multiple, 3),
        "exit_reason": t.exit_reason,
    }


def anchor_report(session: Session, row: StrategyRecord) -> ValidationReport | None:
    """Latest validation report for the exact version and parameters (passing ones first)."""
    return session.scalars(
        select(ValidationReport)
        .where(
            ValidationReport.strategy_id == row.id,
            ValidationReport.version == row.version,
            ValidationReport.params_hash == params_hash(row.params),
        )
        .order_by(ValidationReport.passed.desc(), ValidationReport.id.desc())
        .limit(1)
    ).first()


def backtest_reference(report: ValidationReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    full = (report.metrics or {}).get("full", {})
    return {
        "report_id": report.id,
        "passed": report.passed,
        "data_start": report.data_start.isoformat(),
        "data_end": report.data_end.isoformat(),
        **{k: full.get(k) for k in REFERENCE_KEYS},
    }


def latest_bar_date(session: Session, symbols: list[str], as_of: date) -> date | None:
    end_ts = datetime(as_of.year, as_of.month, as_of.day, 23, 59, tzinfo=NY)
    latest = session.scalar(
        select(func.max(Bar.ts)).where(
            Bar.symbol.in_(symbols),
            Bar.timeframe == "1Day",
            Bar.adjustment == "all",
            Bar.ts <= end_ts,
        )
    )
    if latest is None:
        return None
    latest = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
    return latest.astimezone(NY).date()


def forward_sim(
    session: Session,
    strategy: Strategy,
    row: StrategyRecord,
    *,
    policy: LoadedPolicy,
    calendar: MarketCalendar,
    as_of: date,
) -> dict[str, Any]:
    report = anchor_report(session, row)
    base: dict[str, Any] = {
        "kind": FORWARD_SIM,
        "anchor_report_id": report.id if report else None,
        "metrics": {"backtest_reference": backtest_reference(report)},
    }
    if report is None:
        return {**base, "note": "no validation report for this version; nothing to anchor to"}
    later = [d for d in calendar.sessions_between(report.data_end, as_of) if d > report.data_end]
    end = latest_bar_date(session, list(report.symbols), as_of)
    if not later or end is None or end < later[0]:
        return {
            **base,
            "start": later[0] if later else None,
            "note": f"no sessions with stored data after the validation data ({report.data_end})",
        }
    start = later[0]
    warmup = timedelta(days=int((strategy.lookback + 40) * 1.6) + 10)
    bars = load_history(session, report.symbols, "all", end, start - warmup)
    raw = load_history(session, report.symbols, "raw", end, start - warmup)
    sim = Simulator(strategy, policy.policy, calendar)
    res = sim.run(bars, raw, start, end)
    # The simulator closes everything at the end; here those are open positions, not trades.
    closed = [t for t in res.trades if t.exit_reason != "end_of_test"]
    still_open = [t for t in res.trades if t.exit_reason == "end_of_test"]
    metrics = summarize(res.dates, res.equity, closed, res.exposed_days)
    metrics["rejections"] = dict(res.rejections)
    metrics["backtest_reference"] = backtest_reference(report)
    return {
        **base,
        "start": start,
        "as_of": end,
        "sessions": len(res.dates),
        "metrics": _finite(metrics),
        "equity_curve": [
            [d.isoformat(), round(e, 2)] for d, e in zip(res.dates, res.equity, strict=True)
        ],
        "trades": [trade_json(t) for t in closed],
        "open_positions": [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date.isoformat(),
                "qty": str(t.qty),
                "entry_price": str(t.entry_price),
                "mark": str(t.exit_price),
                "unrealized_pnl": str(t.pnl.quantize(Decimal("0.01"))),
            }
            for t in still_open
        ],
    }


def paper_since(session: Session, strategy_id: str, version: str) -> date | None:
    """Day of the latest RESEARCH -> PAPER promotion of this version (start of the stint)."""
    for entry in session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "strategy.status_changed", AuditLog.target == strategy_id)
        .order_by(AuditLog.id.desc())
    ):
        d = entry.details or {}
        if d.get("to") == "PAPER" and d.get("from") == "RESEARCH":
            if d.get("version") != version:
                return None  # the latest stint was a different version
            ts = entry.ts if entry.ts.tzinfo else entry.ts.replace(tzinfo=UTC)
            return ts.astimezone(NY).date()
    return None


def evaluate_gates(
    gates: TrackRecordGatesPolicy,
    *,
    sessions: int,
    trades: list[Trade],
    drawdown_pct: float,
    metrics: dict[str, Any],
    reference: dict[str, Any] | None,
) -> list[Gate]:
    pf = metrics.get("profit_factor")
    avg_r = metrics.get("avg_r")
    ref_r = (reference or {}).get("avg_r")
    need_r = None if ref_r is None else gates.min_expectancy_vs_backtest * float(ref_r)
    return [
        Gate(
            "paper_sessions",
            sessions >= gates.min_paper_sessions,
            sessions,
            f">= {gates.min_paper_sessions}",
        ),
        Gate(
            "paper_trades",
            len(trades) >= gates.min_paper_trades,
            len(trades),
            f">= {gates.min_paper_trades}",
        ),
        Gate(
            "profit_factor",
            pf is not None and pf >= gates.min_profit_factor,
            pf,
            f">= {gates.min_profit_factor}",
        ),
        Gate(
            "drawdown",
            drawdown_pct <= gates.max_drawdown_pct,
            round(drawdown_pct, 2),
            f"<= {gates.max_drawdown_pct}% of budget",
        ),
        Gate(
            "expectancy_vs_backtest",
            avg_r is not None and need_r is not None and avg_r > 0 and avg_r >= need_r,
            avg_r,
            f">= {gates.min_expectancy_vs_backtest} x backtest avg R"
            + (f" ({round(need_r, 3)})" if need_r is not None else ""),
            "" if ref_r is not None else "no validation report to compare with",
        ),
    ]


def paper_record(
    session: Session,
    row: StrategyRecord,
    *,
    policy: LoadedPolicy,
    calendar: MarketCalendar,
    as_of: date,
) -> dict[str, Any]:
    report = anchor_report(session, row)
    reference = backtest_reference(report)
    since = paper_since(session, row.id, row.version)
    base: dict[str, Any] = {
        "kind": PAPER,
        "anchor_report_id": report.id if report else None,
        "start": since,
    }
    gates_policy = policy.policy.track_record_gates
    budget = Decimal(str(policy.policy.account.starting_equity_usd))
    if since is None:
        gates = evaluate_gates(
            gates_policy, sessions=0, trades=[], drawdown_pct=0.0, metrics={}, reference=reference
        )
        return {
            **base,
            "metrics": {"backtest_reference": reference},
            "gates": [g.__dict__ for g in gates],
            "passed": False,
            "note": "no promotion of this version to PAPER on record",
        }
    ledger = build_ledger(session, row.id)
    trades = sorted(
        (
            p.trade
            for p in ledger.trades
            if p.version == row.version and p.trade.entry_date >= since
        ),
        key=lambda t: (t.exit_date, t.symbol),
    )
    days = [d for d in calendar.sessions_between(since, as_of) if d > since]
    # Realised P&L on the policy budget, marked at each session close.
    curve, cum, i = [], Decimal(0), 0
    for d in days:
        while i < len(trades) and trades[i].exit_date <= d:
            cum += trades[i].pnl
            i += 1
        curve.append(float(budget + cum))
    metrics = summarize(days, curve, trades) if days else summarize([], [], trades)
    drawdown = max_drawdown_pct([float(budget), *curve]) if curve else 0.0
    metrics["backtest_reference"] = reference
    metrics["unmatched_sells"] = {k: str(v) for k, v in ledger.unmatched_sell_qty.items()}
    gates = evaluate_gates(
        gates_policy,
        sessions=len(days),
        trades=trades,
        drawdown_pct=drawdown,
        metrics=metrics,
        reference=reference,
    )
    return {
        **base,
        "as_of": as_of,
        "sessions": len(days),
        "metrics": _finite(metrics),
        "equity_curve": [[d.isoformat(), round(e, 2)] for d, e in zip(days, curve, strict=True)],
        "trades": [trade_json(t) for t in trades],
        "open_positions": [
            {
                "symbol": lot.symbol,
                "entry_date": lot.entry_date.isoformat(),
                "qty": str(lot.qty),
                "entry_price": str(lot.price),
            }
            for lot in ledger.open_lots
            if lot.version == row.version
        ],
        "gates": [g.__dict__ for g in gates],
        "passed": all(g.passed for g in gates),
    }


def store(
    session: Session,
    row: StrategyRecord,
    rec: dict[str, Any],
    *,
    policy: LoadedPolicy,
    as_of: date,
    now: datetime,
) -> TrackRecord:
    """One row per strategy, kind and session: a re-run replaces that session's row."""
    key = {
        "strategy_id": row.id,
        "kind": rec["kind"],
        "as_of": rec.get("as_of") or as_of,
        "version": row.version,
        "params_hash": params_hash(row.params),
        "policy_sha256": policy.sha256,
    }
    existing = session.scalars(
        select(TrackRecord).where(*(getattr(TrackRecord, k) == v for k, v in key.items()))
    ).first()
    tr = existing or TrackRecord(**key)
    tr.created_at = now
    tr.start = rec.get("start")
    tr.sessions = rec.get("sessions", 0)
    tr.anchor_report_id = rec.get("anchor_report_id")
    tr.metrics = rec.get("metrics", {})
    tr.equity_curve = rec.get("equity_curve", [])
    tr.trades = rec.get("trades", [])
    tr.open_positions = rec.get("open_positions", [])
    tr.gates = rec.get("gates", [])
    tr.passed = rec.get("passed")
    tr.note = rec.get("note")
    if existing is None:
        session.add(tr)
    session.flush()
    return tr


def update_track_records(
    session: Session,
    *,
    strategies: dict[str, Strategy],
    rows: list[StrategyRecord],
    policy: LoadedPolicy,
    calendar: MarketCalendar,
    as_of: date,
    now: datetime,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        if row.status == StrategyStatus.RETIRED or row.id not in strategies:
            continue
        fwd = forward_sim(
            session, strategies[row.id], row, policy=policy, calendar=calendar, as_of=as_of
        )
        summary = {FORWARD_SIM: store(session, row, fwd, policy=policy, as_of=as_of, now=now).id}
        if row.status in TRADING_STATUSES:
            pr = paper_record(session, row, policy=policy, calendar=calendar, as_of=as_of)
            summary[PAPER] = store(session, row, pr, policy=policy, as_of=as_of, now=now).id
            summary["passed"] = pr["passed"]
        out[row.id] = summary
    return out


def passing_track_record(session: Session, strategy_id: str, policy: LoadedPolicy) -> str | None:
    """Id of a passing paper record that justifies LIVE_CANDIDATE, else None."""
    row = session.get(StrategyRecord, strategy_id)
    if row is None:
        return None
    max_age = policy.policy.track_record_gates.record_max_age_days
    cutoff = datetime.now(UTC) - timedelta(days=max_age)
    rec = session.scalars(
        select(TrackRecord)
        .where(
            TrackRecord.strategy_id == strategy_id,
            TrackRecord.kind == PAPER,
            TrackRecord.version == row.version,
            TrackRecord.params_hash == params_hash(row.params),
            TrackRecord.policy_sha256 == policy.sha256,
            TrackRecord.passed.is_(True),
            TrackRecord.created_at >= cutoff,
        )
        .order_by(TrackRecord.id.desc())
        .limit(1)
    ).first()
    return str(rec.id) if rec is not None else None
