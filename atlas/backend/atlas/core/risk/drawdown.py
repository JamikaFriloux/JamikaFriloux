"""Drawdown halt with a cooldown and reset (``policy.yaml`` ``limits``).

Rule, evaluated on session-close equity:
  * the high-water mark (HWM) is the highest close since the last reset;
  * a close at least ``limit_dollars`` below the HWM halts new entries;
  * entries stay blocked for the next ``drawdown_cooldown_sessions`` sessions;
  * at the close of the last cooldown session the HWM resets to that close, and drawdown is
    measured from there (a new breach starts a new cooldown).

Intraday, the risk engine also blocks entries whenever live equity is past the limit, but
only a breach at the close starts a cooldown. Exits are never blocked by any of this.

The same ``step`` runs in production (replayed over recorded session closes) and in the
backtester (once per simulated close), so both apply exactly the same rule.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import AccountSnapshot, EquityClose


@dataclass(frozen=True)
class DrawdownState:
    peak: Decimal | None = None
    halted_on: date | None = None  # session whose close breached the limit


def limit_dollars(peak: Decimal, policy: RiskPolicy) -> Decimal:
    """Allowed drawdown in dollars: a % of the peak, capped at the policy budget."""
    base = min(peak, Decimal(str(policy.account.starting_equity_usd)))
    return base * Decimal(str(policy.limits.max_drawdown_pct)) / 100


def _sessions_after(calendar: MarketCalendar, start: date, end: date) -> int:
    """Completed sessions strictly after ``start`` up to and including ``end``."""
    if end <= start:
        return 0
    return sum(1 for d in calendar.sessions_between(start, end) if d > start)


def step(
    state: DrawdownState, day: date, equity: Decimal, policy: RiskPolicy, calendar: MarketCalendar
) -> DrawdownState:
    """Advance the rule by one session close."""
    cooldown = policy.limits.drawdown_cooldown_sessions
    if state.halted_on is not None:
        if _sessions_after(calendar, state.halted_on, day) >= cooldown:
            return DrawdownState(peak=equity, halted_on=None)  # reset at this close
        return state
    peak = equity if state.peak is None else max(state.peak, equity)
    if peak - equity >= limit_dollars(peak, policy):
        return DrawdownState(peak=peak, halted_on=day)
    return DrawdownState(peak=peak, halted_on=None)


def replay(
    closes: Iterable[tuple[date, Decimal]], policy: RiskPolicy, calendar: MarketCalendar
) -> DrawdownState:
    state = DrawdownState()
    for day, equity in closes:
        state = step(state, day, equity, policy, calendar)
    return state


def at_session(
    state: DrawdownState,
    today: date,
    live_equity: Decimal,
    policy: RiskPolicy,
    calendar: MarketCalendar,
) -> tuple[Decimal, int]:
    """(HWM to measure against, cooldown sessions remaining) for a session not yet closed.

    If the cooldown has run out but the reset close was never recorded (e.g. the executor
    was down), the HWM resets to live equity rather than staying stuck on the old peak.
    """
    if state.halted_on is None:
        return max(state.peak or live_equity, live_equity), 0
    elapsed = _sessions_after(calendar, state.halted_on, today) - (
        1 if calendar.is_trading_day(today) and today > state.halted_on else 0
    )
    remaining = policy.limits.drawdown_cooldown_sessions - elapsed
    if remaining <= 0:
        return live_equity, 0
    assert state.peak is not None
    return state.peak, remaining


def record_equity_close(session: Session, calendar: MarketCalendar) -> EquityClose | None:
    """Upsert today's session-close equity from the latest broker snapshot.

    Called after every broker sync; the row is overwritten until the session ends, so the
    last snapshot of the day is what remains.
    """
    snap = session.scalars(
        select(AccountSnapshot).order_by(AccountSnapshot.ts.desc()).limit(1)
    ).first()
    if snap is None:
        return None
    ts = snap.ts.replace(tzinfo=UTC) if snap.ts.tzinfo is None else snap.ts
    s = calendar.session(ts.astimezone(NY).date())
    if s is None or ts < s.open:
        return None  # no session today, or before the open: nothing to record
    row = session.get(EquityClose, s.day)
    if row is None:
        row = EquityClose(day=s.day, equity=snap.equity, recorded_at=ts)
        session.add(row)
    else:
        prev = (
            row.recorded_at.replace(tzinfo=UTC)
            if row.recorded_at.tzinfo is None
            else row.recorded_at
        )
        # Keep updating through the close; the first snapshot after it is final.
        if ts > prev and (ts <= s.close or prev <= s.close):
            row.equity, row.recorded_at = snap.equity, ts
    return row


def production_state(
    session: Session, today: date, policy: RiskPolicy, calendar: MarketCalendar
) -> DrawdownState:
    """Replay recorded closes before ``today``."""
    rows = session.execute(
        select(EquityClose.day, EquityClose.equity)
        .where(EquityClose.day < today)
        .order_by(EquityClose.day)
    ).all()
    return replay(((d, e) for d, e in rows), policy, calendar)
