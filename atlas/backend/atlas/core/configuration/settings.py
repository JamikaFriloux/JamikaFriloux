"""Service settings.

Settings are split by trust boundary:

* ``AtlasSettings``  - shared, non-broker configuration. Loaded by every service.
* ``BrokerSettings`` - Alpaca paper credentials. Loaded ONLY by the execution service.
  Research agents, the API and the research worker never construct it, and in Docker
  Compose only the ``executor`` container receives the ALPACA_* variables.
* ``LLMSettings``    - LLM provider key. Loaded only by the research worker.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_POLICY = _PROJECT_ROOT / "config" / "policy.yaml"

PAPER_TRADING_BASE_URL = "https://paper-api.alpaca.markets"
# Hosts that must never be configured in this deployment. Checked defensively even though
# the Alpaca client is always constructed with paper=True.
FORBIDDEN_BROKER_HOSTS = ("api.alpaca.markets", "broker-api.alpaca.markets")


class AtlasSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    # The only accepted value. Live trading requires a separate deployment (docs/security.md).
    trading_mode: Literal["paper"] = "paper"

    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas"
    redis_url: str = "redis://localhost:6379/0"
    policy_path: Path = _DEFAULT_POLICY

    jwt_secret: SecretStr = Field(default=SecretStr(""))
    jwt_ttl_minutes: int = Field(default=60, ge=5, le=24 * 60)
    cors_origins: list[str] = ["http://localhost:3000"]
    login_rate_limit_per_minute: int = 10

    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: SecretStr | None = None
    otel_enabled: bool = False

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    timezone: str = "America/New_York"

    # Bar ingestion (executor). Benchmarks always ingested; watchlist symbols are added.
    ingest_default_symbols: list[str] = ["SPY", "QQQ", "IWM", "DIA"]
    ingest_daily_lookback_days: int = Field(default=400, ge=30, le=3650)
    ingest_minute_lookback_days: int = Field(default=5, ge=1, le=30)

    # Live market-data stream (executor). Alpaca's free IEX plan allows 30 streamed symbols.
    stream_enabled: bool = True
    stream_max_symbols: int = Field(default=30, ge=1, le=1000)
    stream_data_timeout_seconds: float = Field(default=60.0, ge=10, le=600)

    @model_validator(mode="after")
    def _require_strong_secret_outside_dev(self) -> AtlasSettings:
        secret = self.jwt_secret.get_secret_value()
        if self.environment in ("staging", "production") and len(secret) < 32:
            raise ValueError("ATLAS_JWT_SECRET must be at least 32 characters outside development")
        return self

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


class BrokerSettings(BaseSettings):
    """Alpaca PAPER credentials. Executor service only."""

    model_config = SettingsConfigDict(env_prefix="ALPACA_", env_file=".env", extra="ignore")

    api_key_id: SecretStr
    api_secret_key: SecretStr
    base_url: str = PAPER_TRADING_BASE_URL
    data_feed: Literal["iex", "sip", "delayed_sip"] = "iex"

    @field_validator("base_url")
    @classmethod
    def _paper_only(cls, v: str) -> str:
        normalized = v.rstrip("/").lower()
        if normalized != PAPER_TRADING_BASE_URL:
            raise ValueError(
                f"ALPACA_BASE_URL must be {PAPER_TRADING_BASE_URL}; live endpoints are not "
                "permitted in this deployment"
            )
        return normalized

    @field_validator("api_key_id")
    @classmethod
    def _not_live_key(cls, v: SecretStr) -> SecretStr:
        # Defense in depth: Alpaca live key IDs conventionally start with "AK", paper with "PK".
        # The authoritative check is the account probe in integrations.alpaca.guard.
        if v.get_secret_value().upper().startswith("AK"):
            raise ValueError("ALPACA_API_KEY_ID looks like a LIVE key; only paper keys allowed")
        return v


class LLMSettings(BaseSettings):
    """LLM provider configuration. Research worker only."""

    model_config = SettingsConfigDict(env_prefix="ATLAS_LLM_", env_file=".env", extra="ignore")

    provider: Literal["anthropic", "disabled"] = "disabled"
    anthropic_api_key: SecretStr | None = None
    model: str = "claude-opus-5-5"
    max_tokens: int = 4096
    timeout_seconds: float = 60.0
    # Hard cap on LLM calls per New York calendar day across all agents. Agents still run
    # their deterministic part when the cap is reached; only the narrative is skipped.
    max_calls_per_day: int = Field(default=40, ge=0, le=500)


@lru_cache(maxsize=1)
def get_settings() -> AtlasSettings:
    return AtlasSettings()
