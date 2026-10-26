"""Risk & trading policy loading and validation.

The policy file is the single source of truth for risk limits. It is validated against
HARD_LIMITS, which encode structural constraints of the paper deployment (long-only, no
leverage, ...). A policy that tries to loosen a hard limit fails at startup instead of being
silently clamped, so an operator always sees why the service refused to start.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Absolute ceilings. Raising any of these requires a code change + review, never a config edit.
HARD_LIMITS = {
    "max_risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 3.0,
    "max_drawdown_pct": 15.0,
    "max_position_allocation_pct": 25.0,
    "max_concurrent_positions": 20,
    "max_sector_exposure_pct": 50.0,
    "max_gross_exposure_pct": 100.0,  # 100% == no leverage
    "max_new_trades_per_day": 20,
    "max_order_notional_usd": 25_000.0,
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AccountPolicy(_Strict):
    starting_equity_usd: float = Field(gt=0)


class InstrumentPolicy(_Strict):
    allowed_asset_classes: list[Literal["us_equity"]]
    long_only: Literal[True]
    allow_short_selling: Literal[False]
    allow_margin: Literal[False]
    allow_leverage: Literal[False]
    allow_options: Literal[False]
    allow_crypto: Literal[False]
    allow_otc: Literal[False]
    min_price_usd: float = Field(ge=5.0)  # penny stocks are never eligible
    min_avg_daily_dollar_volume_usd: float = Field(ge=1_000_000)
    max_spread_bps: float = Field(gt=0, le=200)


class SessionPolicy(_Strict):
    regular_hours_only: Literal[True]
    no_new_positions_minutes_after_open: int = Field(ge=0, le=120)
    no_new_positions_minutes_before_close: int = Field(ge=0, le=120)
    block_entries_before_earnings_days: int = Field(ge=0, le=10)


class LimitsPolicy(_Strict):
    max_risk_per_trade_pct: float = Field(gt=0)
    max_daily_loss_pct: float = Field(gt=0)
    max_drawdown_pct: float = Field(gt=0)
    max_position_allocation_pct: float = Field(gt=0)
    max_concurrent_positions: int = Field(gt=0)
    max_sector_exposure_pct: float = Field(gt=0)
    max_gross_exposure_pct: float = Field(gt=0)
    max_new_trades_per_day: int = Field(gt=0)
    max_order_notional_usd: float = Field(gt=0)
    min_cash_buffer_usd: float = Field(ge=0)
    # After a drawdown halt, entries stay blocked this many sessions, then the HWM resets.
    drawdown_cooldown_sessions: int = Field(ge=5, le=250)

    @model_validator(mode="after")
    def _within_hard_limits(self) -> LimitsPolicy:
        violations = [
            f"{name}={getattr(self, name)} exceeds hard limit {ceiling}"
            for name, ceiling in HARD_LIMITS.items()
            if getattr(self, name) > ceiling
        ]
        if violations:
            raise ValueError("; ".join(violations))
        if self.max_position_allocation_pct > self.max_gross_exposure_pct:
            raise ValueError("max_position_allocation_pct cannot exceed max_gross_exposure_pct")
        return self


class DataQualityPolicy(_Strict):
    max_quote_age_seconds: float = Field(gt=0, le=300)
    max_bar_age_seconds: float = Field(gt=0, le=3600)
    reject_on_missing_data: Literal[True]


class ExecutionPolicy(_Strict):
    default_order_type: Literal["limit", "market"]
    limit_offset_bps: float = Field(ge=0, le=100)
    stop_slippage_assumption_bps: float = Field(ge=0)
    order_time_in_force: Literal["day"]


class BacktestPolicy(_Strict):
    # Floors: a validation backtest may not assume (near-)free trading.
    half_spread_bps: float = Field(ge=0.5, le=100)
    slippage_bps: float = Field(ge=1.0, le=200)
    sec_fee_per_million_usd: float = Field(ge=0, le=1000)
    finra_taf_per_share: float = Field(ge=0, le=0.01)
    finra_taf_max_per_trade_usd: float = Field(ge=0, le=100)
    max_participation_pct: float = Field(gt=0, le=10)


class PromotionGatesPolicy(_Strict):
    # Floors: gates can be tightened in policy.yaml, never loosened past these.
    min_history_years: float = Field(ge=3, le=30)
    min_trades: int = Field(ge=30)
    min_profit_factor: float = Field(ge=1.0)
    min_sharpe: float = Field(ge=0.0)
    max_drawdown_pct: float = Field(gt=0, le=25)
    holdout_years: float = Field(ge=1, le=5)
    holdout_min_trades: int = Field(ge=10)
    holdout_min_sharpe: float = Field(ge=0.0)
    walk_forward_window_months: int = Field(ge=3, le=24)
    min_profitable_windows_pct: float = Field(ge=50, le=100)
    min_stable_neighbors_pct: float = Field(ge=50, le=100)
    bootstrap_samples: int = Field(ge=500, le=100_000)
    bootstrap_confidence: float = Field(ge=0.9, lt=1)
    report_max_age_days: int = Field(ge=1, le=365)


class RiskPolicy(_Strict):
    version: int
    trading_mode: Literal["paper"]
    account: AccountPolicy
    instruments: InstrumentPolicy
    session: SessionPolicy
    limits: LimitsPolicy
    data_quality: DataQualityPolicy
    execution: ExecutionPolicy
    backtest: BacktestPolicy
    promotion_gates: PromotionGatesPolicy


class LoadedPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy: RiskPolicy
    path: str
    sha256: str


def load_policy(path: str | Path) -> LoadedPolicy:
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"policy file {path} must contain a mapping")
    return LoadedPolicy(
        policy=RiskPolicy.model_validate(data),
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


@lru_cache(maxsize=1)
def get_policy() -> LoadedPolicy:
    from atlas.core.configuration.settings import get_settings

    return load_policy(get_settings().policy_path)
