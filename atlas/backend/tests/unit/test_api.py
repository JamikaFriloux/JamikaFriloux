import pytest
from fastapi.testclient import TestClient

from atlas.apps.api.main import create_app
from atlas.core.models.db import Role
from atlas.core.security.auth import create_user

PW = "correct horse battery"


@pytest.fixture
def dispatched():
    return []


@pytest.fixture
def client(settings, session_factory, policy, dispatched):
    with session_factory() as s:
        for name, role in [
            ("viewer", Role.VIEWER),
            ("operator", Role.OPERATOR),
            ("admin", Role.ADMIN),
        ]:
            create_user(s, name, PW, role)
        s.commit()
    app = create_app(
        settings,
        session_factory,
        policy,
        redis_client=None,
        dispatcher=lambda: dispatched.append(1) or True,
        validation_dispatcher=lambda sid, who: dispatched.append((sid, who)) or True,
    )
    with TestClient(app) as c:
        yield c


def _auth(client, user):
    r = client.post("/api/v1/auth/login", json={"username": user, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"


def test_ready_reports_service_status_and_staleness(client, session_factory):
    from datetime import UTC, datetime, timedelta

    from atlas.core.models.db import ServiceHeartbeat

    now = datetime.now(UTC)
    old = now - timedelta(hours=5)
    with session_factory() as s:
        s.add_all([
            ServiceHeartbeat(service="stream", status="error", last_seen=now),
            ServiceHeartbeat(service="worker", status="ok", last_seen=old),
            ServiceHeartbeat(service="universe", status="ok", last_seen=old),
            ServiceHeartbeat(service="ingest_1min", status="degraded", last_seen=old),
        ])  # fmt: skip
        s.commit()
    services = client.get("/health/ready").json()["checks"]["services"]
    assert services == {
        "stream": "error",  # alive but failing must not read as ok
        "worker": "stale",  # continuous service that stopped reporting
        "universe": "ok",  # scheduled job: an old heartbeat is normal
        "ingest_1min": "degraded",
    }


def test_security_headers(client):
    r = client.get("/health/live")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Trading-Mode"] == "PAPER"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_login_failure_generic(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"
    r = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"


def test_login_rate_limited(client, settings):
    from unittest.mock import patch

    # Freeze the clock mid-window: the limiter uses fixed 60 s windows, so a burst that
    # straddled a minute boundary would split across two windows and never hit the limit.
    with patch("atlas.core.security.rate_limit.time.time", return_value=1_800_000_030.0):
        codes = [
            client.post("/api/v1/auth/login", json={"username": "x", "password": "y"}).status_code
            for _ in range(settings.login_rate_limit_per_minute + 2)
        ]
    assert codes[: settings.login_rate_limit_per_minute] == [401] * (
        settings.login_rate_limit_per_minute
    )
    assert codes[-2:] == [429, 429]


def test_status_requires_auth_and_shows_paper(client):
    assert client.get("/api/v1/status").status_code == 401
    assert (
        client.get("/api/v1/status", headers={"Authorization": "Bearer garbage"}).status_code == 401
    )
    body = client.get("/api/v1/status", headers=_auth(client, "viewer")).json()
    assert body["trading_mode"] == "PAPER"
    assert body["kill_switch"]["engaged"] is True and body["trading_allowed"] is False
    assert body["account"] is None  # no broker sync yet: we never fabricate numbers
    assert body["policy"]["limits"]["max_concurrent_positions"] == 5


def test_rbac_on_kill_switch_and_audit(client):
    viewer = _auth(client, "viewer")
    assert (
        client.post(
            "/api/v1/kill-switch/engage", json={"reason": "test"}, headers=viewer
        ).status_code
        == 403
    )
    assert client.get("/api/v1/audit", headers=viewer).status_code == 403
    operator = _auth(client, "operator")
    assert (
        client.post(
            "/api/v1/kill-switch/resume", json={"reason": "x" * 5, "password": PW}, headers=operator
        ).status_code
        == 403
    )


def test_kill_switch_full_cycle(client, dispatched):
    admin = _auth(client, "admin")
    # resume requires password re-entry
    r = client.post(
        "/api/v1/kill-switch/resume", json={"reason": "armed", "password": "wrong"}, headers=admin
    )
    assert r.status_code == 403
    r = client.post(
        "/api/v1/kill-switch/resume",
        json={"reason": "config verified", "password": PW},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["engaged"] is False
    r = client.post(
        "/api/v1/kill-switch/resume", json={"reason": "again", "password": PW}, headers=admin
    )
    assert r.status_code == 409

    operator = _auth(client, "operator")
    r = client.post(
        "/api/v1/kill-switch/engage", json={"reason": "abnormal losses"}, headers=operator
    )
    assert r.status_code == 200 and r.json()["engaged"] is True and r.json()["follow_up_dispatched"]
    assert dispatched == [1]
    r = client.post("/api/v1/kill-switch/engage", json={"reason": "again"}, headers=operator)
    assert r.json()["changed"] is False and dispatched == [1]

    actions = [e["action"] for e in client.get("/api/v1/audit", headers=admin).json()]
    assert "kill_switch.engage" in actions and "kill_switch.resume" in actions
    assert "auth.login" in actions and "service.start" in actions


def test_deactivated_user_token_rejected(client, session_factory):
    headers = _auth(client, "viewer")
    from sqlalchemy import update

    from atlas.core.models.db import User

    with session_factory() as s:
        s.execute(update(User).where(User.username == "viewer").values(is_active=False))
        s.commit()
    assert client.get("/api/v1/status", headers=headers).status_code == 401


def test_data_quality_endpoint_returns_latest_report_per_series(client, session_factory):
    import uuid
    from datetime import UTC, datetime

    from atlas.core.models.db import DataQualityReport

    def report(symbol, ok, ts):
        return DataQualityReport(
            run_id=uuid.uuid4(), ts=ts, symbol=symbol, timeframe="1Day", source="alpaca_iex",
            window_start=ts, window_end=ts, ok=ok, stale=not ok, issues=[],
        )  # fmt: skip

    t1, t2 = datetime(2026, 10, 21, tzinfo=UTC), datetime(2026, 10, 22, tzinfo=UTC)
    with session_factory() as s:
        s.add_all([report("SPY", False, t1), report("SPY", True, t2), report("QQQ", True, t2)])
        s.commit()
    assert client.get("/api/v1/data/quality").status_code == 401
    rows = client.get("/api/v1/data/quality", headers=_auth(client, "viewer")).json()
    assert [(r["symbol"], r["ok"]) for r in rows] == [("QQQ", True), ("SPY", True)]


def test_market_live_endpoint(client):
    import fakeredis

    from atlas.core.data.live import LiveSnapshot, LiveStore, Quote

    assert client.get("/api/v1/market/live").status_code == 401
    headers = _auth(client, "viewer")
    # The test app has no Redis: say so instead of inventing data.
    assert client.get("/api/v1/market/live", headers=headers).status_code == 503

    r = fakeredis.FakeRedis()
    store = LiveStore(r)
    from datetime import UTC, datetime
    from decimal import Decimal

    old = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
    store.write([LiveSnapshot("SPY", Quote("SPY", Decimal("1"), Decimal("1.01"), Decimal(1),
                                           Decimal(1), old))])  # fmt: skip
    store.write_status({"status": "ok", "state": "subscribed"})
    client.app.state.redis = r
    body = client.get("/api/v1/market/live", headers=headers).json()
    assert body["trading_mode"] == "PAPER" and body["stream"]["state"] == "subscribed"
    (q,) = body["quotes"]
    assert q["symbol"] == "SPY" and q["bid"] == "1" and q["fresh"] is False and q["last"] is None


def test_universe_and_watchlist_endpoints(client, session_factory):
    from tests.unit.test_watchlists import seed_universe

    viewer, operator = _auth(client, "viewer"), _auth(client, "operator")
    assert client.get("/api/v1/universe", headers=viewer).json()["snapshot"] is None
    # No universe yet: additions are refused, not silently accepted.
    r = client.post("/api/v1/watchlists", json={"name": "core", "symbols": ["AAPL"]},
                    headers=operator)  # fmt: skip
    assert r.status_code == 409

    with session_factory() as s:
        seed_universe(s, ["AAPL", "MSFT", "NVDA"])
        s.commit()
    body = client.get("/api/v1/universe?q=ms", headers=viewer).json()
    assert body["snapshot"]["member_count"] == 3 and [m["symbol"] for m in body["members"]] == [
        "MSFT"
    ]

    new = {"name": "core", "symbols": ["aapl", "MSFT"]}
    assert client.post("/api/v1/watchlists", json=new, headers=viewer).status_code == 403
    r = client.post("/api/v1/watchlists", json=new, headers=operator)
    assert r.status_code == 201 and r.json()["symbols"] == ["AAPL", "MSFT"]
    assert client.post("/api/v1/watchlists", json=new, headers=operator).status_code == 400
    r = client.put("/api/v1/watchlists/core", json={"symbols": ["PENNY"]}, headers=operator)
    assert r.status_code == 422 and "PENNY" in r.json()["detail"]["rejected"]
    r = client.put("/api/v1/watchlists/nope", json={"symbols": ["AAPL"]}, headers=operator)
    assert r.status_code == 404
    r = client.put("/api/v1/watchlists/core", json={"symbols": ["NVDA"]}, headers=operator)
    assert r.status_code == 200

    view = client.get("/api/v1/watchlists", headers=viewer).json()
    assert view["watchlists"][0]["symbols"] == [{"symbol": "NVDA", "in_universe": True}]
    assert view["stream"] == {"symbols": 5, "capacity": 30}  # NVDA + 4 benchmarks
    assert view["benchmarks"] == ["SPY", "QQQ", "IWM", "DIA"]
    assert client.delete("/api/v1/watchlists/core", headers=operator).status_code == 204
    assert client.delete("/api/v1/watchlists/core", headers=operator).status_code == 404


def test_trading_endpoints_and_gated_promotion(client, session_factory):
    from datetime import date
    from decimal import Decimal

    from atlas.core.models.db import RiskDecision, SignalRecord

    viewer, admin, operator = (
        _auth(client, "viewer"),
        _auth(client, "admin"),
        _auth(client, "operator"),
    )
    strategies = client.get("/api/v1/strategies", headers=viewer).json()
    assert {s["id"]: s["status"] for s in strategies} == {
        "rsi_pullback": "RESEARCH",
        "trend_breakout": "RESEARCH",
    }
    assert all(not s["can_submit_paper_orders"] for s in strategies)

    body = {"status": "PAPER", "reason": "looks good", "password": PW}
    url = "/api/v1/strategies/trend_breakout/status"
    assert client.post(url, json=body, headers=operator).status_code == 403
    assert client.post(url, json={**body, "password": "wrong"}, headers=admin).status_code == 403
    r = client.post(url, json=body, headers=admin)
    assert r.status_code == 409 and "validation report" in r.json()["detail"]
    r = client.post(url, json={**body, "status": "RETIRED"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "RETIRED"
    assert (
        client.post("/api/v1/strategies/nope/status", json=body, headers=admin).status_code == 404
    )

    with session_factory() as s:
        s.add(
            SignalRecord(
                id="a" * 32,
                strategy_id="rsi_pullback",
                strategy_version="1.0.0",
                symbol="AAA",
                kind="entry",
                side="buy",
                as_of=date(2026, 10, 23),
                ref_price=Decimal(100),
                stop_price=Decimal(95),
                reason={"rsi": 4.2},
                mode="shadow",
                status="SHADOWED",
            )
        )
        s.add(
            RiskDecision(
                signal_id="a" * 32,
                strategy_id="rsi_pullback",
                symbol="AAA",
                kind="entry",
                mode="shadow",
                approved=False,
                failed=["earnings_blackout"],
                checks=[],
                capital_base=Decimal(10000),
            )
        )
        s.commit()
    sig = client.get("/api/v1/signals", headers=viewer).json()[0]
    assert sig["symbol"] == "AAA" and sig["decision"]["failed"] == ["earnings_blackout"]
    rej = client.get("/api/v1/risk-decisions?rejected_only=true", headers=viewer).json()
    assert len(rej) == 1 and rej[0]["capital_base"] == "10000.000000"
    assert client.get("/api/v1/orders", headers=viewer).json() == []
    # No endpoint can create an order.
    assert client.post("/api/v1/orders", json={}, headers=admin).status_code == 405


def test_status_with_account_snapshots(client, session_factory):
    """Regression: /status crashed (Decimal - float) once a broker snapshot existed."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from atlas.core.models.db import AccountSnapshot

    now = datetime.now(UTC)
    with session_factory() as s:
        for ts, eq in ((now - timedelta(days=3), "100000"), (now, "100250.50")):
            s.add(
                AccountSnapshot(
                    ts=ts,
                    source="alpaca_paper",
                    is_paper=True,
                    account_status="ACTIVE",
                    equity=Decimal(eq),
                    last_equity=Decimal("100100"),
                    cash=Decimal(eq),
                    buying_power=Decimal(eq),
                    long_market_value=Decimal(0),
                    trading_blocked=False,
                    shorting_enabled=True,
                )
            )
        s.commit()
    r = client.get("/api/v1/status", headers=_auth(client, "viewer"))
    assert r.status_code == 200, r.text
    a = r.json()["account"]
    assert Decimal(a["total_pl"]) == Decimal("250.50")  # vs first sync, not the policy budget
    assert Decimal(a["day_pl"]) == Decimal("150.50")
    assert Decimal(a["capital_base"]) == Decimal("10000") and a["shorting_enabled"] is True
    dd = r.json()["drawdown"]
    assert Decimal(dd["limit"]) == Decimal("500") and dd["cooldown_sessions_remaining"] == 0


def test_validation_endpoints(client, session_factory, dispatched, policy):
    from datetime import date
    from decimal import Decimal

    from atlas.core.backtesting.validation import params_hash
    from atlas.core.models.db import ValidationReport
    from atlas.core.strategies.registry import STRATEGIES

    admin, viewer = _auth(client, "admin"), _auth(client, "viewer")
    assert (
        client.post("/api/v1/strategies/rsi_pullback/validate", headers=viewer).status_code == 403
    )
    assert client.post("/api/v1/strategies/nope/validate", headers=admin).status_code == 404
    r = client.post("/api/v1/strategies/rsi_pullback/validate", headers=admin)
    assert r.status_code == 202 and ("rsi_pullback", "admin") in dispatched

    client.get("/api/v1/strategies", headers=viewer)  # registers strategies
    params = STRATEGIES["rsi_pullback"].params.model_dump()
    with session_factory() as s:
        s.add(
            ValidationReport(
                strategy_id="rsi_pullback",
                version="1.0.0",
                params=params,
                params_hash=params_hash(params),
                target_status="PAPER",
                policy_sha256=policy.sha256,
                passed=False,
                data_start=date(2016, 1, 4),
                data_end=date(2026, 10, 23),
                symbols=["SPY"],
                gates=[
                    {
                        "name": "sharpe",
                        "passed": False,
                        "value": 0.1,
                        "threshold": ">= 0.5",
                        "detail": "",
                    }
                ],
                metrics={"full": {"trades": 120, "sharpe": 0.1}},
                equity_curve=[["2026-10-23", 10100.0]],
                caveats=["survivorship_bias: ..."],
                runtime_seconds=Decimal("12.5"),
            )
        )
        s.commit()
    rows = client.get("/api/v1/validation-reports?strategy_id=rsi_pullback", headers=viewer).json()
    assert len(rows) == 1 and rows[0]["failed_gates"] == ["sharpe"]
    assert (
        rows[0]["headline"]["trades"] == 120 and rows[0]["currently_valid_for_promotion"] is False
    )
    full = client.get(f"/api/v1/validation-reports/{rows[0]['id']}", headers=viewer).json()
    assert full["equity_curve"] == [["2026-10-23", 10100.0]] and full["caveats"]
    assert client.get("/api/v1/validation-reports/999", headers=viewer).status_code == 404
