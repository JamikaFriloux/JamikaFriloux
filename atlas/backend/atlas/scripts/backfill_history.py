"""Load long daily history (adjusted and raw, SIP) for backtest validation.

Run once in the executor environment (it needs the broker credentials), then the daily
ingestion keeps the most recent ~400 days current:
    python -m atlas.scripts.backfill_history [--years 10]

Scope: benchmarks plus all watchlist symbols. Data quality reports are recorded as usual.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from atlas.apps.executor.tasks import get_sip_bar_source
from atlas.core.configuration.settings import get_settings
from atlas.core.data.ingestion import ingest_bars, ingestion_symbols
from atlas.core.models.session import session_scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=float, default=10.0)
    args = parser.parse_args(argv)
    settings = get_settings()
    now = datetime.now(UTC) - timedelta(minutes=16)  # free plan: SIP up to 15 minutes ago
    source = get_sip_bar_source()
    ok = True
    with session_scope() as s:
        symbols = ingestion_symbols(s, settings.ingest_default_symbols)
        for adjustment in ("all", "raw"):
            result = ingest_bars(
                s,
                source,
                symbols,
                "1Day",
                now=now,
                lookback=timedelta(days=int(365.25 * args.years)),
                incremental=False,
                adjustment=adjustment,
            )
            ok = ok and result.ok
            print(
                f"{adjustment}: {len(symbols)} symbols, {result.bars_written} bars, "
                f"failed={result.failed_symbols} stale={result.stale_symbols}"
            )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
