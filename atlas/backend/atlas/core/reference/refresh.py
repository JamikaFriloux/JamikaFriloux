"""Refresh reference data (executor). Config always applies; providers are optional.

Order: config/instruments.yaml (reviewed, wins), then SEC EDGAR for still-unclassified
watched symbols, then the earnings calendar. A provider failure keeps whatever was stored
before and is reported; it never deletes data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.data.calendar import NY
from atlas.core.models.db import InstrumentReference
from atlas.core.reference.earnings import EarningsItem, store_calendar
from atlas.core.reference.instruments import LoadedInstruments, apply_config


class CompanySource(Protocol):
    def companies(self, symbols: Sequence[str]) -> Sequence[Any]: ...


class EarningsSource(Protocol):
    source: str

    def calendar(self, start: Any, end: Any, symbols: Sequence[str]) -> list[EarningsItem]: ...


def classify_from_provider(
    session: Session, source: CompanySource, symbols: Sequence[str], now: datetime
) -> int:
    known = set(session.scalars(select(InstrumentReference.symbol)).all())
    todo = [s for s in symbols if s not in known]
    if not todo:
        return 0
    added = 0
    for c in source.companies(todo):
        if c.sector is None:
            continue  # an SIC code we can't map is still unknown
        session.add(
            InstrumentReference(
                symbol=c.symbol,
                asset_type="stock",
                sector=c.sector,
                name=c.name or None,
                sic=c.sic,
                source="sec_edgar",
                updated_at=now,
            )
        )
        added += 1
    session.flush()
    return added


def refresh_reference(
    session: Session,
    *,
    instruments: LoadedInstruments,
    symbols: Sequence[str],
    now: datetime,
    companies: CompanySource | None,
    earnings: EarningsSource | None,
    horizon_days: int,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "instruments_sha256": instruments.sha256[:12],
        "config_changes": apply_config(session, instruments, now),
        "errors": {},
    }
    if companies is None:
        summary["sec_edgar"] = "not configured"
    else:
        try:
            with session.begin_nested():
                summary["sec_edgar"] = classify_from_provider(session, companies, symbols, now)
        except Exception as exc:
            summary["errors"]["sec_edgar"] = str(exc)[:200] or type(exc).__name__
    if earnings is None:
        summary["earnings"] = "not configured"
    else:
        start = now.astimezone(NY).date()
        end = start + timedelta(days=horizon_days)
        try:
            # Watched stocks are also queried by symbol: the market-wide calendar can omit
            # a share class (see integrations/finnhub/earnings.py).
            stocks = sorted(set(symbols) - set(instruments.data.etfs))
            items = earnings.calendar(start, end, stocks)
            with session.begin_nested():
                cov = store_calendar(
                    session, earnings.source, items, window_start=start, window_end=end, now=now
                )
            summary["earnings"] = {"events": cov.events, "window": [str(start), str(end)]}
        except Exception as exc:
            summary["errors"]["earnings"] = str(exc)[:200] or type(exc).__name__
    unclassified = sorted(
        set(symbols) - set(session.scalars(select(InstrumentReference.symbol)).all())
    )
    summary["unclassified"] = unclassified
    return summary
