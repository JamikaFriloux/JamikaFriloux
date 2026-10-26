"""Reference data: instrument classification, earnings calendar coverage, entry clearance."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.apps.api.deps import get_db, require_role
from atlas.core.configuration.settings import RefDataSettings
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import ingestion_symbols
from atlas.core.models.db import (
    EarningsCoverage,
    EarningsEvent,
    InstrumentReference,
    Position,
    Role,
    User,
)
from atlas.core.reference.earnings import blackout_lookup, blackout_span
from atlas.core.reference.instruments import UNKNOWN_SECTOR

router = APIRouter(prefix="/api/v1", tags=["reference"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


@router.get("/reference")
def reference(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    settings, policy = request.app.state.settings, request.app.state.policy.policy
    ref = RefDataSettings()
    cal = MarketCalendar()
    now = datetime.now(UTC)
    today = now.astimezone(NY).date()
    days = policy.session.block_entries_before_earnings_days
    rows = {r.symbol: r for r in db.scalars(select(InstrumentReference)).all()}
    watched = ingestion_symbols(db, settings.ingest_default_symbols)
    lookup = blackout_lookup(
        db,
        now=now,
        today=today,
        days=days,
        calendar=cal,
        max_age=timedelta(hours=ref.earnings_max_age_hours),
    )
    span = blackout_span(today, days, cal)
    upcoming = db.scalars(
        select(EarningsEvent)
        .where(EarningsEvent.day >= today, EarningsEvent.day <= today + timedelta(days=21))
        .where(EarningsEvent.symbol.in_(watched))
        .order_by(EarningsEvent.day, EarningsEvent.symbol)
    ).all()
    cov = db.scalars(
        select(EarningsCoverage).order_by(EarningsCoverage.fetched_at.desc()).limit(1)
    ).first()
    exposure: dict[str, Decimal] = defaultdict(Decimal)
    for p in db.scalars(select(Position)).all():
        r = rows.get(p.symbol)
        exposure[(r.sector if r else None) or UNKNOWN_SECTOR] += p.market_value

    def clearance(sym: str) -> str:
        if days == 0:
            return "disabled"
        v = lookup(sym)
        return "unknown" if v is None else ("blackout" if v else "clear")

    return {
        "blackout_days": days,
        "blackout_span": [d.isoformat() for d in span],
        "earnings_max_age_hours": ref.earnings_max_age_hours,
        "latest_coverage": None
        if cov is None
        else {
            "source": cov.source,
            "fetched_at": _iso(cov.fetched_at),
            "window_start": cov.window_start.isoformat(),
            "window_end": cov.window_end.isoformat(),
            "events": cov.events,
        },
        "watched": [
            {
                "symbol": s,
                "asset_type": rows[s].asset_type if s in rows else None,
                "sector": (rows[s].sector if s in rows else None) or UNKNOWN_SECTOR,
                "source": rows[s].source if s in rows else None,
                "leveraged": rows[s].leveraged if s in rows else False,
                "earnings": clearance(s),
            }
            for s in watched
        ],
        "upcoming_earnings": [
            {"symbol": e.symbol, "day": e.day.isoformat(), "timing": e.timing, "source": e.source}
            for e in upcoming
        ],
        "sector_exposure": {k: str(v) for k, v in sorted(exposure.items())},
        "max_sector_exposure_pct": policy.limits.max_sector_exposure_pct,
    }
