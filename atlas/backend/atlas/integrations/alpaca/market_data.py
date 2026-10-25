"""Alpaca historical market data adapter (read-only data API).

Uses the same paper key pair as the trading gateway, so it also runs inside the execution
service / data-ingestion worker that holds those credentials. Bars are returned as validated
``BarRecord`` objects tagged with their source and adjustment so nothing downstream has to
guess where data came from.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from atlas.core.configuration.settings import BrokerSettings
from atlas.core.data.bars import BarRecord, Timeframe

_TF = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


class AlpacaMarketData:
    def __init__(self, client: StockHistoricalDataClient, feed: str = "iex"):
        self._client = client
        self._feed = DataFeed(feed)

    @classmethod
    def from_settings(cls, settings: BrokerSettings, feed: str | None = None) -> AlpacaMarketData:
        client = StockHistoricalDataClient(
            api_key=settings.api_key_id.get_secret_value(),
            secret_key=settings.api_secret_key.get_secret_value(),
        )
        return cls(client, feed or settings.data_feed)

    @property
    def source(self) -> str:
        return f"alpaca_{self._feed.value}"

    def get_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        adjustment: str = "all",
    ) -> dict[str, list[BarRecord]]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start/end must be timezone-aware")
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=_TF[timeframe],
            start=start,
            end=end,
            adjustment=Adjustment(adjustment),
            feed=self._feed,
        )
        result = self._client.get_stock_bars(req)
        data: dict[str, list[Any]] = getattr(result, "data", {}) or {}
        out: dict[str, list[BarRecord]] = {}
        for symbol, bars in data.items():
            out[symbol] = [
                BarRecord(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=b.timestamp,
                    open=Decimal(str(b.open)),
                    high=Decimal(str(b.high)),
                    low=Decimal(str(b.low)),
                    close=Decimal(str(b.close)),
                    volume=Decimal(str(b.volume)),
                    vwap=_dec(b.vwap),
                    trade_count=int(b.trade_count) if b.trade_count is not None else None,
                    source=self.source,
                    adjustment=adjustment,  # type: ignore[arg-type]
                )
                for b in bars
            ]
        return out
