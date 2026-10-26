"""ATLAS API service.

Holds NO broker credentials. It reads state that the execution service writes to the database
and dispatches control actions (kill switch follow-up) to the execution queue.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from atlas.apps.api.routes import auth, health, market, system, trading, universe
from atlas.core.configuration.policy import LoadedPolicy, load_policy
from atlas.core.configuration.settings import AtlasSettings, get_settings
from atlas.core.models.session import get_sessionmaker, session_scope
from atlas.core.observability.logging import configure_logging, get_logger
from atlas.core.observability.telemetry import init_telemetry
from atlas.core.security import audit
from atlas.core.security.rate_limit import RateLimiter

log = get_logger(__name__)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


def _default_dispatcher(settings: AtlasSettings) -> Callable[[], bool]:
    def dispatch() -> bool:
        try:
            from atlas.apps.worker.celery_app import celery_app

            celery_app.send_task("atlas.execution.kill_switch_actions", queue="execution")
            return True
        except Exception:
            log.error("kill_switch_dispatch_failed")
            return False

    return dispatch


def _default_validation_dispatcher() -> Callable[[str, str], bool]:
    def dispatch(strategy_id: str, requested_by: str) -> bool:
        try:
            from atlas.apps.worker.celery_app import celery_app

            celery_app.send_task(
                "atlas.worker.validate_strategy", args=[strategy_id, requested_by], queue="default"
            )
            return True
        except Exception:
            log.error("validation_dispatch_failed")
            return False

    return dispatch


def _redis_client(settings: AtlasSettings) -> Any | None:
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
    except Exception:
        return None


def create_app(
    settings: AtlasSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    policy: LoadedPolicy | None = None,
    redis_client: Any | None = "auto",
    dispatcher: Callable[[], bool] | None = None,
    validation_dispatcher: Callable[[str, str], bool] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if settings.trading_mode != "paper":  # pragma: no cover - Literal already enforces this
        raise RuntimeError("only paper trading is supported in this deployment")
    policy = policy or load_policy(settings.policy_path)
    session_factory = session_factory or get_sessionmaker()
    redis = _redis_client(settings) if redis_client == "auto" else redis_client

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_json, service="api")
        init_telemetry(settings, "api")
        try:
            with session_scope(session_factory) as s:
                audit.record(
                    s,
                    actor="system",
                    action="service.start",
                    target="api",
                    details={"policy_sha256": policy.sha256, "trading_mode": "paper"},
                )
        except Exception:
            log.error("startup_audit_failed")
        yield

    app = FastAPI(
        title="ATLAS API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.policy = policy
    app.state.redis = redis
    app.state.rate_limiter = RateLimiter(redis)
    app.state.dispatch_kill_switch_actions = dispatcher or _default_dispatcher(settings)
    app.state.dispatch_validation = validation_dispatcher or _default_validation_dispatcher()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        if request.url.path in ("/docs", "/openapi.json"):
            del response.headers["Content-Security-Policy"]  # Swagger UI needs CDN assets
        response.headers["X-Request-ID"] = request_id[:64]
        response.headers["X-Trading-Mode"] = "PAPER"
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(market.router)
    app.include_router(universe.router)
    app.include_router(trading.router)
    return app


def app_factory() -> FastAPI:
    return create_app()
