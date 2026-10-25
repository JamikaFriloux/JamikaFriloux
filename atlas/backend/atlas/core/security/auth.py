"""Password hashing (Argon2id), JWT access tokens and account lockout."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.configuration.settings import AtlasSettings
from atlas.core.models.db import Role, User

_hasher = PasswordHasher()
_ALGORITHM = "HS256"
_ISSUER = "atlas"
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 12
# Verified against when the user doesn't exist, so timing doesn't reveal valid usernames.
_DUMMY_HASH = _hasher.hash("atlas-dummy-password-for-timing")


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _secret(settings: AtlasSettings) -> str:
    secret = settings.jwt_secret.get_secret_value()
    if len(secret) < 32:
        raise AuthError("ATLAS_JWT_SECRET is not configured (min 32 chars)")
    return secret


def issue_token(settings: AtlasSettings, user: User) -> tuple[str, int]:
    now = datetime.now(UTC)
    ttl = settings.jwt_ttl_minutes * 60
    payload = {
        "sub": str(user.id),
        "usr": user.username,
        "role": user.role.value,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=ttl),
        "iss": _ISSUER,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _secret(settings), algorithm=_ALGORITHM), ttl


def decode_token(settings: AtlasSettings, token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            _secret(settings),
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid token") from exc


def authenticate(session: Session, username: str, password: str) -> User:
    """Verify credentials with lockout. Raises AuthError with a generic message."""
    user = session.scalar(select(User).where(User.username == username))
    now = datetime.now(UTC)
    if user is None:
        verify_password(_DUMMY_HASH, password)
        raise AuthError("invalid credentials")
    locked_until = user.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)  # SQLite drops tzinfo
    if locked_until is not None and locked_until > now:
        raise AuthError("invalid credentials")
    if not user.is_active or not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCKOUT
            user.failed_login_count = 0
        raise AuthError("invalid credentials")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    return user


def create_user(session: Session, username: str, password: str, role: Role) -> User:
    if session.scalar(select(User).where(User.username == username)) is not None:
        raise ValueError(f"user {username!r} already exists")
    user = User(username=username, password_hash=hash_password(password), role=role)
    session.add(user)
    session.flush()
    return user
