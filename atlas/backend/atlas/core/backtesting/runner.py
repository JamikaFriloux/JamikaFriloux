"""Run a validation from stored history and record the report.

Runs in the research worker (no broker credentials). Scope matches the production signal
engine: benchmarks plus watchlist symbols in the current universe. Adjusted daily bars drive
the simulation; raw bars drive the point-in-time liquidity screen. History is loaded by the
executor's daily ingestion and the one-off ``atlas.scripts.backfill_history``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.core.backtesting.validation import validate_strategy
from atlas.core.configuration.policy import LoadedPolicy
from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import ingestion_symbols
from atlas.core.data.universe import current_universe, member_symbols
from atlas.core.models.db import Bar, StrategyStatus, ValidationReport
from atlas.core.strategies.registry import STRATEGIES, sync_registry


class ValidationUnavailable(RuntimeError):
    pass


def load_history(
    session: Session, symbols: Sequence[str], adjustment: str, end: date
) -> dict[str, list[BarRecord]]:
    end_ts = datetime(end.year, end.month, end.day, 23, 59, tzinfo=NY)
    rows = session.scalars(
        select(Bar)
        .where(
            Bar.symbol.in_(symbols),
            Bar.timeframe == "1Day",
            Bar.adjustment == adjustment,
            Bar.ts <= end_ts,
        )
        .order_by(Bar.symbol, Bar.ts)
    ).all()
    out: dict[str, list[BarRecord]] = {s: [] for s in symbols}
    for r in rows:
        ts = r.ts.replace(tzinfo=UTC) if r.ts.tzinfo is None else r.ts
        out[r.symbol].append(
            BarRecord(
                symbol=r.symbol,
                timeframe="1Day",
                ts=ts,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                vwap=r.vwap,
                trade_count=r.trade_count,
                source=r.source,
                adjustment=adjustment,  # type: ignore[arg-type]
            )
        )
    return {s: v for s, v in out.items() if v}


def run_validation(
    session: Session,
    strategy_id: str,
    *,
    policy: LoadedPolicy,
    calendar: MarketCalendar,
    default_symbols: Sequence[str],
    requested_by: str = "system",
    end: date | None = None,
) -> ValidationReport:
    rows = {r.id: r for r in sync_registry(session)}
    row = rows.get(strategy_id)
    if row is None or strategy_id not in STRATEGIES:
        raise ValidationUnavailable(f"unknown strategy {strategy_id}")
    if row.status == StrategyStatus.RETIRED:
        raise ValidationUnavailable(f"{strategy_id} is retired")
    snap = current_universe(session)
    if snap is None:
        raise ValidationUnavailable("no universe snapshot")
    members = member_symbols(session, snap)
    symbols = [s for s in ingestion_symbols(session, default_symbols) if s in members]
    if not symbols:
        raise ValidationUnavailable("no symbols in scope")
    if end is None:
        latest = session.scalar(
            select(func.max(Bar.ts)).where(
                Bar.symbol.in_(symbols), Bar.timeframe == "1Day", Bar.adjustment == "raw"
            )
        )
        if latest is None:
            raise ValidationUnavailable("no raw daily history; run atlas.scripts.backfill_history")
        latest = latest.replace(tzinfo=UTC) if latest.tzinfo is None else latest
        end = latest.astimezone(NY).date()
    bars = load_history(session, symbols, "all", end)
    raw = load_history(session, symbols, "raw", end)
    strategy = STRATEGIES[strategy_id]
    outcome = validate_strategy(strategy, policy, calendar, bars, raw, end=end)
    report = ValidationReport(
        strategy_id=outcome.strategy_id,
        version=outcome.version,
        params=outcome.params,
        params_hash=outcome.params_hash,
        target_status=StrategyStatus.PAPER.value,
        policy_sha256=policy.sha256,
        passed=outcome.passed,
        data_start=outcome.data_start,
        data_end=outcome.data_end,
        symbols=outcome.symbols,
        gates=[g.__dict__ for g in outcome.gates],
        metrics=_jsonable(outcome.metrics),
        equity_curve=[list(p) for p in outcome.equity_curve],
        caveats=outcome.caveats,
        runtime_seconds=outcome.runtime_seconds,
        requested_by=requested_by,
    )
    session.add(report)
    session.flush()
    return report


def _jsonable(v: object) -> object:
    """JSON can't hold inf/nan; record them as strings so nothing is silently dropped."""
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v
