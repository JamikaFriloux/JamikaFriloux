"""Finnhub earnings calendar (needs ATLAS_REFDATA_FINNHUB_API_KEY).

The key travels in the ``X-Finnhub-Token`` header, never in the URL, so it can't leak into
logs. A fetch either returns the complete calendar for the window or raises; callers store
coverage only for complete fetches.
"""

from __future__ import annotations

from datetime import date

import httpx

from atlas.core.reference.earnings import EarningsItem

URL = "https://finnhub.io/api/v1/calendar/earnings"
SOURCE = "finnhub"
TIMINGS = {"bmo": "bmo", "amc": "amc", "dmh": "dmh"}


class FinnhubError(RuntimeError):
    pass


class FinnhubEarnings:
    source = SOURCE

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise FinnhubError("no API key")
        self._client = client or httpx.Client(timeout=30.0)
        self._headers = {"X-Finnhub-Token": api_key}

    def calendar(self, start: date, end: date) -> list[EarningsItem]:
        try:
            resp = self._client.get(
                URL,
                params={"from": start.isoformat(), "to": end.isoformat()},
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise FinnhubError(type(exc).__name__) from exc
        if resp.status_code != 200:
            raise FinnhubError(f"HTTP {resp.status_code}")
        try:
            rows = resp.json()["earningsCalendar"]
        except (ValueError, KeyError, TypeError) as exc:
            raise FinnhubError("unexpected payload") from exc
        if not isinstance(rows, list):
            raise FinnhubError("unexpected payload")
        out = []
        for r in rows:
            try:
                day = date.fromisoformat(str(r["date"]))
                symbol = str(r["symbol"]).strip().upper()
            except (KeyError, TypeError, ValueError):
                continue  # one malformed row doesn't invalidate the rest
            if symbol:
                out.append(
                    EarningsItem(symbol, day, TIMINGS.get(str(r.get("hour") or ""), "unknown"))
                )
        return out
