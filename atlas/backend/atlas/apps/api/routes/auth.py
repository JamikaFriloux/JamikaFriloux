from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from atlas.apps.api.deps import client_ip, get_current_user, get_db
from atlas.core.models.db import User
from atlas.core.security import audit
from atlas.core.security.auth import AuthError, authenticate, issue_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
    role: str


class Me(BaseModel):
    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    settings = request.app.state.settings
    ip = client_ip(request)
    limiter = request.app.state.rate_limiter
    if not limiter.hit(f"login:{ip}", settings.login_rate_limit_per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many login attempts")
    try:
        user = authenticate(db, body.username, body.password)
    except AuthError:
        audit.record(db, actor=body.username[:64], action="auth.login_failed", ip_address=ip)
        db.commit()  # persist failed-attempt counter + audit before raising
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from None
    token, ttl = issue_token(settings, user)
    audit.record(db, actor=user.username, action="auth.login", ip_address=ip)
    return TokenResponse(access_token=token, expires_in=ttl, role=user.role.value)


@router.get("/me", response_model=Me)
def me(user: User = Depends(get_current_user)) -> Me:
    return Me(username=user.username, role=user.role.value)
