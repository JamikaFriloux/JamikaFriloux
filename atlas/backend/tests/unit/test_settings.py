import pytest
from pydantic import SecretStr, ValidationError

from atlas.core.configuration.settings import AtlasSettings, BrokerSettings


def _broker(**kw):
    base = {
        "api_key_id": SecretStr("PKTESTKEY123"),
        "api_secret_key": SecretStr("s"),
        "_env_file": None,
    }
    base.update(kw)
    return BrokerSettings(**base)


def test_broker_settings_default_to_paper():
    assert _broker().base_url == "https://paper-api.alpaca.markets"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.alpaca.markets",
        "https://broker-api.alpaca.markets",
        "http://paper-api.alpaca.markets",
        "https://paper-api.alpaca.markets.evil.com",
    ],
)
def test_live_or_unknown_endpoints_rejected(url):
    with pytest.raises(ValidationError):
        _broker(base_url=url)


def test_live_looking_key_rejected():
    with pytest.raises(ValidationError):
        _broker(api_key_id=SecretStr("AKLIVEKEY123"))


def test_trading_mode_cannot_be_live():
    with pytest.raises(ValidationError):
        AtlasSettings(trading_mode="live", _env_file=None)  # type: ignore[arg-type]


def test_production_requires_strong_jwt_secret():
    with pytest.raises(ValidationError):
        AtlasSettings(environment="production", jwt_secret=SecretStr("short"), _env_file=None)
    AtlasSettings(environment="production", jwt_secret=SecretStr("y" * 40), _env_file=None)


def test_secrets_not_in_repr():
    s = _broker(api_secret_key=SecretStr("supersecretvalue"))
    assert "supersecretvalue" not in repr(s)
