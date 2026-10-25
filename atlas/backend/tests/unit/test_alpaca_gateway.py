import json
from types import SimpleNamespace

import pytest
import requests
from alpaca.common.exceptions import APIError

from atlas.core.execution.broker import BrokerRejected, BrokerUncertain, DuplicateClientOrderId
from atlas.integrations.alpaca.trading import (
    AlpacaPaperGateway,
    LiveEnvironmentDetected,
    _translate,
    verify_paper_environment,
)


def _api_error(status, message="err"):
    http = SimpleNamespace(response=SimpleNamespace(status_code=status))
    return APIError(json.dumps({"code": status, "message": message}), http)


def test_error_translation():
    assert isinstance(_translate(_api_error(403, "insufficient buying power")), BrokerRejected)
    assert isinstance(
        _translate(_api_error(422, "client_order_id must be unique")), DuplicateClientOrderId
    )
    assert isinstance(_translate(_api_error(429)), BrokerUncertain)
    assert isinstance(_translate(_api_error(503)), BrokerUncertain)
    assert isinstance(_translate(requests.exceptions.ReadTimeout()), BrokerUncertain)


def _account(number):
    return SimpleNamespace(
        account_number=number,
        status="ACTIVE",
        equity="10000",
        last_equity="10000",
        cash="10000",
        buying_power="20000",
        long_market_value="0",
        trading_blocked=False,
        account_blocked=False,
    )


class _Client:
    def __init__(self, url, number):
        self._base_url = SimpleNamespace(value=url)
        self._number = number

    def get_account(self):
        return _account(self._number)


def test_verify_accepts_paper():
    acct = verify_paper_environment(_Client("https://paper-api.alpaca.markets", "PA3XYZ"))
    assert acct.is_paper


def test_verify_rejects_live_url():
    with pytest.raises(LiveEnvironmentDetected):
        verify_paper_environment(_Client("https://api.alpaca.markets", "PA3XYZ"))


def test_verify_rejects_live_account_number():
    with pytest.raises(LiveEnvironmentDetected):
        verify_paper_environment(_Client("https://paper-api.alpaca.markets", "123456"))


def test_real_sdk_client_resolves_to_paper():
    from alpaca.trading.client import TradingClient

    c = TradingClient("PKTEST", "secret", paper=True)
    assert c._base_url.value == "https://paper-api.alpaca.markets"


def test_lookup_404_returns_none():
    class C:
        def get_order_by_client_id(self, _):
            raise _api_error(404, "order not found")

    assert AlpacaPaperGateway(C()).get_order_by_client_id("x") is None  # type: ignore[arg-type]


def test_list_assets_parses_raw_json_including_unknown_exchanges():
    from atlas.integrations.alpaca.trading import AlpacaPaperGateway

    class Client:
        def get(self, path, params):
            assert path == "/assets" and params == {"status": "active", "asset_class": "us_equity"}
            return [
                {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "class": "us_equity",
                 "status": "active", "tradable": True, "fractionable": True, "shortable": True,
                 "easy_to_borrow": True},
                {"symbol": "NEWCO", "name": None, "exchange": "TXSE", "class": "us_equity",
                 "status": "active", "tradable": True},
            ]  # fmt: skip

    assets = AlpacaPaperGateway(Client()).list_assets()  # type: ignore[arg-type]
    assert [a.symbol for a in assets] == ["AAPL", "NEWCO"]
    assert assets[1].exchange == "TXSE" and assets[1].name == "" and not assets[1].shortable
