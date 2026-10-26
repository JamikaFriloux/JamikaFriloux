"""Signal engine: run every active strategy after the close on stored daily bars.

Runs in the research worker (no broker credentials): it reads bars and the universe from the
database and writes signals. Scope is benchmarks plus watchlist symbols that are members of
the current universe snapshot. Signal ids are deterministic, so re-running for the same
session adds nothing new. RESEARCH strategies produce shadow signals; only PAPER strategies
produce signals the executor may order, and only PAPER strategies have positions to exit.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import ingestion_symbols
from atlas.core.data.universe import current_universe, member_symbols
from atlas.core.execution.positions import open_positions_for
from atlas.core.models.db import Bar, SignalRecord, StrategyStatus
from atlas.core.strategies.registry import STRATEGIES, sync_registry


def load_daily_bars(
    session: Session, symbols: Sequence[str], as_of: date, sessions: int
) -> dict[str, list[BarRecord]]:
    start = datetime.combine(
        as_of - timedelta(days=int(sessions * 1.6) + 10), datetime.min.time(), NY
    )
    end = datetime.combine(as_of + timedelta(days=1), datetime.min.time(), NY)
    rows = session.scalars(
        select(Bar)
        .where(
            Bar.symbol.in_(symbols),
            Bar.timeframe == "1Day",
            Bar.adjustment == "all",
            Bar.ts >= start,
            Bar.ts < end,
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
                adjustment="all",
            )
        )
    return out


def generate_signals(
    session: Session, *, as_of: date, default_symbols: Sequence[str], calendar: MarketCalendar
) -> dict[str, Any]:
    rows = sync_registry(session)
    snap = current_universe(session)
    members = member_symbols(session, snap) if snap else set()
    scope = [s for s in ingestion_symbols(session, default_symbols) if s in members]
    active = [r for r in rows if r.status != StrategyStatus.RETIRED and r.id in STRATEGIES]
    lookback = max((STRATEGIES[r.id].lookback for r in active), default=0)
    bars = load_daily_bars(session, scope, as_of, lookback) if scope else {}
    summary: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "universe_as_of": snap.as_of.isoformat() if snap else None,
        "scope": len(scope),
        "strategies": {},
    }
    for row in active:
        strat = STRATEGIES[row.id]
        paper = row.status == StrategyStatus.PAPER
        positions = open_positions_for(session, row.id, as_of, calendar) if paper else {}
        signals, skipped = strat.generate(as_of, bars, positions)
        created = 0
        for sig in signals:
            if session.get(SignalRecord, sig.id) is not None:
                continue
            session.add(
                SignalRecord(
                    id=sig.id,
                    strategy_id=sig.strategy_id,
                    strategy_version=sig.strategy_version,
                    symbol=sig.symbol,
                    kind=sig.kind,
                    side=sig.side,
                    as_of=sig.as_of,
                    ref_price=sig.ref_price,
                    stop_price=sig.stop_price,
                    reason=dict(sig.reason),
                    mode="paper" if paper else "shadow",
                    status="NEW",
                )
            )
            created += 1
        summary["strategies"][row.id] = {
            "status": row.status.value,
            "signals": len(signals),
            "new": created,
            "skipped": skipped,
        }
    session.flush()
    return summary
