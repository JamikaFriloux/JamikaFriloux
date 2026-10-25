"""Watchlist management.

Watchlists choose which symbols get minute bars and live quotes (benchmarks are always
included). A symbol can be added only if it is a member of the current universe snapshot;
with no snapshot nothing can be added (fail closed). Symbols that later leave the universe
stay on the list but are reported as ``in_universe: false``; trading must check membership
itself rather than trust a watchlist. Every change is written to the audit log.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.data.universe import SYMBOL_RE, current_universe, member_symbols
from atlas.core.models.db import Watchlist
from atlas.core.security import audit

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_SYMBOLS_PER_LIST = 100


class WatchlistError(ValueError):
    pass


class UniverseUnavailable(WatchlistError):
    pass


class SymbolsRejected(WatchlistError):
    def __init__(self, rejected: dict[str, str]):
        super().__init__(f"{len(rejected)} symbol(s) rejected")
        self.rejected = rejected


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    """Upper-case, strip and de-duplicate (order kept). Raises on malformed symbols."""
    out: list[str] = []
    bad: dict[str, str] = {}
    for raw in symbols:
        s = str(raw).strip().upper()
        if not SYMBOL_RE.match(s):
            bad[str(raw)[:20]] = "malformed symbol"
        elif s not in out:
            out.append(s)
    if bad:
        raise SymbolsRejected(bad)
    if len(out) > MAX_SYMBOLS_PER_LIST:
        raise WatchlistError(f"at most {MAX_SYMBOLS_PER_LIST} symbols per watchlist")
    return out


def _check_universe(session: Session, symbols: list[str]) -> None:
    snap = current_universe(session)
    if snap is None:
        raise UniverseUnavailable("no universe snapshot yet; run the universe refresh first")
    members = member_symbols(session, snap)
    rejected = {
        s: f"not in universe snapshot of {snap.as_of.isoformat()}"
        for s in symbols
        if s not in members
    }
    if rejected:
        raise SymbolsRejected(rejected)


def get_watchlist(session: Session, name: str) -> Watchlist | None:
    return session.scalars(select(Watchlist).where(Watchlist.name == name)).first()


def save_watchlist(
    session: Session,
    name: str,
    symbols: Iterable[str],
    *,
    actor: str,
    ip_address: str | None = None,
    create: bool,
) -> Watchlist:
    """Create (``create=True``) or replace the symbols of a watchlist."""
    if not NAME_RE.match(name):
        raise WatchlistError("name must be 1-64 chars of a-z, 0-9, '_' or '-'")
    clean = normalize_symbols(symbols)
    wl = get_watchlist(session, name)
    if create and wl is not None:
        raise WatchlistError(f"watchlist {name!r} already exists")
    if not create and wl is None:
        raise LookupError(name)
    before = list(wl.symbols) if wl else []
    # Only additions must be in the universe; keeping a symbol that has since dropped out
    # is allowed so an edit elsewhere in the list doesn't force its removal.
    _check_universe(session, [s for s in clean if s not in before])
    if wl is None:
        wl = Watchlist(name=name, symbols=clean)
        session.add(wl)
    else:
        wl.symbols = clean
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="watchlist.create" if create else "watchlist.update",
        target=name,
        details={
            "added": [s for s in clean if s not in before],
            "removed": [s for s in before if s not in clean],
        },
        ip_address=ip_address,
    )
    return wl


def delete_watchlist(
    session: Session, name: str, *, actor: str, ip_address: str | None = None
) -> bool:
    wl = get_watchlist(session, name)
    if wl is None:
        return False
    audit.record(
        session,
        actor=actor,
        action="watchlist.delete",
        target=name,
        details={"symbols": list(wl.symbols)},
        ip_address=ip_address,
    )
    session.delete(wl)
    session.flush()
    return True


def watchlists_view(session: Session) -> dict[str, Any]:
    snap = current_universe(session)
    members = member_symbols(session, snap) if snap else set()
    lists = session.scalars(select(Watchlist).order_by(Watchlist.name)).all()
    return {
        "universe_as_of": snap.as_of.isoformat() if snap else None,
        "watchlists": [
            {
                "name": wl.name,
                "updated_at": wl.updated_at.isoformat() if wl.updated_at else None,
                "symbols": [
                    {"symbol": s, "in_universe": (s in members) if snap else None}
                    for s in wl.symbols
                ],
            }
            for wl in lists
        ],
    }
