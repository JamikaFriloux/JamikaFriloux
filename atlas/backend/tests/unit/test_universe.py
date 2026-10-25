from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.universe import (
    UniverseBuildError,
    UniverseCriteria,
    build_universe_snapshot,
    current_universe,
    is_stale,
    liquidity_screen,
    member_symbols,
    static_exclusion,
    universe_for_session,
)
from atlas.core.models.db import UniverseMember, UniverseSnapshot
from tests.fakes import FakeAssetSource, FakeBarSource, daily_series, make_asset

CAL = MarketCalendar()
NOW = datetime(2026, 10, 23, 20, 0, tzinfo=NY)  # Friday evening
AS_OF = date(2026, 10, 23)
SESSIONS = CAL.sessions_between(date(2026, 9, 1), AS_OF)[-20:]
CRIT = UniverseCriteria(min_price=Decimal(10), min_adv_usd=Decimal(20_000_000), min_members=2)


class RecordingBars(FakeBarSource):
    def get_bars(self, symbols, timeframe, start, end, adjustment="all"):
        self.adjustments = [*getattr(self, "adjustments", []), adjustment]
        return super().get_bars(symbols, timeframe, start, end, adjustment)


def test_criteria_from_policy(policy):
    c = UniverseCriteria.from_policy(policy.policy)
    assert c.min_price == Decimal("10.0") and c.min_adv_usd == Decimal("20000000")
    assert c.allow_otc is False and "OTC" not in c.exchanges


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"exchange": "OTC"}, "otc"),
        ({"exchange": "XYZ"}, "exchange_not_allowed"),
        ({"tradable": False}, "not_tradable"),
        ({"status": "inactive"}, "inactive"),
        ({"asset_class": "crypto"}, "not_us_equity"),
        ({"symbol": "ABC/WS"}, "unsupported_symbol"),
        ({}, None),
        ({"exchange": "TXSE"}, None),
    ],
)
def test_static_exclusions(kw, reason):
    symbol = kw.pop("symbol", "ABC")
    assert static_exclusion(make_asset(symbol, **kw), CRIT) == reason


def _screen(series, symbol="ABC"):
    return liquidity_screen(make_asset(symbol), series, CRIT, as_of=AS_OF, now=NOW)


def test_liquidity_screen_metrics_and_reasons():
    member = _screen(daily_series("ABC", SESSIONS, close="50", volume="1000000"))
    assert not isinstance(member, str)
    assert member.adv_usd == Decimal("50000000.00") and member.sessions == 20
    assert _screen(daily_series("ABC", SESSIONS, close="9.99", volume="10000000")) == (
        "price_below_min"
    )
    assert _screen(daily_series("ABC", SESSIONS, close="50", volume="100000")) == "adv_below_min"
    assert _screen(daily_series("ABC", SESSIONS[-10:])) == "insufficient_history"
    assert _screen(daily_series("ABC", SESSIONS[:-1])) == "no_trade_on_as_of"
    assert _screen([]) == "no_data"
    assert _screen(daily_series("ABC", SESSIONS, close="0")) == "bad_data"


def test_screen_ignores_bars_after_as_of():
    later = daily_series("ABC", [date(2026, 10, 26)], close="1", volume="1")
    member = _screen(daily_series("ABC", SESSIONS) + later)
    assert not isinstance(member, str) and member.last_close == Decimal(50)


def _sources():
    assets = [
        make_asset("AAA"),
        make_asset("BBB", exchange="NYSE", shortable=True),
        make_asset("CCC"),  # too cheap
        make_asset("DDD", exchange="OTC"),
        make_asset("EEE", tradable=False),
        make_asset("AAA"),  # listed twice by the broker
    ]
    bars = {
        "AAA": daily_series("AAA", SESSIONS, close="100", volume="500000"),
        "BBB": daily_series("BBB", SESSIONS, close="40", volume="2000000"),
        "CCC": daily_series("CCC", SESSIONS, close="3", volume="90000000"),
    }
    return FakeAssetSource(assets), RecordingBars(bars)


def test_build_snapshot_end_to_end(db):
    assets, bars = _sources()
    snap, created = build_universe_snapshot(db, assets, bars, CRIT, now=NOW, calendar=CAL,
                                            batch_size=1)  # fmt: skip
    assert created and snap.as_of == AS_OF and snap.member_count == 2 and snap.assets_seen == 5
    assert snap.exclusions == {"not_tradable": 1, "otc": 1, "price_below_min": 1}
    assert member_symbols(db, snap) == {"AAA", "BBB"}
    bbb = db.get(UniverseMember, (snap.id, "BBB"))
    assert bbb.exchange == "NYSE" and bbb.shortable and bbb.adv_usd == Decimal("80000000.00")
    # Only statically eligible symbols are fetched, raw (unadjusted), one batch per symbol.
    assert sorted(c[0][0] for c in bars.calls) == ["AAA", "BBB", "CCC"]
    assert set(bars.adjustments) == {"raw"}
    start, end = bars.calls[0][2], bars.calls[0][3]
    assert start.astimezone(NY).date() == SESSIONS[0] and end == NOW - timedelta(minutes=16)


def test_build_is_idempotent_unless_forced(db):
    assets, bars = _sources()
    first, _ = build_universe_snapshot(db, assets, bars, CRIT, now=NOW, calendar=CAL)
    again, created = build_universe_snapshot(db, assets, bars, CRIT, now=NOW, calendar=CAL)
    assert again.id == first.id and not created
    forced, created = build_universe_snapshot(
        db, assets, bars, CRIT, now=NOW, calendar=CAL, force=True
    )
    assert created and forced.id != first.id
    other = UniverseCriteria(min_price=Decimal(50), min_adv_usd=Decimal(1), min_members=1)
    stricter, created = build_universe_snapshot(db, assets, bars, other, now=NOW, calendar=CAL)
    assert created and member_symbols(db, stricter) == {"AAA"}


def test_build_refuses_implausibly_small_universe(db):
    assets, bars = _sources()
    strict = UniverseCriteria(min_price=Decimal(10), min_adv_usd=Decimal(20_000_000))
    with pytest.raises(UniverseBuildError, match="only 2 members"):
        build_universe_snapshot(db, assets, bars, strict, now=NOW, calendar=CAL)
    assert db.scalars(select(UniverseSnapshot)).all() == []


def test_build_fails_closed_on_data_errors(db):
    assets, bars = _sources()
    bars.error = TimeoutError()
    with pytest.raises(UniverseBuildError, match="bar fetch failed: TimeoutError"):
        build_universe_snapshot(db, assets, bars, CRIT, now=NOW, calendar=CAL)
    assets.error = ConnectionError("https://x?token=secret")
    with pytest.raises(UniverseBuildError, match="asset list unavailable: ConnectionError"):
        build_universe_snapshot(db, assets, bars, CRIT, now=NOW, calendar=CAL)
    assert db.scalars(select(UniverseSnapshot)).all() == []


def test_point_in_time_lookup_has_no_lookahead(db):
    assets, bars = _sources()
    thu = datetime(2026, 10, 22, 20, 0, tzinfo=NY)
    s_thu, _ = build_universe_snapshot(
        db, assets, bars, CRIT, now=thu, calendar=CAL
    )  # as_of Thursday; Friday's bar is excluded, so last session must be Thursday
    s_fri, _ = build_universe_snapshot(db, assets, bars, CRIT, now=NOW, calendar=CAL)
    assert s_thu.as_of == date(2026, 10, 22)
    assert universe_for_session(db, date(2026, 10, 23)).id == s_thu.id  # Friday trading
    assert universe_for_session(db, date(2026, 10, 26)).id == s_fri.id  # Monday trading
    assert universe_for_session(db, date(2026, 10, 22)) is None
    assert current_universe(db).id == s_fri.id
    monday_evening = datetime(2026, 10, 26, 20, tzinfo=NY)
    assert not is_stale(s_fri, NOW, CAL) and is_stale(s_fri, monday_evening, CAL)
