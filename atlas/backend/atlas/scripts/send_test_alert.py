"""Send one Telegram test alert and say whether it arrived. Places no orders.

Usage (any backend container; reads ATLAS_TELEGRAM_* from .env):
    python -m atlas.scripts.send_test_alert

Exit 0 when Telegram accepted the message, 2 when Telegram isn't configured, 3 when the
message was refused or Telegram couldn't be reached. On a refusal it checks the bot token
separately, so the output says whether the token or the chat id is wrong. Prints neither.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from atlas.core.configuration.settings import get_settings
from atlas.integrations.telegram.notifier import _API, build_notifier


def main() -> int:
    settings = get_settings()
    if not settings.telegram_enabled or settings.telegram_bot_token is None:
        print(
            "FAIL  Telegram not configured: set ATLAS_TELEGRAM_BOT_TOKEN and ATLAS_TELEGRAM_CHAT_ID"
        )
        return 2
    now = datetime.now(UTC)
    sent = build_notifier().send(
        f"[PAPER TRADING] ATLAS test alert ({settings.environment}), {now:%Y-%m-%d %H:%M} UTC. "
        "If you can read this, alerts work. No action needed.",
        critical=True,  # bypass duplicate suppression so a re-run sends again
    )
    if sent:
        print("OK    test alert accepted by Telegram: check the chat")
        return 0
    token = settings.telegram_bot_token.get_secret_value()
    try:
        token_ok = httpx.get(f"{_API}/bot{token}/getMe", timeout=10.0).status_code == 200
    except httpx.HTTPError as exc:
        print(f"FAIL  api.telegram.org unreachable ({type(exc).__name__})")
        return 3
    if not token_ok:
        print("FAIL  Telegram rejected the bot token: check ATLAS_TELEGRAM_BOT_TOKEN")
    else:
        print(
            "FAIL  the bot token is valid but the message was refused: check "
            "ATLAS_TELEGRAM_CHAT_ID, and send your bot any message first"
        )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
