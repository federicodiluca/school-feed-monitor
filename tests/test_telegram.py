import sfm.telegram as telegram
from sfm.db_user import add_user, deactivate_user
from tests.conftest import FakeResponse


def test_send_message_posts_json_with_defaults(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr("requests.post", fake_post)
    res = telegram.send_message("ciao", parse_mode="HTML", chat_id=42)

    assert res == {"ok": True, "result": {"message_id": 1}}
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendMessage")
    assert "123456:TEST-TOKEN" in calls[0]["url"]
    assert calls[0]["timeout"] == telegram.REQUEST_TIMEOUT
    assert calls[0]["json"] == {
        "chat_id": 42,
        "text": "ciao",
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }


def test_send_message_without_parse_mode_and_preview_override(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, json=None, **kw: (calls.append(json), FakeResponse({"ok": True}))[1])
    telegram.send_message("x", chat_id=1, disable_web_page_preview=False)
    assert "parse_mode" not in calls[0]
    assert calls[0]["disable_web_page_preview"] is False


def test_send_message_reports_api_error(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: FakeResponse({"ok": False, "description": "Bad Request: can't parse entities"}, status_code=400),
    )
    res = telegram.send_message("<b>rotto", parse_mode="HTML", chat_id=1)
    assert res["ok"] is False
    assert res["status_code"] == 400


def test_send_message_handles_network_exception(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("no network")

    monkeypatch.setattr("requests.post", boom)
    res = telegram.send_message("x", chat_id=1)
    assert res == {"ok": False, "exception": "no network"}


def test_send_message_broadcasts_to_active_users_only(monkeypatch):
    add_user(1)
    add_user(2)
    add_user(3)
    deactivate_user(2)
    targets = []
    monkeypatch.setattr("requests.post", lambda url, json=None, **kw: (targets.append(json["chat_id"]), FakeResponse({"ok": True}))[1])

    results = telegram.send_message("broadcast")

    assert sorted(targets) == [1, 3]
    assert len(results) == 2


# --- split_long_message ---------------------------------------------------

def test_split_short_text_is_single_part():
    assert telegram.split_long_message("ciao") == ["ciao"]
    assert telegram.split_long_message("") == []
    assert telegram.split_long_message(None) == []


def test_split_prefers_double_newline():
    block = "riga " * 100  # ~500 chars
    text = "\n\n".join([block.strip()] * 20)  # ~10k chars
    parts = telegram.split_long_message(text, max_len=4000)
    assert len(parts) >= 3
    for p in parts:
        assert len(p) <= 4000
        assert not p.startswith("\n") and not p.endswith("\n")
    # nessun blocco spezzato a metà: ogni parte è fatta di blocchi interi
    for p in parts:
        for chunk in p.split("\n\n"):
            assert chunk == block.strip()


def test_split_falls_back_to_hard_cut_without_separators():
    text = "x" * 9000
    parts = telegram.split_long_message(text, max_len=4000)
    assert [len(p) for p in parts] == [4000, 4000, 1000]
    assert "".join(parts) == text


def test_send_long_message_sends_each_part(sent_messages):
    text = "\n\n".join(["blocco " * 50] * 30)
    results = telegram.send_long_message(text, chat_id=7)
    assert len(results) == len(sent_messages) > 1
    assert all(m["chat_id"] == 7 and m["parse_mode"] == "HTML" for m in sent_messages)
    assert telegram.send_long_message("", chat_id=7) == []


def test_send_message_with_reply_markup_and_edit_and_answer(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, json=None, **kw: (calls.append((url.rsplit("/", 1)[1], json)), FakeResponse({"ok": True, "result": {}}))[1])
    kb = {"inline_keyboard": [[{"text": "x", "callback_data": "src:t:1"}]]}
    telegram.send_message("ciao", chat_id=1, reply_markup=kb)
    telegram.edit_message_text(1, 55, "nuovo", parse_mode="HTML", reply_markup=kb)
    telegram.answer_callback_query("cq1", text="ok")
    telegram.answer_callback_query("cq2")
    assert calls[0][0] == "sendMessage" and calls[0][1]["reply_markup"] == kb
    assert calls[1] == ("editMessageText", {"chat_id": 1, "message_id": 55, "text": "nuovo", "disable_web_page_preview": True, "parse_mode": "HTML", "reply_markup": kb})
    assert calls[2] == ("answerCallbackQuery", {"callback_query_id": "cq1", "text": "ok"})
    assert calls[3] == ("answerCallbackQuery", {"callback_query_id": "cq2"})
