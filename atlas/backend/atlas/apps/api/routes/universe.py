"""Universe snapshots (read-only) and watchlist management."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from atlas.apps.api.deps import client_ip, get_db, require_role
from atlas.core.data import watchlists as wl
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.universe import current_universe, is_stale
from atlas.core.models.db import Role, UniverseMember, User

router = APIRouter(prefix="/api/v1", tags=["universe"])


@router.get("/universe")
def get_universe(
    q: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    """Latest snapshot summary plus members by dollar volume (searchable by symbol/name)."""
    snap = current_universe(db)
    if snap is None:
        return {"snapshot": None, "members": [], "total": 0}
    query = select(UniverseMember).where(UniverseMember.snapshot_id == snap.id)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(UniverseMember.symbol.ilike(pattern), UniverseMember.name.ilike(pattern))
        )
    rows = db.scalars(
        query.order_by(UniverseMember.adv_usd.desc(), UniverseMember.symbol)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "snapshot": {
            "id": snap.id,
            "as_of": snap.as_of.isoformat(),
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
            "stale": is_stale(snap, datetime.now(UTC), MarketCalendar()),
            "source": snap.source,
            "criteria": snap.criteria,
            "assets_seen": snap.assets_seen,
            "member_count": snap.member_count,
            "exclusions": snap.exclusions,
        },
        "total": snap.member_count if not q else None,
        "members": [
            {
                "symbol": m.symbol,
                "name": m.name,
                "exchange": m.exchange,
                "last_close": str(m.last_close),
                "adv_usd": str(m.adv_usd),
                "sessions": m.sessions,
                "fractionable": m.fractionable,
            }
            for m in rows
        ],
    }


class WatchlistBody(BaseModel):
    symbols: list[str] = Field(max_length=wl.MAX_SYMBOLS_PER_LIST * 2)


class NewWatchlistBody(WatchlistBody):
    name: str = Field(min_length=1, max_length=64)


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, wl.SymbolsRejected):
        raise HTTPException(
            422,  # Unprocessable Content (constant name differs across Starlette versions)
            {"message": str(exc), "rejected": exc.rejected},
        ) from None
    if isinstance(exc, wl.UniverseUnavailable):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    if isinstance(exc, LookupError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watchlist not found") from None
    if isinstance(exc, wl.WatchlistError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    raise exc


@router.get("/watchlists")
def list_watchlists(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict[str, Any]:
    view = wl.watchlists_view(db)
    settings = request.app.state.settings
    unique = {s["symbol"] for w in view["watchlists"] for s in w["symbols"]}
    benchmarks = [s.upper() for s in settings.ingest_default_symbols]
    unique |= set(benchmarks)
    view["benchmarks"] = benchmarks
    # The stream carries at most stream_max_symbols; the rest still get REST bars.
    view["stream"] = {"symbols": len(unique), "capacity": settings.stream_max_symbols}
    return view


@router.post("/watchlists", status_code=status.HTTP_201_CREATED)
def create_watchlist(
    body: NewWatchlistBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.OPERATOR)),
) -> dict[str, Any]:
    try:
        w = wl.save_watchlist(
            db, body.name, body.symbols, actor=user.username, ip_address=client_ip(request),
            create=True,
        )  # fmt: skip
    except (wl.WatchlistError, LookupError) as exc:
        _raise(exc)
    db.commit()
    return {"name": w.name, "symbols": w.symbols}


@router.put("/watchlists/{name}")
def replace_watchlist(
    name: str,
    body: WatchlistBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.OPERATOR)),
) -> dict[str, Any]:
    try:
        w = wl.save_watchlist(
            db, name, body.symbols, actor=user.username, ip_address=client_ip(request),
            create=False,
        )  # fmt: skip
    except (wl.WatchlistError, LookupError) as exc:
        _raise(exc)
    db.commit()
    return {"name": w.name, "symbols": w.symbols}


@router.delete("/watchlists/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watchlist(
    name: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.OPERATOR)),
) -> None:
    if not wl.delete_watchlist(db, name, actor=user.username, ip_address=client_ip(request)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watchlist not found")
    db.commit()
