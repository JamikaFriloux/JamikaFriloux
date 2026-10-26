"""Verify the Alpaca PAPER integration end-to-end without placing any order.

Usage (inside the executor environment, where ALPACA_* is set):
    python -m atlas.scripts.check_alpaca [--symbol SPY]

Checks: credentials load and pass the paper-only validators, the trading client resolves to
the paper endpoint, the account is a paper account, the clock/calendar agree with XNYS,
recent daily bars are retrievable and pass data validation. Prints no secrets.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from alpaca.trading.client import TradingClient
from alpaca.trading.models import Calendar, Clock
from alpaca.trading.requests import GetCalendarRequest

from atlas.core.configuration.settings import BrokerSettings
from atlas.core.data.bars import validate_bars
from atlas.core.data.calendar import NY, MarketCalendar, compare_with_broker_calendar
from atlas.integrations.alpaca.market_data import AlpacaMarketData
from atlas.integrations.alpaca.trading import verify_paper_environment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    args = parser.parse_args(argv)

    settings = BrokerSettings()  # type: ignore[call-arg]
    print("[1/5] credentials loaded; base URL:", settings.base_url)
    client = TradingClient(
        settings.api_key_id.get_secret_value(),
        settings.api_secret_key.get_secret_value(),
        paper=True,
    )
    account = verify_paper_environment(client)
    print(
        f"[2/5] PAPER account verified: status={account.status} equity={account.equity} "
        f"cash={account.cash} buying_power={account.buying_power}"
    )

    # Policy is long-only, no margin. The broker accepts stop-sells without a position, so a
    # stale protective stop could open a short unless shorting is disabled on the account.
    raw = cast(dict[str, Any], client.get("/account"))
    shorting, multiplier = raw.get("shorting_enabled"), raw.get("multiplier")
    guard_ok = shorting is False
    print(
        f"[2b] broker guardrails: shorting_enabled={shorting} multiplier={multiplier} -> "
        + (
            "OK"
            if guard_ok
            else "WARN: entries are rejected until shorting is disabled "
            "(Alpaca dashboard > Account > Configure, or PATCH /v2/account/configurations "
            '{"no_shorting": true, "max_margin_multiplier": "1"})'
        )
    )

    clock = cast(Clock, client.get_clock())
    print(f"[3/5] broker clock: is_open={clock.is_open} next_open={clock.next_open}")

    today = datetime.now(UTC).date()
    cal_rows = cast(
        list[Calendar],
        client.get_calendar(GetCalendarRequest(start=today, end=today + timedelta(days=30))),
    )
    broker_sessions = [
        (
            row.date,
            row.open.replace(tzinfo=NY).astimezone(UTC) if row.open.tzinfo is None else row.open,
            row.close.replace(tzinfo=NY).astimezone(UTC) if row.close.tzinfo is None else row.close,
        )
        for row in cal_rows
    ]
    issues = compare_with_broker_calendar(MarketCalendar(), broker_sessions)
    print(
        f"[4/5] calendar cross-check over {len(broker_sessions)} sessions: "
        + ("OK" if not issues else f"{len(issues)} discrepancies: {issues[:3]}")
    )

    md = AlpacaMarketData.from_settings(settings)
    now = datetime.now(UTC)
    bars = md.get_bars([args.symbol], "1Day", now - timedelta(days=20), now - timedelta(minutes=16))
    series = bars.get(args.symbol, [])
    report = validate_bars(series, now=now)
    last = series[-1] if series else None
    print(
        f"[5/5] {len(series)} daily bars for {args.symbol} from {md.source}; "
        f"last={last.ts.isoformat() if last else None} close={last.close if last else None}; "
        f"validation_ok={report.ok} issues={[i.code for i in report.issues]}"
    )
    return 0 if report.ok and not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
