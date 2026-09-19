import sfm.channels.telegram_channel as telegram_channel
import sfm.news_fetcher as news_fetcher
from sfm.db_news import get_recent_news
from sfm.db_sources import add_user_source, get_source, set_user_source
from sfm.db_user import add_user, deactivate_user, update_keywords
from tests.fixtures import html_list_page, rss

UNO = "https://example.org/uno/feed/"
DUE = "https://example.org/due/feed/"


def test_fetch_news_stores_new_entries_and_dedupes(fake_sources, sent_messages):
    fake_sources[UNO] = rss([
        {"title": "Uno", "link": "https://x/1", "published": "Mon, 29 Sep 2025 10:05:28 +0000", "description": "s1"},
        {"title": "Due", "link": "https://x/2", "published": "Mon, 29 Sep 2025 11:05:28 +0000", "description": "s2"},
    ])

    assert news_fetcher.fetch_news() == 2
    assert sorted(fake_sources["__calls__"]) == [DUE, UNO]
    rows = get_recent_news()
    assert {r["link"] for r in rows} == {"https://x/1", "https://x/2"}
    assert {(r["source"], r["source_id"]) for r in rows} == {("Feed Uno", 1)}

    # secondo giro: niente di nuovo, niente notifiche
    assert news_fetcher.fetch_news() == 0
    assert sent_messages == []


def test_fetch_news_notifies_only_matching_active_followers(fake_sources, sent_messages):
    add_user(10); update_keywords(10, ["docenti"])
    add_user(20); update_keywords(20, ["graduatoria finale"])
    add_user(30); update_keywords(30, ["docenti"]); deactivate_user(30)
    add_user(40)  # nessuna keyword
    add_user(50); update_keywords(50, ["docenti"]); set_user_source(5, 1, False)  # (id 5) non segue Feed Uno

    fake_sources[UNO] = rss([
        {"title": "Concorso docenti & ATA", "link": "https://x/1", "description": "<p>Testo <b>breve</b></p>"},
        {"title": "Altro", "link": "https://x/2", "content": "pubblicata la GRADUATORIA FINALE"},
        {"title": "Nulla", "link": "https://x/3", "description": "<div class='docenti'>senza match nel testo</div>"},
    ])

    news_fetcher.fetch_news()

    by_chat = {}
    for m in sent_messages:
        by_chat.setdefault(m["chat_id"], []).append(m)
    assert set(by_chat) == {10, 20}
    assert len(by_chat[10]) == 1 and len(by_chat[20]) == 1

    msg = by_chat[10][0]
    assert msg["parse_mode"] == "HTML"
    assert "<b>Concorso docenti &amp; ATA</b>" in msg["text"]
    assert "<i>Testo breve</i>" in msg["text"]
    assert '<a href="https://x/1">Feed Uno</a>' in msg["text"]


def test_custom_html_source_notifies_only_its_followers(fake_sources, sent_messages):
    add_user(1); update_keywords(1, ["concorso"])
    add_user(2); update_keywords(2, ["concorso"])
    source, _ = add_user_source("USR Marche", "https://mim.example/novita", "html", user_id=1)
    fake_sources["https://mim.example/novita"] = html_list_page(
        [{"title": "Concorso ordinario scuola primaria", "link": "/-/concorso", "date": "11 settembre 2026", "abstract": "abstract"}],
        base="https://mim.example",
    )

    assert news_fetcher.fetch_news() == 1
    row = get_recent_news()[0]
    assert row["source_id"] == source["id"] and row["link"] == "https://mim.example/-/concorso"
    assert [m["chat_id"] for m in sent_messages] == [1]
    assert '<a href="https://mim.example/-/concorso">USR Marche</a>' in sent_messages[0]["text"]


def test_fetch_news_skips_broken_source_and_continues(fake_sources, sent_messages):
    fake_sources[DUE] = rss([{"title": "ok", "link": "https://x/ok"}])
    # UNO non registrato → SourceError
    assert news_fetcher.fetch_news() == 1
    assert get_recent_news()[0]["source"] == "Feed Due"


def test_fetch_news_survives_unexpected_exception(fake_sources, sent_messages):
    fake_sources[UNO] = RuntimeError("boom")
    fake_sources[DUE] = rss([{"title": "ok", "link": "https://x/ok"}])
    assert news_fetcher.fetch_news() == 1


def test_fetch_news_ignores_entries_without_link(fake_sources, sent_messages):
    fake_sources[UNO] = rss([{"title": "senza link", "link": ""}, {"title": "con link", "link": "https://x/1"}])
    assert news_fetcher.fetch_news() == 1


def test_fetch_source_without_notify_seeds_silently(fake_sources, sent_messages):
    add_user(1); update_keywords(1, ["ok"])
    fake_sources[UNO] = rss([{"title": "ok 1", "link": "https://x/1"}, {"title": "ok 2", "link": "https://x/2"}])
    assert news_fetcher.fetch_source(get_source(1), followers=[{"telegram_id": 1, "keywords": ["ok"]}], notify=False) == 2
    assert sent_messages == []
    # al giro successivo sono già note: nessuna notifica retroattiva
    assert news_fetcher.fetch_news() == 0
    assert sent_messages == []


def test_notification_error_does_not_abort_fetch(fake_sources, monkeypatch):
    add_user(10); update_keywords(10, ["ok"])

    def failing_send(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(telegram_channel, "send_message", failing_send)
    fake_sources[UNO] = rss([{"title": "ok 1", "link": "https://x/1"}, {"title": "ok 2", "link": "https://x/2"}])

    assert news_fetcher.fetch_news() == 2
    assert len(get_recent_news()) == 2
