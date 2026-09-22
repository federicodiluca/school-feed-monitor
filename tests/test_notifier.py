import sfm.notifier as notifier
from sfm.matching import match_users, news_text


# --- matching (logica pura) ------------------------------------------------

def test_news_text_strips_html_from_content():
    assert news_text({"title": "Titolo", "content": "<p>corpo <b>x</b></p>"}) == "Titolo corpo x"
    assert news_text({"title": None, "content": None}) == " "


def test_match_users_returns_only_users_with_matching_keywords():
    news = {"title": "Concorso docenti", "content": "<p>pubblicata la GRADUATORIA finale</p>"}
    users = [
        {"telegram_id": 1, "keywords": ["docenti"]},
        {"telegram_id": 2, "keywords": ["graduatoria finale", "ata"]},
        {"telegram_id": 3, "keywords": ["docente"]},   # non è parola intera
        {"telegram_id": 4, "keywords": []},
        {"telegram_id": 5},
    ]
    matches = match_users(news, users)
    assert [(u["telegram_id"], kws) for u, kws in matches] == [(1, ["docenti"]), (2, ["graduatoria finale"])]


# --- dispatcher ------------------------------------------------------------

class FakeChannel:
    NAME = "fake"

    def __init__(self, fail=False):
        self.alerts, self.digests, self.fail = [], [], fail

    def send_alert(self, user, news, matched_keywords):
        if self.fail:
            raise RuntimeError("down")
        self.alerts.append((user, news, matched_keywords))

    def send_digest(self, user, news_list):
        if self.fail:
            raise RuntimeError("down")
        self.digests.append((user, news_list))


def test_channels_for_telegram_only_when_id_present():
    assert notifier.channels_for({"telegram_id": 5}) == ["telegram"]
    assert notifier.channels_for({"telegram_id": None}) == []
    assert notifier.channels_for({}) == []
    assert notifier.channels_for({"email": "a@b.it"}) == []   # niente canale email in questa versione


def test_send_alert_dispatches_to_user_channels(monkeypatch):
    ch = FakeChannel()
    monkeypatch.setitem(notifier.CHANNELS, "fake", ch)
    monkeypatch.setattr(notifier, "channels_for", lambda user: ["fake"])
    user, news = {"telegram_id": 1, "keywords": ["x"]}, {"title": "t", "link": "l"}
    assert notifier.send_alert(user, news, ["x"]) == ["fake"]
    assert ch.alerts == [(user, news, ["x"])]


def test_send_digest_dispatches_to_user_channels(monkeypatch):
    ch = FakeChannel()
    monkeypatch.setitem(notifier.CHANNELS, "fake", ch)
    monkeypatch.setattr(notifier, "channels_for", lambda user: ["fake"])
    assert notifier.send_digest({"telegram_id": 1}, []) == ["fake"]
    assert ch.digests == [({"telegram_id": 1}, [])]


def test_failing_channel_is_isolated(monkeypatch):
    ok, ko = FakeChannel(), FakeChannel(fail=True)
    monkeypatch.setitem(notifier.CHANNELS, "ok", ok)
    monkeypatch.setitem(notifier.CHANNELS, "ko", ko)
    monkeypatch.setattr(notifier, "channels_for", lambda user: ["ko", "ok"])
    assert notifier.send_alert({"telegram_id": 1}, {"title": "t"}, ["k"]) == ["ok"]
    assert len(ok.alerts) == 1


def test_telegram_channel_sends_alert_and_digest(sent_messages):
    user = {"telegram_id": 42, "keywords": ["k"]}
    notifier.send_alert(user, {"title": "T & T", "link": "https://x/1", "source": "Src", "content": "<p>c</p>"}, ["k"])
    notifier.send_digest(user, [])
    assert [m["chat_id"] for m in sent_messages] == [42, 42]
    assert "<b>T &amp; T</b>" in sent_messages[0]["text"] and '<a href="https://x/1">Src</a>' in sent_messages[0]["text"]
    assert "Nessuna notizia" in sent_messages[1]["text"]
