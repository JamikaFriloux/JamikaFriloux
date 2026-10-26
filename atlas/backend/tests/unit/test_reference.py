from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import EarningsCoverage, EarningsEvent, InstrumentReference
from atlas.core.reference.earnings import (
    EarningsItem,
    blackout_lookup,
    blackout_span,
    store_calendar,
)
from atlas.core.reference.instruments import (
    InstrumentsFile,
    apply_config,
    instruments_path,
    load_instruments,
    sector_buckets,
)
from atlas.core.reference.refresh import refresh_reference
from atlas.core.reference.sectors import sector_for_sic
from atlas.core.risk.engine import evaluate
from atlas.integrations.finnhub.earnings import ROW_CAP, FinnhubEarnings, FinnhubError
from atlas.integrations.sec.edgar import EdgarClient, EdgarError

CAL = MarketCalendar()
NOW = datetime(2026, 10, 26, 7, 0, tzinfo=NY)  # Monday premarket
TODAY = date(2026, 10, 26)
MAX_AGE = timedelta(hours=30)


def _loaded(tmp_path, text):
    p = tmp_path / "instruments.yaml"
    p.write_text(text)
    return load_instruments(p)


# ---------- config ----------
def test_repository_instruments_file_is_valid(settings):
    loaded = load_instruments(instruments_path(settings.policy_path))
    assert loaded.data.etfs["SPY"].sector == "us_equity_broad"
    assert loaded.data.etfs["SOXL"].leveraged is True
    assert loaded.data.stocks["NVDA"].sector == "Information Technology"
    assert {"BE", "CRWV", "NBIS", "SPCX"}.isdisjoint({*loaded.data.etfs, *loaded.data.stocks})


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (
            {"version": 1, "etfs": {"SPY": {"sector": "x"}}, "stocks": {"SPY": {"sector": "y"}}},
            "both",
        ),
        ({"version": 1, "etfs": {"spy": {"sector": "x"}}}, "invalid symbols"),
        ({"version": 1, "stocks": {"AAA": {"sector": "unknown"}}}, "reserved"),
        ({"version": 1, "stocks": {"AAA": {"sector": "x", "extra": 1}}}, "Extra inputs"),
    ],
)
def test_instruments_file_validation(data, error):
    with pytest.raises(ValidationError, match=error):
        InstrumentsFile.model_validate(data)


def test_apply_config_upserts_removes_and_leaves_provider_rows(db, tmp_path):
    db.add(
        InstrumentReference(symbol="XOM", asset_type="stock", sector="Energy", source="sec_edgar")
    )
    db.add(InstrumentReference(symbol="OLD", asset_type="stock", sector="x", source="config"))
    db.flush()
    loaded = _loaded(
        tmp_path,
        "version: 1\netfs:\n  SPY: {sector: broad, name: S&P}\nstocks:\n  AAPL: {sector: IT}\n",
    )
    assert apply_config(db, loaded) == 3  # SPY, AAPL added; OLD removed
    assert apply_config(db, loaded) == 0  # idempotent
    rows = {r.symbol: r for r in db.scalars(select(InstrumentReference)).all()}
    assert set(rows) == {"SPY", "AAPL", "XOM"} and rows["XOM"].source == "sec_edgar"
    assert (rows["SPY"].asset_type, rows["SPY"].name) == ("etf", "S&P")
    assert sector_buckets(db) == {"SPY": "broad", "AAPL": "IT", "XOM": "Energy"}


# ---------- sectors ----------
@pytest.mark.parametrize(
    ("sic", "sector"),
    [
        (3674, "Information Technology"),  # semiconductors
        (3571, "Information Technology"),  # computers
        (2834, "Health Care"),
        (7372, "Information Technology"),
        (6798, "Real Estate"),
        (6021, "Financials"),
        (1311, "Energy"),
        (3711, "Consumer Discretionary"),
        (4911, "Utilities"),
        (9995, None),
        (None, None),
    ],
)
def test_sic_to_sector(sic, sector):
    assert sector_for_sic(sic) == sector


# ---------- providers ----------
def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_edgar_maps_tickers_to_sectors():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((str(req.url), req.headers["User-Agent"]))
        if req.url.path == "/files/company_tickers.json":
            return httpx.Response(
                200,
                json={
                    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"},
                    "1": {"cik_str": 34088, "ticker": "XOM", "title": "Exxon"},
                },
            )
        if req.url.path.endswith("CIK0001045810.json"):
            return httpx.Response(200, json={"sic": "3674", "name": "NVIDIA CORP"})
        return httpx.Response(404)

    c = EdgarClient("ATLAS ops@example.com", _client(handler), sleep=lambda _s: None)
    out = c.companies(["NVDA", "XOM", "SPY"])  # XOM: 404 on submissions; SPY: unknown ticker
    assert [(x.symbol, x.cik, x.sic, x.sector) for x in out] == [
        ("NVDA", 1045810, 3674, "Information Technology")
    ]
    assert all(ua == "ATLAS ops@example.com" for _, ua in seen)
    assert "CIK0001045810" in seen[1][0]


def test_edgar_requires_contact_and_reports_errors():
    with pytest.raises(EdgarError, match="contact"):
        EdgarClient("ATLAS")
    c = EdgarClient("a b@c.d", _client(lambda r: httpx.Response(503)), sleep=lambda _s: None)
    with pytest.raises(EdgarError, match="503"):
        c.companies(["NVDA"])


def test_finnhub_token_in_header_not_url_and_parsing():
    seen = []
    rows = {
        "2026-10-28": [
            {"date": "2026-10-28", "hour": "amc", "symbol": "aapl"},
            {"date": "2026-10-28", "hour": "amc", "symbol": "GOOGL"},
            {"date": "bad", "symbol": "X"},
            {"hour": "bmo", "symbol": "Y"},
        ],
        "2026-10-29": [{"date": "2026-10-29", "hour": "", "symbol": "MSFT"}],
    }
    by_symbol = {
        # As live: the market-wide calendar omits GOOG and a GOOG query answers with the
        # issuer's row labelled GOOGL. Rows outside the window are dropped.
        "GOOG": [
            {"date": "2026-10-28", "hour": "amc", "symbol": "GOOGL"},
            {"date": "2027-01-27", "hour": "amc", "symbol": "GOOGL"},
        ],
        "META": [],
    }

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        p = req.url.params
        if "symbol" in p:
            got = by_symbol[p["symbol"]]
        else:
            assert p["from"] == p["to"]
            got = rows.get(p["from"], [])
        return httpx.Response(200, json={"earningsCalendar": got})

    waits = []
    f = FinnhubEarnings("sekret", _client(handler), sleep=waits.append)
    items = f.calendar(date(2026, 10, 26), date(2026, 11, 25), ["GOOG", "META"])
    assert items == [
        EarningsItem("AAPL", date(2026, 10, 28), "amc"),
        EarningsItem("GOOGL", date(2026, 10, 28), "amc"),
        EarningsItem("MSFT", date(2026, 10, 29), "unknown"),
        EarningsItem("GOOG", date(2026, 10, 28), "amc"),
    ]
    days = [(date(2026, 10, 26) + timedelta(days=i)).isoformat() for i in range(31)]
    assert [r.url.params.get("from") for r in seen[:31]] == days
    assert [r.url.params["symbol"] for r in seen[31:]] == ["GOOG", "META"]
    assert len(waits) == len(seen) - 1 and all(w > 0 for w in waits)  # paced under 60/min
    for req in seen:
        assert req.headers["X-Finnhub-Token"] == "sekret" and "sekret" not in str(req.url)


def test_finnhub_truncated_day_raises():
    # Finnhub caps a response at 1500 rows, keeping the latest dates; a capped day can't be
    # trusted to list every report, so it must fail rather than clear stocks.
    def handler(req: httpx.Request) -> httpx.Response:
        d = req.url.params["from"]
        n = ROW_CAP if d == "2026-10-27" else 3
        return httpx.Response(
            200, json={"earningsCalendar": [{"date": d, "symbol": f"S{i}"} for i in range(n)]}
        )

    with pytest.raises(FinnhubError, match="truncated"):
        FinnhubEarnings("k", _client(handler), sleep=lambda _s: None).calendar(
            TODAY, TODAY + timedelta(days=2)
        )


def test_finnhub_row_outside_requested_day_raises():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"earningsCalendar": [{"date": "2026-11-20", "symbol": "AAPL"}]}
        )

    with pytest.raises(FinnhubError, match="window"):
        FinnhubEarnings("k", _client(handler), sleep=lambda _s: None).calendar(TODAY, TODAY)


def test_finnhub_failed_symbol_query_fails_the_whole_fetch():
    def handler(req: httpx.Request) -> httpx.Response:
        if "symbol" in req.url.params:
            return httpx.Response(429)
        return httpx.Response(200, json={"earningsCalendar": []})

    with pytest.raises(FinnhubError, match="429"):
        FinnhubEarnings("k", _client(handler), sleep=lambda _s: None).calendar(
            TODAY, TODAY, ["GOOG"]
        )


@pytest.mark.parametrize("resp", [httpx.Response(401), httpx.Response(200, json={"x": 1})])
def test_finnhub_failures_raise(resp):
    with pytest.raises(FinnhubError):
        FinnhubEarnings("k", _client(lambda _r: resp), sleep=lambda _s: None).calendar(TODAY, TODAY)


# ---------- calendar and blackout ----------
def _classify(db, **kinds):
    for sym, kind in kinds.items():
        db.add(InstrumentReference(symbol=sym, asset_type=kind, sector="s", source="config"))
    db.flush()


def _lookup(db, now=NOW, days=2):
    return blackout_lookup(
        db, now=now, today=now.astimezone(NY).date(), days=days, calendar=CAL, max_age=MAX_AGE
    )


def test_blackout_span_includes_today_and_next_sessions():
    assert blackout_span(TODAY, 2, CAL) == [
        date(2026, 10, 26),
        date(2026, 10, 27),
        date(2026, 10, 28),
    ]
    # From a Saturday: the next two sessions.
    assert blackout_span(date(2026, 10, 24), 2, CAL) == [date(2026, 10, 26), date(2026, 10, 27)]


def test_store_calendar_replaces_window_and_dedupes(db):
    t0 = NOW.astimezone(UTC)
    store_calendar(
        db,
        "f",
        [EarningsItem("AAA", date(2026, 10, 27))],
        window_start=TODAY,
        window_end=date(2026, 11, 25),
        now=t0,
    )
    cov = store_calendar(
        db,
        "f",
        [
            EarningsItem("AAA", date(2026, 10, 30)),
            EarningsItem("AAA", date(2026, 10, 30)),
            EarningsItem("BBB", date(2027, 1, 1)),
        ],  # outside the window: dropped
        window_start=TODAY,
        window_end=date(2026, 11, 25),
        now=t0,
    )
    rows = db.scalars(select(EarningsEvent)).all()
    assert [(r.symbol, r.day) for r in rows] == [("AAA", date(2026, 10, 30))]  # date moved
    assert cov.events == 1 and len(db.scalars(select(EarningsCoverage)).all()) == 2


def test_blackout_rules(db):
    _classify(db, SPY="etf", AAA="stock", BBB="stock", CCC="stock")
    lk = _lookup(db)
    assert lk("SPY") is False  # ETF: no earnings, no calendar needed
    assert lk("AAA") is None and lk("ZZZ") is None  # no calendar: fail closed
    store_calendar(
        db,
        "f",
        [EarningsItem("AAA", date(2026, 10, 28), "amc"), EarningsItem("BBB", date(2026, 10, 29))],
        window_start=TODAY,
        window_end=date(2026, 11, 25),
        now=NOW.astimezone(UTC) - timedelta(hours=2),
    )
    lk = _lookup(db)
    assert lk("AAA") is True  # reports on the 2nd session ahead
    assert lk("BBB") is False  # 3rd session ahead: outside the span
    assert lk("CCC") is False  # classified stock, fresh calendar, no report
    assert lk("ZZZ") is None  # unclassified: absence from a calendar proves nothing
    # A day later than max age: no clearance, but a known report still blocks.
    stale = _lookup(db, now=NOW + timedelta(hours=31))
    assert stale("CCC") is None and stale("SPY") is False
    assert _lookup(db, now=NOW + timedelta(days=1, hours=31))("BBB") is True


def test_coverage_must_span_the_blackout(db):
    _classify(db, CCC="stock")
    store_calendar(
        db, "f", [], window_start=TODAY, window_end=date(2026, 10, 27), now=NOW.astimezone(UTC)
    )
    assert _lookup(db)("CCC") is None  # window ends before the 3rd session of the span
    assert _lookup(db, days=1)("CCC") is False


# ---------- refresh ----------
class FakeCompanies:
    def __init__(self, out=(), error=None):
        self.out, self.error, self.asked = list(out), error, None

    def companies(self, symbols):
        self.asked = list(symbols)
        if self.error:
            raise self.error
        return self.out


class FakeEarnings:
    source = "fake"

    def __init__(self, items=(), error=None):
        self.items, self.error = list(items), error
        self.symbols = None

    def calendar(self, start, end, symbols):
        self.symbols = list(symbols)
        if self.error:
            raise self.error
        return self.items


def test_refresh_applies_config_providers_and_reports(db, tmp_path):
    from atlas.integrations.sec.edgar import CompanyInfo

    loaded = _loaded(tmp_path, "version: 1\netfs:\n  SPY: {sector: broad}\n")
    comp = FakeCompanies(
        [
            CompanyInfo("XOM", 1, "Exxon", 2911, "Energy"),
            CompanyInfo("SHEL", 2, "Shell co", 9995, None),
        ]
    )
    out = refresh_reference(
        db,
        instruments=loaded,
        symbols=["SPY", "XOM", "SHEL"],
        now=NOW.astimezone(UTC),
        companies=comp,
        earnings=(fe := FakeEarnings([EarningsItem("XOM", date(2026, 10, 30))])),
        horizon_days=30,
    )
    assert comp.asked == ["XOM", "SHEL"]  # only symbols config doesn't cover
    assert fe.symbols == ["SHEL", "XOM"]  # watched stocks queried by symbol; ETFs aren't
    assert out["sec_edgar"] == 1 and out["unclassified"] == ["SHEL"] and out["errors"] == {}
    assert out["earnings"]["events"] == 1
    assert db.get(InstrumentReference, "XOM").sic == 2911


def test_refresh_provider_failures_keep_config_and_report(db, tmp_path):
    loaded = _loaded(tmp_path, "version: 1\netfs:\n  SPY: {sector: broad}\n")
    out = refresh_reference(
        db,
        instruments=loaded,
        symbols=["SPY", "XOM"],
        now=NOW.astimezone(UTC),
        companies=FakeCompanies(error=RuntimeError("blocked")),
        earnings=FakeEarnings(error=FinnhubError("HTTP 403")),
        horizon_days=30,
    )
    assert out["errors"] == {"sec_edgar": "blocked", "earnings": "HTTP 403"}
    assert db.get(InstrumentReference, "SPY") is not None
    assert db.scalars(select(EarningsCoverage)).all() == []  # a failed fetch clears nothing
    out = refresh_reference(
        db,
        instruments=loaded,
        symbols=["SPY"],
        now=NOW.astimezone(UTC),
        companies=None,
        earnings=None,
        horizon_days=30,
    )
    assert out["sec_edgar"] == out["earnings"] == "not configured"


# ---------- risk engine ----------
def test_engine_sector_cap_uses_supplied_bucket(policy):
    from tests.unit.test_risk_engine import ENTRY, ctx

    # Capital base $10k: 25% sector budget = $2,500.
    full = evaluate(ENTRY, ctx(sector="IT", sector_exposure=Decimal(2_450)), policy.policy, CAL)
    assert full.failed == ["size"] and "binding: sector_exposure" in full.checks[-1].detail
    assert "sector IT" in full.checks[-1].detail
    room = evaluate(ENTRY, ctx(sector="IT", sector_exposure=Decimal(0)), policy.policy, CAL)
    assert room.approved


def test_earnings_rejection_says_why(policy):
    from tests.unit.test_risk_engine import ENTRY, ctx

    r = evaluate(ENTRY, ctx(earnings_blackout=None), policy.policy, CAL)
    detail = next(c.detail for c in r.checks if c.name == "earnings_blackout")
    assert "unclassified" in detail and "fail closed" in detail


def test_check_reference_fails_closed_without_providers(session_factory, monkeypatch, capsys):
    from contextlib import contextmanager

    from atlas.scripts import check_reference

    @contextmanager
    def scope():
        with session_factory() as s:
            yield s
            s.commit()

    monkeypatch.delenv("ATLAS_REFDATA_SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("ATLAS_REFDATA_FINNHUB_API_KEY", raising=False)
    monkeypatch.setattr(check_reference, "session_scope", scope)
    assert check_reference.main() == 2
    out = capsys.readouterr().out
    assert "FAIL  ATLAS_REFDATA_FINNHUB_API_KEY not set" in out
    assert (
        "unclassified watched symbols" in out and "RESULT 4 failing" in out
    )  # SEC, Finnhub, unclassified, calendar
