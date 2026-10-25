from datetime import UTC, datetime, timedelta

import jwt
import pytest

from atlas.core.models.db import Role
from atlas.core.security.auth import (
    MAX_FAILED_LOGINS,
    AuthError,
    authenticate,
    create_user,
    decode_token,
    hash_password,
    issue_token,
    verify_password,
)
from tests.conftest import TEST_SECRET

PW = "correct horse battery"


def test_hash_and_verify():
    h = hash_password(PW)
    assert h.startswith("$argon2id$")
    assert verify_password(h, PW) and not verify_password(h, "wrong")
    assert not verify_password("not-a-hash", PW)


def test_short_password_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


def test_token_roundtrip_and_tamper(settings, db):
    user = create_user(db, "alice", PW, Role.OPERATOR)
    token, ttl = issue_token(settings, user)
    claims = decode_token(settings, token)
    assert claims["role"] == "operator" and ttl == settings.jwt_ttl_minutes * 60
    with pytest.raises(AuthError):
        decode_token(settings, token[:-2] + ("AA" if token[-2:] != "AA" else "BB"))
    forged = jwt.encode({**claims, "role": "admin"}, "other-secret-" + "z" * 40, algorithm="HS256")
    with pytest.raises(AuthError):
        decode_token(settings, forged)
    none_alg = jwt.encode({**claims}, None, algorithm="none")
    with pytest.raises(AuthError):
        decode_token(settings, none_alg)


def test_expired_token_rejected(settings, db):
    user = create_user(db, "bob", PW, Role.VIEWER)
    past = datetime.now(UTC) - timedelta(hours=2)
    token = jwt.encode(
        {"sub": str(user.id), "iat": past, "exp": past + timedelta(minutes=5), "iss": "atlas"},
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_token(settings, token)


def test_lockout_after_failed_attempts(db):
    create_user(db, "carol", PW, Role.VIEWER)
    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(AuthError):
            authenticate(db, "carol", "wrong password!")
    with pytest.raises(AuthError):
        authenticate(db, "carol", PW)  # locked even with the correct password


def test_unknown_user_generic_error(db):
    with pytest.raises(AuthError, match="invalid credentials"):
        authenticate(db, "nobody", PW)


def test_missing_secret_refuses_tokens(db):
    from pydantic import SecretStr

    from atlas.core.configuration.settings import AtlasSettings

    weak = AtlasSettings(environment="development", jwt_secret=SecretStr(""), _env_file=None)
    user = create_user(db, "dave", PW, Role.VIEWER)
    with pytest.raises(AuthError):
        issue_token(weak, user)
