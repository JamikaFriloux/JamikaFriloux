import httpx

from atlas.integrations.telegram.notifier import (
    Event,
    NotificationPreferences,
    TelegramNotifier,
    TradeNotification,
)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_disabled_without_credentials():
    assert TelegramNotifier(None, None).send("hi") is False


def test_sends_and_redacts():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"ok": True})

    n = TelegramNotifier("123:tok", "42", client=_client(handler))
    assert n.send("leaked PKABCDEFGHIJKLMNOPQR")
    assert "PKABCDEFGHIJKLMNOPQR" not in seen["body"]
    assert seen["url"].endswith("/bot123:tok/sendMessage")


def test_dedupes_non_critical_but_not_critical():
    calls = []
    n = TelegramNotifier(
        "t",
        "c",
        client=_client(lambda r: calls.append(1) or httpx.Response(200, json={"ok": True})),
    )
    assert n.send("same") and not n.send("same")
    assert n.send("same", critical=True)
    assert len(calls) == 2


def test_preferences_filter_events():
    n = TelegramNotifier(
        "t",
        "c",
        NotificationPreferences(enabled_events=set()),
        client=_client(lambda r: httpx.Response(200, json={"ok": True})),
    )
    assert not n.notify(Event.ORDER_FILLED, "x")
    assert n.notify(Event.CRITICAL_ERROR, "y", critical=True)


def test_network_failure_returns_false():
    def boom(_req):
        raise httpx.ConnectError("down")

    assert TelegramNotifier("t", "c", client=_client(boom)).send("x") is False


def test_trade_notification_has_paper_label_and_fields():
    text = TradeNotification(
        "AAPL", "trend_v1", "ENTRY", "3", "190.10", "25.00", "EMA cross"
    ).render()
    for part in (
        "[PAPER TRADING]",
        "AAPL",
        "trend_v1",
        "ENTRY",
        "3",
        "190.10",
        "25.00",
        "EMA cross",
    ):
        assert part in text
