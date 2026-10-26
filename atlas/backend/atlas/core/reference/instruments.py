"""``config/instruments.yaml``: reviewed classification of ETFs and stock sectors."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.models.db import InstrumentReference

SYMBOL = r"^[A-Z][A-Z0-9.]{0,9}$"
UNKNOWN_SECTOR = "unknown"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EtfEntry(_Strict):
    sector: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    leveraged: bool = False


class StockEntry(_Strict):
    sector: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=255)


class InstrumentsFile(_Strict):
    version: int
    etfs: dict[str, EtfEntry] = Field(default_factory=dict)
    stocks: dict[str, StockEntry] = Field(default_factory=dict)

    @field_validator("etfs", "stocks")
    @classmethod
    def _symbols(cls, v: Mapping[str, object]) -> Mapping[str, object]:
        import re

        bad = [s for s in v if not re.match(SYMBOL, s)]
        if bad:
            raise ValueError(f"invalid symbols: {bad}")
        return v

    @model_validator(mode="after")
    def _disjoint(self) -> InstrumentsFile:
        both = set(self.etfs) & set(self.stocks)
        if both:
            raise ValueError(f"listed as both ETF and stock: {sorted(both)}")
        sectors = {e.sector for e in self.etfs.values()} | {e.sector for e in self.stocks.values()}
        if UNKNOWN_SECTOR in sectors:
            raise ValueError(f"'{UNKNOWN_SECTOR}' is reserved for unclassified symbols")
        return self


class LoadedInstruments(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: InstrumentsFile
    path: str
    sha256: str


def instruments_path(policy_path: Path) -> Path:
    return policy_path.parent / "instruments.yaml"


def load_instruments(path: str | Path) -> LoadedInstruments:
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return LoadedInstruments(
        data=InstrumentsFile.model_validate(data),
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def apply_config(session: Session, loaded: LoadedInstruments, now: datetime | None = None) -> int:
    """Upsert every configured symbol (source ``config``) and remove config rows that are no
    longer listed. Provider rows are left alone unless the config now covers the symbol."""
    now = now or datetime.now(UTC)
    rows = {r.symbol: r for r in session.scalars(select(InstrumentReference)).all()}
    wanted: dict[str, tuple[str, str, str | None, bool]] = {
        s: ("etf", e.sector, e.name, e.leveraged) for s, e in loaded.data.etfs.items()
    }
    wanted.update({s: ("stock", e.sector, e.name, False) for s, e in loaded.data.stocks.items()})
    changed = 0
    for sym, (kind, sector, name, lev) in wanted.items():
        row = rows.get(sym)
        if row is None:
            row = InstrumentReference(symbol=sym)
            session.add(row)
        elif (row.asset_type, row.sector, row.name, row.leveraged, row.source) == (
            kind,
            sector,
            name or row.name,
            lev,
            "config",
        ):
            continue
        row.asset_type, row.sector, row.leveraged, row.source = kind, sector, lev, "config"
        row.name = name or row.name
        row.updated_at = now
        changed += 1
    for sym, row in rows.items():
        if row.source == "config" and sym not in wanted:
            session.delete(row)
            changed += 1
    session.flush()
    return changed


def sector_buckets(session: Session) -> dict[str, str]:
    """symbol -> sector bucket for every classified symbol (others are ``unknown``)."""
    return {
        r.symbol: r.sector or UNKNOWN_SECTOR
        for r in session.scalars(select(InstrumentReference)).all()
    }
