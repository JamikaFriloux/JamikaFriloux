from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from atlas.core.configuration.policy import HARD_LIMITS, RiskPolicy, load_policy


def _raw(settings) -> dict:
    return yaml.safe_load(Path(settings.policy_path).read_text())


def test_default_policy_matches_spec(policy):
    p = policy.policy
    assert p.trading_mode == "paper"
    assert p.account.starting_equity_usd == 10_000
    lim = p.limits
    assert lim.max_risk_per_trade_pct == 0.25
    assert lim.max_daily_loss_pct == 1.0
    assert lim.max_drawdown_pct == 5.0
    assert lim.max_position_allocation_pct == 10.0
    assert lim.max_concurrent_positions == 5
    assert lim.max_sector_exposure_pct == 25.0
    assert lim.max_gross_exposure_pct == 50.0
    assert lim.max_new_trades_per_day == 5
    assert p.instruments.min_price_usd == 10.0
    assert p.instruments.min_avg_daily_dollar_volume_usd == 20_000_000
    assert p.instruments.long_only and not p.instruments.allow_short_selling
    assert len(policy.sha256) == 64


@pytest.mark.parametrize("name", list(HARD_LIMITS))
def test_hard_limits_cannot_be_exceeded(settings, name):
    raw = _raw(settings)
    raw["limits"][name] = HARD_LIMITS[name] * 2
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(raw)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("instruments", "allow_short_selling", True),
        ("instruments", "allow_margin", True),
        ("instruments", "allow_leverage", True),
        ("instruments", "allow_options", True),
        ("instruments", "allow_crypto", True),
        ("instruments", "long_only", False),
        ("instruments", "min_price_usd", 1.0),
        ("session", "regular_hours_only", False),
        ("data_quality", "reject_on_missing_data", False),
        (None, "trading_mode", "live"),
        # Validation backtests can't assume free trading or loosened gates.
        ("backtest", "slippage_bps", 0.0),
        ("backtest", "half_spread_bps", 0.0),
        ("promotion_gates", "min_trades", 5),
        ("promotion_gates", "min_profit_factor", 0.8),
        ("promotion_gates", "bootstrap_confidence", 0.5),
        ("promotion_gates", "holdout_years", 0),
        ("promotion_gates", "report_max_age_days", 3650),
    ],
)
def test_structural_restrictions_enforced(settings, section, key, value):
    raw = _raw(settings)
    (raw[section] if section else raw)[key] = value
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(raw)


def test_unknown_keys_rejected(settings):
    raw = _raw(settings)
    raw["limits"]["max_risk_per_trade_pct_typo"] = 1
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(raw)


def test_policy_hash_changes_with_content(tmp_path, settings):
    a = tmp_path / "a.yaml"
    a.write_text(Path(settings.policy_path).read_text())
    b = tmp_path / "b.yaml"
    b.write_text(Path(settings.policy_path).read_text() + "\n# comment\n")
    assert load_policy(a).sha256 != load_policy(b).sha256
