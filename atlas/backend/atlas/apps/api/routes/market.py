"""Live market data, read from the Redis cache the executor's stream service maintains."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from atlas.apps.api.deps import require_role
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.live import LiveStore, fresh_quote
from atlas.core.models.db import Role, User

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/live")
def live_quotes(
    request: Request, _user: User = Depends(require_role(Role.VIEWER))
) -> dict[str, Any]:
    redis = request.app.state.redis
    if redis is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "live data unavailable")
    store = LiveStore(redis)
    try:
        snapshots = store.read()
        stream = store.read_status()
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "live data unavailable") from None
    now = datetime.now(UTC)
    cal = MarketCalendar()
    max_age = request.app.state.policy.policy.data_quality.max_quote_age_seconds
    quotes = []
    for symbol, snap in snapshots.items():
        q, t = snap.quote, snap.trade
        age = snap.quote_age(now)
        quotes.append(
            {
                "symbol": symbol,
                "bid": str(q.bid) if q else None,
                "ask": str(q.ask) if q else None,
                "quote_ts": q.ts.isoformat() if q else None,
                "quote_age_seconds": round(age, 3) if age is not None else None,
                "last": str(t.price) if t else None,
                "trade_ts": t.ts.isoformat() if t else None,
                # Same rule the trading engine uses: market open, recent, two-sided, uncrossed.
                "fresh": fresh_quote(snap, now=now, max_age_seconds=max_age, calendar=cal)
                is not None,
            }
        )
    return {
        "trading_mode": "PAPER",
        "server_time": now.isoformat(),
        "market_open": cal.is_open(now),
        "max_quote_age_seconds": max_age,
        "stream": stream or None,
        "quotes": quotes,
    }
