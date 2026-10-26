import httpx
import pytest
from pydantic import SecretStr

from atlas.integrations.telegram.notifier import TelegramNotifier
from atlas.scripts import send_test_alert as test_alert

TOKEN = "123456:secret-token-value"


@pytest.fixture
def configured(settings, monkeypatch):
    settings.telegram_bot_token = SecretStr(TOKEN)
    settings.telegram_chat_id = "42"
    monkeypatch.setattr(test_alert, "get_settings", lambda: settings)
    return settings


def _wire(monkeypatch, send_status, getme_status):
    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(req)
        if send_status == 200:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(send_status, json={"ok": False})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        test_alert, "build_notifier", lambda: TelegramNotifier(TOKEN, "42", client=client)
    )
    monkeypatch.setattr(
        test_alert.httpx, "get", lambda url, timeout: httpx.Response(getme_status, json={})
    )
    return sent


def test_not_configured(settings, monkeypatch, capsys):
    monkeypatch.setattr(test_alert, "get_settings", lambda: settings)
    assert test_alert.main() == 2
    assert "not configured" in capsys.readouterr().out


def test_delivered(configured, monkeypatch, capsys):
    sent = _wire(monkeypatch, 200, 200)
    assert test_alert.main() == 0
    body = sent[0].read().decode()
    assert "[PAPER TRADING]" in body and "test alert" in body
    out = capsys.readouterr().out
    assert out.startswith("OK") and TOKEN not in out


@pytest.mark.parametrize(
    ("getme", "expected"),
    [(401, "rejected the bot token"), (200, "check ATLAS_TELEGRAM_CHAT_ID")],
)
def test_refused_says_which_setting_is_wrong(configured, monkeypatch, capsys, getme, expected):
    _wire(monkeypatch, 400, getme)
    assert test_alert.main() == 3
    out = capsys.readouterr().out
    assert expected in out and TOKEN not in out and "42" not in out
