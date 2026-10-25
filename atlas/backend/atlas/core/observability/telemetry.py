"""Optional error monitoring (Sentry) and tracing (OpenTelemetry)."""

from __future__ import annotations

from typing import Any

from atlas.core.configuration.settings import AtlasSettings
from atlas.core.observability.logging import get_logger, redact_mapping

log = get_logger(__name__)


def _scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    return redact_mapping(event)


def init_telemetry(settings: AtlasSettings, service: str) -> None:
    if settings.sentry_dsn is not None:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn.get_secret_value(),
            environment=settings.environment,
            send_default_pii=False,
            before_send=_scrub_event,  # type: ignore[arg-type]
            traces_sample_rate=0.0,
        )
        log.info("sentry_enabled", service=service)
    if settings.otel_enabled:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        # Exporter is configured via standard OTEL_EXPORTER_* env vars by the deployment.
        trace.set_tracer_provider(
            TracerProvider(resource=Resource.create({"service.name": f"atlas-{service}"}))
        )
        log.info("otel_enabled", service=service)
