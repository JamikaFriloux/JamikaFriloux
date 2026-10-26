"""Alpaca news adapter (read-only data API, executor only: it uses the paper key pair)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from atlas.core.configuration.settings import BrokerSettings
from atlas.core.data.news import NewsItem

MAX_ITEMS = 500


def _ts(v: Any) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def parse(raw: dict[str, Any]) -> NewsItem | None:
    published = _ts(raw.get("created_at"))
    if published is None or not raw.get("id") or not raw.get("headline"):
        return None
    return NewsItem(
        source="alpaca",
        provider_id=str(raw["id"]),
        published_at=published,
        updated_at=_ts(raw.get("updated_at")),
        headline=str(raw["headline"]),
        summary=str(raw.get("summary") or ""),
        provider=raw.get("source") or None,
        url=raw.get("url") or None,
        symbols=tuple(str(s) for s in raw.get("symbols") or []),
    )


class AlpacaNews:
    def __init__(self, client: NewsClient):
        self._client = client

    @classmethod
    def from_settings(cls, settings: BrokerSettings) -> AlpacaNews:
        return cls(
            NewsClient(
                api_key=settings.api_key_id.get_secret_value(),
                secret_key=settings.api_secret_key.get_secret_value(),
                raw_data=True,  # parse ourselves; the SDK models lag the API
            )
        )

    def get_news(self, symbols: Sequence[str], start: datetime, end: datetime) -> list[NewsItem]:
        # The SDK follows next_page_token itself until ``limit`` items are collected.
        resp: Any = self._client.get_news(
            NewsRequest(
                symbols=",".join(symbols),
                start=start,
                end=end,
                limit=MAX_ITEMS,
                sort="desc",
                include_content=False,
            )
        )
        items = (parse(raw) for raw in resp.get("news", []))
        return [it for it in items if it is not None]
