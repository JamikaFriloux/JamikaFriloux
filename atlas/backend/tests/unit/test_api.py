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
    codes = [
        client.post("/api/v1/auth/login", json={"username": "x", "password": "y"}).status_code
        for _ in range(settings.login_rate_limit_per_minute + 2)
    ]
    assert 429 in codes


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
