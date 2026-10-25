"""Tradable universe: policy screen and immutable point-in-time snapshots.

Screen (all from ``config/policy.yaml`` instruments):
  * US equity, active, tradable at the broker, listed on a national exchange (never OTC);
  * last close >= ``min_price_usd`` on the snapshot's ``as_of`` session;
  * mean daily dollar volume (close * volume) over the last 20 sessions
    >= ``min_avg_daily_dollar_volume_usd``, with at least 15 sessions of history.

Volume must be consolidated (SIP). IEX alone is a few percent of market volume and would
understate dollar volume roughly thirtyfold, so the executor passes a SIP bar source.

Point-in-time rule: a snapshot with ``as_of = D`` uses data through D's close, so it is the
universe for trading on the *next* session. ``universe_for_session(T)`` therefore returns the
latest snapshot with ``as_of < T``; research that asks for day T never sees data from T.

A build either writes a complete snapshot or nothing. It refuses to publish when the bar
fetch fails or the result is implausibly small, leaving the previous snapshot current.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.configuration.policy import RiskPolicy
from atlas.core.data.bars import BarRecord, validate_bars
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import BarSource, last_completed_session
from atlas.core.models.db import UniverseMember, UniverseSnapshot

# SEC-registered national securities exchanges as Alpaca labels them. Anything else (OTC, or
# a label we don't recognize yet) is excluded until reviewed.
NATIONAL_EXCHANGES = ("AMEX", "ARCA", "BATS", "NASDAQ", "NYSE", "NYSEARCA", "TXSE")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
# Historical SIP bars are available on Alpaca's free plan only up to 15 minutes ago.
_SIP_DELAY = timedelta(minutes=16)


class UniverseBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    name: str
    exchange: str
    asset_class: str
    status: str
    tradable: bool
    fractionable: bool = False
    shortable: bool = False
    easy_to_borrow: bool = False


class AssetSource(Protocol):
    def list_assets(self) -> list[AssetInfo]: ...


@dataclass(frozen=True)
class UniverseCriteria:
    min_price: Decimal
    min_adv_usd: Decimal
    allow_otc: bool = False
    lookback_sessions: int = 20
    min_sessions: int = 15
    min_members: int = 50  # fewer means the inputs were incomplete; refuse to publish
    exchanges: tuple[str, ...] = NATIONAL_EXCHANGES

    @classmethod
    def from_policy(cls, policy: RiskPolicy) -> UniverseCriteria:
        inst = policy.instruments
        return cls(
            min_price=Decimal(str(inst.min_price_usd)),
            min_adv_usd=Decimal(str(inst.min_avg_daily_dollar_volume_usd)),
            allow_otc=inst.allow_otc,
        )

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(min_price=str(self.min_price), min_adv_usd=str(self.min_adv_usd))
        d["exchanges"] = list(self.exchanges)
        return d


@dataclass(frozen=True)
class MemberMetrics:
    asset: AssetInfo
    last_close: Decimal
    adv_usd: Decimal
    sessions: int


@dataclass
class ScreenResult:
    members: list[MemberMetrics] = field(default_factory=list)
    exclusions: Counter[str] = field(default_factory=Counter)


def static_exclusion(asset: AssetInfo, criteria: UniverseCriteria) -> str | None:
    """Reason an asset is ineligible before looking at prices, or None."""
    if asset.asset_class != "us_equity":
        return "not_us_equity"
    if asset.status != "active":
        return "inactive"
    if not asset.tradable:
        return "not_tradable"
    if asset.exchange == "OTC" and not criteria.allow_otc:
        return "otc"
    if asset.exchange not in criteria.exchanges:
        return "exchange_not_allowed"
    if not SYMBOL_RE.match(asset.symbol):
        return "unsupported_symbol"
    return None


def liquidity_screen(
    asset: AssetInfo,
    series: Sequence[BarRecord],
    criteria: UniverseCriteria,
    *,
    as_of: date,
    now: datetime,
) -> MemberMetrics | str:
    """Metrics if the asset passes price/liquidity rules, else the exclusion reason."""
    window = [b for b in series if b.ts.astimezone(NY).date() <= as_of]
    window = window[-criteria.lookback_sessions :]
    if not window:
        return "no_data"
    if not validate_bars(window, now=now).ok:
        return "bad_data"
    if window[-1].ts.astimezone(NY).date() != as_of:
        return "no_trade_on_as_of"  # halted, delisting, or no prints that day
    if len(window) < criteria.min_sessions:
        return "insufficient_history"
    last_close = window[-1].close
    if last_close < criteria.min_price:
        return "price_below_min"
    adv = sum((b.close * b.volume for b in window), Decimal(0)) / len(window)
    if adv < criteria.min_adv_usd:
        return "adv_below_min"
    return MemberMetrics(asset, last_close, adv.quantize(Decimal("0.01")), len(window))


def _window_start(calendar: MarketCalendar, as_of: date, sessions: int) -> datetime:
    days = calendar.sessions_between(as_of - timedelta(days=sessions * 2 + 15), as_of)
    first = days[-sessions] if len(days) >= sessions else days[0]
    return datetime(first.year, first.month, first.day, tzinfo=NY)


def build_universe_snapshot(
    session: Session,
    assets_source: AssetSource,
    bar_source: BarSource,
    criteria: UniverseCriteria,
    *,
    now: datetime,
    calendar: MarketCalendar | None = None,
    batch_size: int = 500,
    force: bool = False,
) -> tuple[UniverseSnapshot, bool]:
    """Build and store a snapshot. Returns (snapshot, created).

    Idempotent: an existing snapshot for the same ``as_of`` and criteria is returned as-is
    unless ``force``.
    """
    cal = calendar or MarketCalendar()
    as_of = last_completed_session(cal, now).day
    criteria_dict = criteria.as_dict()
    if not force:
        existing = session.scalars(
            select(UniverseSnapshot)
            .where(UniverseSnapshot.as_of == as_of)
            .order_by(UniverseSnapshot.id.desc())
        ).all()
        for snap in existing:
            if snap.criteria == criteria_dict:
                return snap, False

    try:
        assets = assets_source.list_assets()
    except Exception as exc:
        raise UniverseBuildError(f"asset list unavailable: {type(exc).__name__}") from exc
    by_symbol = {a.symbol: a for a in assets}  # the broker can list a symbol twice
    result = ScreenResult()
    candidates = []
    for asset in by_symbol.values():
        reason = static_exclusion(asset, criteria)
        if reason:
            result.exclusions[reason] += 1
        else:
            candidates.append(asset)

    start = _window_start(cal, as_of, criteria.lookback_sessions)
    end = now - _SIP_DELAY
    symbols = sorted(a.symbol for a in candidates)
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            bars = bar_source.get_bars(batch, "1Day", start, end, "raw")
        except Exception as exc:
            raise UniverseBuildError(f"bar fetch failed: {type(exc).__name__}") from exc
        for sym in batch:
            outcome = liquidity_screen(
                by_symbol[sym], bars.get(sym, []), criteria, as_of=as_of, now=now
            )
            if isinstance(outcome, str):
                result.exclusions[outcome] += 1
            else:
                result.members.append(outcome)

    if len(result.members) < criteria.min_members:
        raise UniverseBuildError(
            f"only {len(result.members)} members (minimum {criteria.min_members}); "
            "inputs look incomplete, not publishing"
        )

    snap = UniverseSnapshot(
        as_of=as_of,
        created_at=now,
        source=bar_source.source,
        criteria=criteria_dict,
        assets_seen=len(by_symbol),
        member_count=len(result.members),
        exclusions=dict(sorted(result.exclusions.items())),
    )
    session.add(snap)
    session.flush()
    session.add_all(
        UniverseMember(
            snapshot_id=snap.id,
            symbol=m.asset.symbol,
            name=m.asset.name[:255],
            exchange=m.asset.exchange,
            last_close=m.last_close,
            adv_usd=m.adv_usd,
            sessions=m.sessions,
            fractionable=m.asset.fractionable,
            shortable=m.asset.shortable,
            easy_to_borrow=m.asset.easy_to_borrow,
        )
        for m in result.members
    )
    session.flush()
    return snap, True


def current_universe(session: Session) -> UniverseSnapshot | None:
    return session.scalars(
        select(UniverseSnapshot)
        .order_by(UniverseSnapshot.as_of.desc(), UniverseSnapshot.id.desc())
        .limit(1)
    ).first()


def universe_for_session(session: Session, trading_day: date) -> UniverseSnapshot | None:
    """The universe known before ``trading_day`` opened (no lookahead)."""
    return session.scalars(
        select(UniverseSnapshot)
        .where(UniverseSnapshot.as_of < trading_day)
        .order_by(UniverseSnapshot.as_of.desc(), UniverseSnapshot.id.desc())
        .limit(1)
    ).first()


def member_symbols(session: Session, snapshot: UniverseSnapshot) -> set[str]:
    return set(
        session.scalars(
            select(UniverseMember.symbol).where(UniverseMember.snapshot_id == snapshot.id)
        ).all()
    )


def is_stale(snapshot: UniverseSnapshot, now: datetime, calendar: MarketCalendar) -> bool:
    """True when a newer completed session exists than the snapshot's data."""
    return snapshot.as_of < last_completed_session(calendar, now).day
