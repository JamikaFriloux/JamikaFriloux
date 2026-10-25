"""Telegram notifications (Bot API sendMessage).

Notifications are best-effort: a failure is logged and returns False, it never raises into
trading logic. Messages are redacted before sending and identical non-critical messages are
suppressed within a cool-down window to avoid alert floods.
"""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field

import httpx

from atlas.core.observability.logging import get_logger, redact_value

log = get_logger(__name__)

_API = "https://api.telegram.org"
_MAX_LEN = 4000  # Telegram limit is 4096 characters


class Event(enum.StrEnum):
    SYSTEM_STARTUP = "system_startup"
    PREMARKET_REPORT = "premarket_report"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    POSITION_CLOSED = "position_closed"
    DAILY_RISK_LIMIT = "daily_risk_limit"
    TRADING_PAUSED = "trading_paused"
    BROKER_DISCONNECTED = "broker_disconnected"
    CRITICAL_ERROR = "critical_error"
    DAILY_SUMMARY = "daily_summary"


@dataclass
class NotificationPreferences:
    enabled_events: set[Event] = field(default_factory=lambda: set(Event))
    dedupe_window_seconds: float = 300.0


@dataclass(frozen=True)
class TradeNotification:
    symbol: str
    strategy: str
    action: str  # "ENTRY" / "EXIT"
    quantity: str
    price: str
    risk_amount: str
    reason: str

    def render(self) -> str:
        return (
            f"[PAPER TRADING] {self.action} {self.symbol}\n"
            f"Strategy: {self.strategy}\nQty: {self.quantity} @ {self.price}\n"
            f"Risk: ${self.risk_amount}\nReason: {self.reason}"
        )


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        preferences: NotificationPreferences | None = None,
        client: httpx.Client | None = None,
    ):
        self._token = bot_token
        self._chat_id = chat_id
        self.preferences = preferences or NotificationPreferences()
        self._client = client or httpx.Client(timeout=10.0)
        self._recent: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def _is_duplicate(self, text: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window = self.preferences.dedupe_window_seconds
            self._recent = {k: t for k, t in self._recent.items() if now - t < window}
            if text in self._recent:
                return True
            self._recent[text] = now
            return False

    def notify(self, event: Event, text: str, *, critical: bool = False) -> bool:
        if event not in self.preferences.enabled_events and not critical:
            return False
        return self.send(text, critical=critical)

    def send(self, text: str, *, critical: bool = False) -> bool:
        if not self.enabled:
            log.info("telegram_disabled_skip")
            return False
        text = str(redact_value(text))[:_MAX_LEN]
        if not critical and self._is_duplicate(text):
            return False
        try:
            resp = self._client.post(
                f"{_API}/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text, "disable_web_page_preview": True},
            )
            ok = resp.status_code == 200 and resp.json().get("ok") is True
        except (httpx.HTTPError, ValueError) as exc:
            # Never log the URL: it contains the bot token.
            log.warning("telegram_send_failed", error=type(exc).__name__)
            return False
        if not ok:
            log.warning("telegram_send_rejected", status=resp.status_code)
        return ok


def build_notifier() -> TelegramNotifier:
    from atlas.core.configuration.settings import get_settings

    s = get_settings()
    return TelegramNotifier(
        s.telegram_bot_token.get_secret_value() if s.telegram_bot_token else None,
        s.telegram_chat_id,
    )
