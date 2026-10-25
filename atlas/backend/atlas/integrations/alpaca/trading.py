"""Alpaca PAPER trading gateway.

Live trading is technically inaccessible from this module:
  * the TradingClient is always constructed with ``paper=True``;
  * BrokerSettings rejects any base URL other than the paper endpoint and live-looking keys;
  * ``verify_paper_environment`` checks the client's resolved URL and the account number
    (Alpaca paper account numbers start with "PA") before the gateway is used.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests
from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, LimitOrderRequest

from atlas.core.configuration.settings import PAPER_TRADING_BASE_URL, BrokerSettings
from atlas.core.data.universe import AssetInfo
from atlas.core.execution.broker import (
    AccountInfo,
    BrokerError,
    BrokerOrder,
    BrokerRejected,
    BrokerUncertain,
    DuplicateClientOrderId,
    OrderRequest,
    PositionInfo,
)
from atlas.core.observability.logging import get_logger

log = get_logger(__name__)


class LiveEnvironmentDetected(RuntimeError):
    pass


def _d(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(0)


def _translate(exc: Exception) -> BrokerError:
    if isinstance(exc, APIError):
        status = exc.status_code
        text = str(exc).lower()
        if "client_order_id" in text and ("unique" in text or "exist" in text):
            return DuplicateClientOrderId(str(exc))
        if status is not None and 400 <= status < 500 and status not in (408, 429):
            return BrokerRejected(f"broker rejected request (HTTP {status})")
        return BrokerUncertain(f"broker error (HTTP {status})")
    if isinstance(exc, requests.exceptions.RequestException | TimeoutError | ConnectionError):
        return BrokerUncertain(type(exc).__name__)
    return BrokerUncertain(type(exc).__name__)


def _order(o: Any) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=str(o.id),
        client_order_id=o.client_order_id,
        symbol=o.symbol,
        side=getattr(o.side, "value", str(o.side)),
        status=getattr(o.status, "value", str(o.status)),
        qty=_d(o.qty),
        filled_qty=_d(o.filled_qty),
        filled_avg_price=_d(o.filled_avg_price) if o.filled_avg_price is not None else None,
    )


def verify_paper_environment(client: TradingClient) -> AccountInfo:
    base_obj = getattr(client, "_base_url", None)
    base = str(getattr(base_obj, "value", base_obj) or "").rstrip("/")
    if base != PAPER_TRADING_BASE_URL:
        raise LiveEnvironmentDetected(f"trading client points at {base!r}")
    gateway = AlpacaPaperGateway(client)
    account = gateway.get_account()
    if not account.is_paper:
        raise LiveEnvironmentDetected("account number is not a paper account")
    return account


class AlpacaPaperGateway:
    def __init__(self, client: TradingClient):
        self._client = client

    @classmethod
    def from_settings(cls, settings: BrokerSettings) -> AlpacaPaperGateway:
        client = TradingClient(
            api_key=settings.api_key_id.get_secret_value(),
            secret_key=settings.api_secret_key.get_secret_value(),
            paper=True,
        )
        verify_paper_environment(client)
        return cls(client)

    def _call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            raise _translate(exc) from exc

    def get_account(self) -> AccountInfo:
        a = self._call(self._client.get_account)
        return AccountInfo(
            account_number=str(a.account_number),
            status=getattr(a.status, "value", str(a.status)),
            equity=_d(a.equity),
            last_equity=_d(a.last_equity),
            cash=_d(a.cash),
            buying_power=_d(a.buying_power),
            long_market_value=_d(a.long_market_value),
            trading_blocked=bool(a.trading_blocked or a.account_blocked),
            is_paper=str(a.account_number).upper().startswith("PA"),
        )

    def list_positions(self) -> list[PositionInfo]:
        return [
            PositionInfo(
                symbol=p.symbol,
                qty=_d(p.qty),
                avg_entry_price=_d(p.avg_entry_price),
                market_value=_d(p.market_value),
                unrealized_pl=_d(p.unrealized_pl),
                current_price=_d(p.current_price) if p.current_price is not None else None,
            )
            for p in self._call(self._client.get_all_positions)
        ]

    def list_open_orders(self) -> list[BrokerOrder]:
        orders = self._call(
            self._client.get_orders, GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
        )
        return [_order(o) for o in orders]

    def get_order_by_client_id(self, client_order_id: str) -> BrokerOrder | None:
        try:
            return _order(self._client.get_order_by_client_id(client_order_id))
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise _translate(exc) from exc
        except Exception as exc:
            raise _translate(exc) from exc

    def submit_limit_order(self, request: OrderRequest) -> BrokerOrder:
        if request.side not in ("buy", "sell"):
            raise BrokerRejected("invalid side")
        req = LimitOrderRequest(
            symbol=request.symbol,
            qty=float(request.qty),
            side=OrderSide.BUY if request.side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=float(request.limit_price),
            client_order_id=request.client_order_id,
            extended_hours=False,
        )
        return _order(self._call(self._client.submit_order, req))

    def cancel_all_open_orders(self) -> list[str]:
        responses = self._call(self._client.cancel_orders) or []
        return [str(getattr(r, "id", "")) for r in responses]

    def list_assets(self) -> list[AssetInfo]:
        """Active US equities. Read as raw JSON: alpaca-py's Asset model rejects exchange codes
        it doesn't know yet (e.g. "TXSE"), which would fail the whole listing."""
        raw = self._call(
            self._client.get, "/assets", {"status": "active", "asset_class": "us_equity"}
        )
        return [
            AssetInfo(
                symbol=str(a["symbol"]),
                name=str(a.get("name") or ""),
                exchange=str(a.get("exchange") or ""),
                asset_class=str(a.get("class") or ""),
                status=str(a.get("status") or ""),
                tradable=bool(a.get("tradable")),
                fractionable=bool(a.get("fractionable")),
                shortable=bool(a.get("shortable")),
                easy_to_borrow=bool(a.get("easy_to_borrow")),
            )
            for a in raw or []
        ]
