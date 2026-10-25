from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.data import watchlists as wl
from atlas.core.models.db import AuditLog, UniverseMember, UniverseSnapshot


def seed_universe(db, symbols, as_of=date(2026, 10, 23)):
    snap = UniverseSnapshot(as_of=as_of, source="fake", criteria={}, assets_seen=len(symbols),
                            member_count=len(symbols), exclusions={})  # fmt: skip
    db.add(snap)
    db.flush()
    db.add_all(
        UniverseMember(
            snapshot_id=snap.id,
            symbol=s,
            name=s,
            exchange="NYSE",
            last_close=Decimal(50),
            adv_usd=Decimal("1e8"),
            sessions=20,
            fractionable=True,
            shortable=False,
            easy_to_borrow=False,
        )
        for s in symbols
    )
    db.flush()
    return snap


def save(db, name, symbols, create=True):
    return wl.save_watchlist(db, name, symbols, actor="op", create=create)


def test_normalize_symbols():
    assert wl.normalize_symbols([" aapl", "MSFT", "AAPL", "brk.b"]) == ["AAPL", "MSFT", "BRK.B"]
    with pytest.raises(wl.SymbolsRejected) as exc:
        wl.normalize_symbols(["AAPL", "not a symbol", "$$$"])
    assert set(exc.value.rejected) == {"not a symbol", "$$$"}
    with pytest.raises(wl.WatchlistError):
        wl.normalize_symbols([f"A{i}" for i in range(101)])


def test_no_universe_means_no_additions(db):
    with pytest.raises(wl.UniverseUnavailable):
        save(db, "core", ["AAPL"])


def test_symbols_outside_universe_rejected(db):
    seed_universe(db, ["AAPL", "MSFT"])
    with pytest.raises(wl.SymbolsRejected) as exc:
        save(db, "core", ["AAPL", "PENNY"])
    assert exc.value.rejected == {"PENNY": "not in universe snapshot of 2026-10-23"}
    assert wl.get_watchlist(db, "core") is None


def test_create_update_delete_with_audit(db):
    seed_universe(db, ["AAPL", "MSFT", "NVDA"])
    save(db, "core", ["aapl", "MSFT"])
    with pytest.raises(wl.WatchlistError, match="already exists"):
        save(db, "core", ["AAPL"])
    save(db, "core", ["MSFT", "NVDA"], create=False)
    assert wl.get_watchlist(db, "core").symbols == ["MSFT", "NVDA"]
    with pytest.raises(LookupError):
        save(db, "missing", ["AAPL"], create=False)
    with pytest.raises(wl.WatchlistError, match="name"):
        save(db, "Bad Name!", ["AAPL"])
    assert wl.delete_watchlist(db, "core", actor="op") is True
    assert wl.delete_watchlist(db, "core", actor="op") is False
    entries = db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    assert [(e.action, e.details) for e in entries] == [
        ("watchlist.create", {"added": ["AAPL", "MSFT"], "removed": []}),
        ("watchlist.update", {"added": ["NVDA"], "removed": ["AAPL"]}),
        ("watchlist.delete", {"symbols": ["MSFT", "NVDA"]}),
    ]


def test_symbol_that_left_universe_can_stay_but_is_flagged(db):
    seed_universe(db, ["AAPL", "MSFT"], as_of=date(2026, 10, 22))
    save(db, "core", ["AAPL", "MSFT"])
    seed_universe(db, ["AAPL", "NVDA"], as_of=date(2026, 10, 23))  # MSFT dropped out
    save(db, "core", ["AAPL", "MSFT", "NVDA"], create=False)  # keeping MSFT is allowed
    with pytest.raises(wl.SymbolsRejected):
        save(db, "other", ["MSFT"])  # but it can't be newly added
    view = wl.watchlists_view(db)
    assert view["universe_as_of"] == "2026-10-23"
    flags = {s["symbol"]: s["in_universe"] for s in view["watchlists"][0]["symbols"]}
    assert flags == {"AAPL": True, "MSFT": False, "NVDA": True}
