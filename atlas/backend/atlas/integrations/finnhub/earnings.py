"""Finnhub earnings calendar (needs ATLAS_REFDATA_FINNHUB_API_KEY).

The key travels in the ``X-Finnhub-Token`` header, never in the URL, so it can't leak into
logs. A fetch either returns the complete calendar for the window or raises; callers store
coverage only for complete fetches.

Two quirks of the market-wide calendar, both checked live on 2026-10-26, make "absent from
the calendar" unsafe on its own:

* A response is silently truncated at ``ROW_CAP`` rows, keeping the latest dates: a 30-day
  request returned only its last 16 days. So the calendar is fetched one day per request and
  a day that reaches the cap is an error.
* It lists one share class per issuer: GOOGL appeared on 2026-10-28, GOOG did not. A query
  for GOOG returns that report labelled GOOGL. So the symbols ATLAS trades are also queried
  one by one, and each answer is stored under the symbol that was asked for.

Requests are spaced to stay under the free tier's 60 calls per minute.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Any

import httpx

from atlas.core.reference.earnings import EarningsItem

URL = "https://finnhub.io/api/v1/calendar/earnings"
SOURCE = "finnhub"
TIMINGS = {"bmo": "bmo", "amc": "amc", "dmh": "dmh"}
ROW_CAP = 1500
MIN_INTERVAL = 1.1  # seconds between requests (< 60/min, with margin for a concurrent check)


class FinnhubError(RuntimeError):
    pass


class FinnhubEarnings:
    source = SOURCE

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise FinnhubError("no API key")
        self._client = client or httpx.Client(timeout=30.0)
        self._headers = {"X-Finnhub-Token": api_key}
        self._sleep = sleep
        self._last = 0.0

    def calendar(self, start: date, end: date, symbols: Sequence[str] = ()) -> list[EarningsItem]:
        """Every report in ``start..end``: the market-wide calendar day by day, plus a
        per-symbol query for each of ``symbols``. Raises unless every request succeeded."""
        out: list[EarningsItem] = []
        day = start
        while day <= end:
            rows = self._rows({"from": day.isoformat(), "to": day.isoformat()})
            if len(rows) >= ROW_CAP:
                raise FinnhubError(f"truncated response for {day.isoformat()} ({len(rows)} rows)")
            items = _parse(rows)
            if any(it.day != day for it in items):
                raise FinnhubError(f"row outside the {day.isoformat()} window")
            out.extend(items)
            day += timedelta(days=1)
        for sym in symbols:
            items = _parse(
                self._rows({"symbol": sym, "from": start.isoformat(), "to": end.isoformat()})
            )
            # Finnhub answers a share-class query with the issuer's row (GOOG -> "GOOGL"), so
            # every row is that issuer's report and is stored under the queried symbol.
            out.extend(
                EarningsItem(sym.upper(), it.day, it.timing)
                for it in items
                if start <= it.day <= end
            )
        return out

    def _rows(self, params: dict[str, str]) -> list[Any]:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = time.monotonic()
        try:
            resp = self._client.get(URL, params=params, headers=self._headers)
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
        return rows


def _parse(rows: list[Any]) -> list[EarningsItem]:
    out = []
    for r in rows:
        try:
            day = date.fromisoformat(str(r["date"]))
            symbol = str(r["symbol"]).strip().upper()
            hour = str(r.get("hour") or "")
        except (KeyError, TypeError, ValueError, AttributeError):
            continue  # one malformed row doesn't invalidate the rest
        if symbol:
            out.append(EarningsItem(symbol, day, TIMINGS.get(hour, "unknown")))
    return out
