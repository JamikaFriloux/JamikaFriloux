"""SEC EDGAR company metadata: ticker -> CIK -> SIC code -> sector (no API key).

SEC's fair-access policy requires a descriptive User-Agent with contact details and at most
10 requests per second; this client sends the configured agent and spaces requests.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

from atlas.core.reference.sectors import sector_for_sic

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
MIN_INTERVAL = 0.15  # seconds between requests (< 10/s)


class EdgarError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompanyInfo:
    symbol: str
    cik: int
    name: str
    sic: int | None
    sector: str | None


class EdgarClient:
    def __init__(
        self,
        user_agent: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if "@" not in user_agent:
            raise EdgarError("SEC requires a User-Agent with a contact email address")
        self._client = client or httpx.Client(timeout=20.0)
        self._headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self._sleep = sleep
        self._last = 0.0

    def _get(self, url: str) -> object:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = time.monotonic()
        try:
            resp = self._client.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise EdgarError(type(exc).__name__) from exc
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise EdgarError(f"HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise EdgarError("invalid JSON") from exc

    def ticker_ciks(self) -> dict[str, int]:
        data = self._get(TICKERS_URL)
        if not isinstance(data, dict):
            raise EdgarError("unexpected company_tickers payload")
        out: dict[str, int] = {}
        for row in data.values():
            try:
                out.setdefault(str(row["ticker"]).upper(), int(row["cik_str"]))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def companies(self, symbols: Sequence[str]) -> list[CompanyInfo]:
        """Metadata for the symbols EDGAR knows; unknown tickers (often ETFs) are skipped."""
        ciks = self.ticker_ciks()
        out = []
        for sym in symbols:
            cik = ciks.get(sym.upper())
            if cik is None:
                continue
            data = self._get(SUBMISSIONS_URL.format(cik=cik))
            if not isinstance(data, dict):
                continue
            try:
                sic = int(data["sic"]) if data.get("sic") else None
            except (TypeError, ValueError):
                sic = None
            out.append(
                CompanyInfo(sym.upper(), cik, str(data.get("name") or ""), sic, sector_for_sic(sic))
            )
        return out
