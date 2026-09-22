"""Chi blocca il bot non deve continuare a ricevere tentativi di invio a ogni notizia."""
import pytest
import requests

import sfm.telegram as telegram
from sfm.db_user import add_user, get_user


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.ok = status_code < 400
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def telegram_says(monkeypatch):
    """Imposta la risposta di Telegram a sendMessage."""
    answer = {}

    def fake_post(url, json=None, timeout=None):
        answer["chat_id"] = (json or {}).get("chat_id")
        return answer["response"]

    monkeypatch.setattr(requests, "post", fake_post)
    return answer


def test_a_user_who_blocked_the_bot_is_suspended(telegram_says):
    add_user(1)
    telegram_says["response"] = FakeResponse(403, {"ok": False, "error_code": 403,
                                                   "description": "Forbidden: bot was blocked by the user"})
    telegram.send_message("ciao", chat_id=1)
    assert get_user(1)["active"] is False


def test_other_errors_do_not_suspend_anyone(telegram_says):
    add_user(1)
    for status, payload in ((429, {"ok": False, "description": "Too Many Requests"}),
                            (400, {"ok": False, "description": "Bad Request: message is too long"}),
                            (403, {"ok": False, "description": "Forbidden: qualcosa di nuovo"})):
        telegram_says["response"] = FakeResponse(status, payload)
        telegram.send_message("ciao", chat_id=1)
        assert get_user(1)["active"] is True, payload


def test_a_successful_send_changes_nothing(telegram_says):
    add_user(1)
    telegram_says["response"] = FakeResponse(200, {"ok": True, "result": {"message_id": 1}})
    assert telegram.send_message("ciao", chat_id=1)["ok"] is True
    assert get_user(1)["active"] is True
