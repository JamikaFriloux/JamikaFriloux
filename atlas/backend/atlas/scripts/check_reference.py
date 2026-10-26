"""Reference-data quality checks (Phase 7). Reads providers live; places no orders.

Usage (executor environment; reads ATLAS_REFDATA_* and the database):
    python -m atlas.scripts.check_reference

  [1] config/instruments.yaml loads and validates
  [2] SEC EDGAR reachable; every configured stock's sector cross-checked against its SIC code
      (disagreements are warnings: SIC -> GICS is approximate)
  [3] Finnhub earnings calendar reachable and plausible for the next 30 days
  [4] stored state: every watched symbol classified; a calendar fresh enough to clear stocks
      for today's blackout span; per-symbol clearance counts

Exit 0 when every hard check passes, 2 otherwise. Prints no secrets.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from atlas.core.configuration.policy import get_policy
from atlas.core.configuration.settings import RefDataSettings, get_settings
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import ingestion_symbols
from atlas.core.models.db import InstrumentReference
from atlas.core.models.session import session_scope
from atlas.core.reference.earnings import blackout_lookup, blackout_span, fresh_coverage
from atlas.core.reference.instruments import instruments_path, load_instruments


def main() -> int:
    hard: list[str] = []
    warn: list[str] = []
    ref = RefDataSettings()
    now = datetime.now(UTC)
    today = now.astimezone(NY).date()

    loaded = load_instruments(instruments_path(get_settings().policy_path))
    print(
        f"[1/4] instruments.yaml sha256={loaded.sha256[:12]}: "
        f"{len(loaded.data.etfs)} ETFs, {len(loaded.data.stocks)} stocks"
    )

    if not ref.sec_user_agent:
        hard.append("ATLAS_REFDATA_SEC_USER_AGENT not set")
        print("[2/4] SEC EDGAR: not configured")
    else:
        from atlas.integrations.sec.edgar import EdgarClient

        try:
            edgar = EdgarClient(ref.sec_user_agent)
            ciks = edgar.ticker_ciks()
            infos = {c.symbol: c for c in edgar.companies(sorted(loaded.data.stocks))}
            print(f"[2/4] SEC EDGAR reachable: {len(ciks)} tickers")
            for sym, entry in sorted(loaded.data.stocks.items()):
                info = infos.get(sym)
                if info is None:
                    warn.append(f"{sym}: not found in EDGAR")
                elif info.sector != entry.sector:
                    warn.append(
                        f"{sym}: config '{entry.sector}' vs EDGAR SIC {info.sic} "
                        f"-> '{info.sector}' ({info.name})"
                    )
            listed_etfs = sorted(s for s in loaded.data.etfs if s in ciks)
            print(f"      ETFs with an EDGAR ticker entry (informational): {listed_etfs or 'none'}")
        except Exception as exc:
            hard.append(f"SEC EDGAR: {str(exc)[:120] or type(exc).__name__}")
            print("[2/4] SEC EDGAR: FAILED")

    if ref.finnhub_api_key is None:
        hard.append("ATLAS_REFDATA_FINNHUB_API_KEY not set: stocks get no earnings clearance")
        print("[3/4] Finnhub: not configured")
    else:
        from atlas.integrations.finnhub.earnings import FinnhubEarnings

        try:
            end = today + timedelta(days=30)
            items = FinnhubEarnings(ref.finnhub_api_key.get_secret_value()).calendar(today, end)
            outside = [i for i in items if not today <= i.day <= end]
            print(
                f"[3/4] Finnhub reachable: {len(items)} reports {today} -> {end}; "
                f"timing {dict(Counter(i.timing for i in items))}"
            )
            if not items:
                hard.append("Finnhub returned an empty 30-day calendar (implausible)")
            if outside:
                hard.append(f"Finnhub returned {len(outside)} reports outside the window")
        except Exception as exc:
            hard.append(f"Finnhub: {str(exc)[:120] or type(exc).__name__}")
            print("[3/4] Finnhub: FAILED")

    cal = MarketCalendar()
    days = get_policy().policy.session.block_entries_before_earnings_days
    with session_scope() as s:
        watched = ingestion_symbols(s, get_settings().ingest_default_symbols)
        classified = set(s.scalars(select(InstrumentReference.symbol)).all())
        missing = sorted(set(watched) - classified)
        if missing:
            hard.append(f"unclassified watched symbols: {missing}")
        span = blackout_span(today, days, cal) or [today]
        max_age = timedelta(hours=ref.earnings_max_age_hours)
        cov = fresh_coverage(s, start=span[0], end=span[-1], now=now, max_age=max_age)
        if cov is None:
            hard.append(f"no earnings calendar fetched within {ref.earnings_max_age_hours} h")
        lookup = blackout_lookup(s, now=now, today=today, days=days, calendar=cal, max_age=max_age)
        clearance = Counter(
            "unknown" if (v := lookup(sym)) is None else ("blackout" if v else "clear")
            for sym in watched
        )
        print(
            f"[4/4] {len(watched)} watched symbols, {len(missing)} unclassified; blackout span "
            f"{span[0]}..{span[-1]}; calendar {'fresh' if cov else 'missing/stale'}; "
            f"clearance {dict(clearance)}"
        )

    for w in warn:
        print("WARN ", w)
    for h in hard:
        print("FAIL ", h)
    print("RESULT", "OK" if not hard else f"{len(hard)} failing check(s)")
    return 0 if not hard else 2


if __name__ == "__main__":
    raise SystemExit(main())
