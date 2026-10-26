"""Performance Analysis: a daily digest of account, strategy and risk-engine activity.

Everything is read from ATLAS's own records (broker snapshots, equity closes, signals, risk
decisions, orders, validation reports). Money stays Decimal and is serialised as strings.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.agents.base import AgentInput, AgentSpec, Narrative
from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import last_completed_session
from atlas.core.models.db import (
    AccountSnapshot,
    EquityClose,
    Order,
    Position,
    RiskDecision,
    SignalRecord,
    StrategyRecord,
    ValidationReport,
)
from atlas.core.risk.drawdown import at_session, limit_dollars, production_state

SESSIONS = 5  # activity window
CLOSES = 20  # equity-curve window

SPEC: AgentSpec[Narrative] = AgentSpec(
    name="performance_analysis",
    prompt_version="pa-1",
    system=(
        "You write the daily performance digest of a paper-trading system for its operator. "
        "Explain what happened (account, strategies, signals, risk-engine rejections and why) "
        "and what is blocking activity, using only the given records. Paper results are not "
        "evidence of future profitability; say so when it matters."
    ),
    schema=Narrative,
)


def _window_start(calendar: MarketCalendar, now: datetime) -> datetime:
    last = last_completed_session(calendar, now).day
    days = calendar.sessions_between(last - timedelta(days=14), last)
    first = days[-SESSIONS] if len(days) >= SESSIONS else days[0]
    s = calendar.session(first)
    assert s is not None
    return s.open


def gather(
    session: Session, *, now: datetime, calendar: MarketCalendar, policy: RiskPolicy
) -> AgentInput:
    as_of = last_completed_session(calendar, now).day
    since = _window_start(calendar, now)
    snap = session.scalars(
        select(AccountSnapshot).order_by(AccountSnapshot.ts.desc()).limit(1)
    ).first()
    account: dict[str, Any] | None = None
    if snap is not None:
        today = now.astimezone(NY).date()
        state = production_state(session, today, policy, calendar)
        hwm, left = at_session(state, today, snap.equity, policy, calendar)
        account = {
            "equity": snap.equity,
            "cash": snap.cash,
            "long_market_value": snap.long_market_value,
            "day_pl": snap.equity - snap.last_equity,
            "capital_base": min(snap.equity, Decimal(str(policy.account.starting_equity_usd))),
            "high_water_mark": hwm,
            "drawdown": hwm - snap.equity,
            "drawdown_limit": limit_dollars(hwm, policy),
            "drawdown_cooldown_sessions_remaining": left,
            "shorting_enabled": snap.shorting_enabled,
            "snapshot_at": snap.ts,
        }
    closes = session.execute(
        select(EquityClose.day, EquityClose.equity).order_by(EquityClose.day.desc()).limit(CLOSES)
    ).all()[::-1]
    curve: dict[str, Any] = {"sessions": len(closes)}
    if len(closes) >= 2:
        first, last = closes[0][1], closes[-1][1]
        peak, worst = first, Decimal(0)
        for _, eq in closes:
            peak = max(peak, eq)
            worst = max(worst, peak - eq)
        curve.update(
            start=closes[0][0],
            end=closes[-1][0],
            change=last - first,
            change_pct=round(float(100 * (last / first - 1)), 2) if first else None,
            max_drawdown=worst,
        )

    signals = session.scalars(select(SignalRecord).where(SignalRecord.created_at >= since)).all()
    decisions = session.scalars(select(RiskDecision).where(RiskDecision.ts >= since)).all()
    orders = session.scalars(select(Order).where(Order.created_at >= since)).all()
    failed: Counter[str] = Counter()
    for d in decisions:
        if not d.approved:
            failed.update(d.failed or [])
    positions = session.scalars(select(Position)).all()

    strategies = []
    for st in session.scalars(select(StrategyRecord).order_by(StrategyRecord.id)).all():
        rep = session.scalars(
            select(ValidationReport)
            .where(ValidationReport.strategy_id == st.id)
            .order_by(ValidationReport.created_at.desc())
            .limit(1)
        ).first()
        strategies.append(
            {
                "id": st.id,
                "version": st.version,
                "status": st.status.value,
                "latest_validation": None
                if rep is None
                else {"id": rep.id, "passed": rep.passed, "created_at": rep.created_at},
            }
        )

    features = {
        "as_of": as_of,
        "activity_since": since,
        "account": account,
        "equity_curve": curve,
        "strategies": strategies,
        "signals": {
            "total": len(signals),
            "by_status": dict(Counter(s.status for s in signals)),
            "by_mode": dict(Counter(s.mode for s in signals)),
        },
        "risk_decisions": {
            "total": len(decisions),
            "approved": sum(d.approved for d in decisions),
            "rejected": sum(not d.approved for d in decisions),
            "top_failed_checks": dict(failed.most_common(8)),
        },
        "orders": {
            "total": len(orders),
            "by_state": dict(Counter(o.state.value for o in orders)),
            "by_purpose": dict(Counter(o.purpose for o in orders)),
        },
        "positions": {
            "count": len(positions),
            "unrealized_pl": sum((p.unrealized_pl for p in positions), Decimal(0)),
        },
    }
    return AgentInput("account", as_of, features, has_data=snap is not None or bool(signals))
