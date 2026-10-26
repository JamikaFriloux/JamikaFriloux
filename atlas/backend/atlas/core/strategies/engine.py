"""Signal engine: run every active strategy after the close on stored daily bars.

Runs in the research worker (no broker credentials): it reads bars and the universe from the
database and writes signals. Scope is benchmarks plus watchlist symbols that are members of
the current universe snapshot. Signal ids are deterministic, so re-running for the same
session adds nothing new. RESEARCH strategies produce shadow signals; only PAPER and
LIVE_CANDIDATE strategies produce signals the executor may order (paper only), and only they
have positions to exit.
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
from atlas.core.risk.engine import PAPER_TRADING_STATUSES
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
    positions_by = {
        r.id: open_positions_for(session, r.id, as_of, calendar)
        for r in active
        if r.status in PAPER_TRADING_STATUSES
    }
    # Held symbols are always evaluated, even if they left the universe or a watchlist:
    # otherwise no exit signal could ever be generated for them.
    held = sorted({sym for pos in positions_by.values() for sym in pos} - set(scope))
    bars = load_daily_bars(session, [*scope, *held], as_of, lookback) if scope or held else {}
    summary: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "universe_as_of": snap.as_of.isoformat() if snap else None,
        "scope": len(scope),
        "held_outside_scope": held,
        "strategies": {},
    }
    for row in active:
        strat = STRATEGIES[row.id]
        paper = row.status in PAPER_TRADING_STATUSES
        positions = positions_by.get(row.id, {})
        universe_bars = {k: v for k, v in bars.items() if k in members or k in positions}
        signals, skipped = strat.generate(as_of, universe_bars, positions)
        # Entries only for universe members; exits for anything held.
        signals = [s for s in signals if s.kind == "exit" or s.symbol in members]
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
