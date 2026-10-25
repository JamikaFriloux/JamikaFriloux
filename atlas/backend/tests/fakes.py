"""Deterministic in-memory broker for failure-scenario tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from atlas.core.data.bars import BarRecord
from atlas.core.data.universe import AssetInfo
from atlas.core.execution.broker import (
    AccountInfo,
    BrokerOrder,
    DuplicateClientOrderId,
    OrderRequest,
    PositionInfo,
)


class FakeBroker:
    def __init__(self) -> None:
        self.orders: dict[str, BrokerOrder] = {}
        self.positions: list[PositionInfo] = []
        self.account = AccountInfo(
            account_number="PA1234567",
            status="ACTIVE",
            equity=Decimal("10000"),
            last_equity=Decimal("9950"),
            cash=Decimal("10000"),
            buying_power=Decimal("20000"),
            long_market_value=Decimal("0"),
            trading_blocked=False,
            is_paper=True,
        )
        self.submit_calls = 0
        self.lookup_calls = 0
        # Hooks to inject failures. Each receives the request/cid and may raise.
        self.on_submit: list[Callable[[OrderRequest], None]] = []
        self.on_lookup: list[Callable[[str], None]] = []
        self.accept_then_fail = False  # simulate "accepted but response lost"
        self.cancel_error: Exception | None = None

    def get_account(self) -> AccountInfo:
        return self.account

    def list_positions(self) -> list[PositionInfo]:
        return list(self.positions)

    def list_open_orders(self) -> list[BrokerOrder]:
        return [
            o for o in self.orders.values() if o.status in ("new", "accepted", "partially_filled")
        ]

    def get_order_by_client_id(self, client_order_id: str) -> BrokerOrder | None:
        self.lookup_calls += 1
        if self.on_lookup:
            self.on_lookup.pop(0)(client_order_id)
        return self.orders.get(client_order_id)

    def submit_limit_order(self, request: OrderRequest) -> BrokerOrder:
        self.submit_calls += 1
        if request.client_order_id in self.orders:
            raise DuplicateClientOrderId(request.client_order_id)
        hook = self.on_submit.pop(0) if self.on_submit else None
        if hook is not None and not self.accept_then_fail:
            hook(request)
        order = BrokerOrder(
            broker_order_id=str(uuid.uuid4()),
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            status="new",
            qty=request.qty,
            filled_qty=Decimal(0),
            filled_avg_price=None,
        )
        self.orders[request.client_order_id] = order
        if hook is not None and self.accept_then_fail:
            hook(request)
        return order

    def cancel_all_open_orders(self) -> list[str]:
        if self.cancel_error:
            raise self.cancel_error
        cancelled = []
        for cid, o in list(self.orders.items()):
            if o.status in ("new", "accepted", "partially_filled"):
                self.orders[cid] = BrokerOrder(**{**o.__dict__, "status": "canceled"})
                cancelled.append(o.broker_order_id)
        return cancelled

    def set_status(
        self, cid: str, status: str, filled: str = "0", price: str | None = None
    ) -> None:
        o = self.orders[cid]
        self.orders[cid] = BrokerOrder(
            **{
                **o.__dict__,
                "status": status,
                "filled_qty": Decimal(filled),
                "filled_avg_price": Decimal(price) if price else None,
            }
        )


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []
        self.events: list[object] = []

    def send(self, text: str, *, critical: bool = False) -> bool:
        self.messages.append((text, critical))
        return True

    def notify(self, event: object, text: str, *, critical: bool = False) -> bool:
        self.events.append(event)
        return self.send(text, critical=critical)


class FakeBarSource:
    """In-memory bar source. ``bars`` maps symbol -> full history; requests are windowed."""

    source = "fake_feed"

    def __init__(self, bars: dict[str, list[BarRecord]] | None = None) -> None:
        self.bars = bars or {}
        self.calls: list[tuple[list[str], str, datetime, datetime]] = []
        self.error: Exception | None = None

    def get_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment: str = "all",
    ) -> dict[str, list[BarRecord]]:
        self.calls.append((list(symbols), timeframe, start, end))
        if self.error is not None:
            raise self.error
        out = {}
        for sym in symbols:
            series = [
                b
                for b in self.bars.get(sym, [])
                if b.timeframe == timeframe and start <= b.ts <= end
            ]
            if series:
                out[sym] = series
        return out


def make_bar(
    symbol: str,
    ts: datetime,
    timeframe: str = "1Day",
    close: str = "100",
    *,
    high: str | None = None,
) -> BarRecord:
    c = Decimal(close)
    return BarRecord(
        symbol=symbol,
        timeframe=timeframe,  # type: ignore[arg-type]
        ts=ts,
        open=c,
        high=Decimal(high) if high else c + 1,
        low=c - 1,
        close=c,
        volume=Decimal(1000),
        source="fake_feed",
        adjustment="all",
    )


class FakeAssetSource:
    def __init__(self, assets: list[AssetInfo]) -> None:
        self.assets = assets
        self.error: Exception | None = None

    def list_assets(self) -> list[AssetInfo]:
        if self.error is not None:
            raise self.error
        return list(self.assets)


def make_asset(symbol: str, exchange: str = "NASDAQ", **kw: object) -> AssetInfo:
    fields: dict[str, object] = {
        "symbol": symbol,
        "name": f"{symbol} Inc",
        "exchange": exchange,
        "asset_class": "us_equity",
        "status": "active",
        "tradable": True,
        "fractionable": True,
    }
    fields.update(kw)
    return AssetInfo(**fields)  # type: ignore[arg-type]


def daily_series(
    symbol: str, days: list, close: str = "50", volume: str = "1000000"
) -> list[BarRecord]:
    """One raw daily bar per session date, stamped at midnight New York like Alpaca."""
    from atlas.core.data.calendar import NY

    c = Decimal(close)
    return [
        BarRecord(
            symbol=symbol,
            timeframe="1Day",
            ts=datetime(d.year, d.month, d.day, tzinfo=NY),
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=Decimal(volume),
            source="fake_sip",
            adjustment="raw",
        )
        for d in days
    ]
