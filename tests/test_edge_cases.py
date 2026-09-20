"""Casi limite del core: matching, parser, dedup, digest, notifier, Telegram."""
from datetime import datetime, timedelta, timezone

import sfm.telegram_commands as tc
from sfm import notifier
from sfm.db_deliveries import delivered_news_ids, record_delivery
from sfm.db_news import add_news, get_recent_news, search_news
from sfm.db_user import add_user, get_user, update_keywords
from sfm.matching import match_users
from sfm.source_parser import detect_source, parse_feed, parse_html_articles, parse_italian_date
from sfm.utils import find_matching_keywords, parse_keywords, parse_rss_datetime
from tests.fixtures import html_list_page, rss


# --- matching -------------------------------------------------------------------

def test_keywords_match_whole_words_with_accents_and_apostrophes():
    text = "Graduatorie per l'insegnamento dell’italiano: posti di sostegno e A-23 (A023)"
    assert find_matching_keywords(text, ["A023"]) == ["A023"]
    assert find_matching_keywords(text, ["A-23"]) == ["A-23"]
    assert find_matching_keywords(text, ["dell'italiano"]) == ["dell'italiano"]      # apostrofo tipografico normalizzato
    assert find_matching_keywords(text, ["sostegn"]) == []                           # non parola intera
    assert find_matching_keywords(text, ["POSTI DI SOSTEGNO"]) == ["POSTI DI SOSTEGNO"]
    assert find_matching_keywords("", ["x"]) == [] and find_matching_keywords(text, ["", "  "]) == []


def test_parse_keywords_dedup_and_trim():
    assert parse_keywords(" A041 , , trasferimenti,graduatorie ") == ["A041", "trasferimenti", "graduatorie"]
    assert parse_keywords("") == []


def test_match_users_ignores_users_without_keywords_and_html_tags():
    news = {"title": "Avviso", "content": "<p class='docenti'>testo <b>ATA</b></p>"}
    users = [{"telegram_id": 1, "keywords": ["docenti"]}, {"telegram_id": 2, "keywords": ["ata"]}, {"telegram_id": 3}]
    assert [(u["telegram_id"], k) for u, k in match_users(news, users)] == [(2, ["ata"])]   # 'docenti' era solo un attributo HTML


# --- parser -----------------------------------------------------------------------

def test_parse_feed_handles_broken_and_empty_input():
    assert parse_feed(b"") == ([], "")
    assert parse_feed(b"<html><body>non un feed</body></html>")[0] == []
    items, title = parse_feed(rss([{"title": "  Titolo <b>ricco</b> ", "link": " https://x/1 "}, {"title": "senza link", "link": ""}], title="F"))
    assert title == "F" and len(items) == 1 and items[0]["title"] == "Titolo ricco" and items[0]["link"] == "https://x/1"


def test_html_parser_filters_external_short_and_duplicate_links():
    page = html_list_page([
        {"title": "Notizia valida numero uno", "link": "/-/uno"},
        {"title": "Notizia valida numero uno", "link": "/-/uno"},               # duplicato
        {"title": "Corta", "link": "/-/due"},                                   # titolo < 10 caratteri
        {"title": "Link esterno da ignorare", "link": "https://altrosito.it/x"},
    ], base="https://www.example.org")
    items, _ = parse_html_articles(page.encode(), "https://www.example.org/novita")
    assert [i["link"] for i in items] == ["https://www.example.org/-/uno"]


def test_parse_italian_date_variants():
    assert parse_italian_date("pubblicato il 3 ottobre 2026 alle 10") == "2026-10-03T00:00:00"
    assert parse_italian_date("del 14/09/2026") == "2026-09-14T00:00:00"
    assert parse_italian_date("2026-09-14T08:30:00+02:00") == "2026-09-14T08:30:00"
    assert parse_italian_date("31 febbraio 2026") is None                       # data impossibile
    assert parse_italian_date("nessuna data") is None and parse_italian_date("") is None


def test_parse_rss_datetime_fallbacks():
    assert parse_rss_datetime("Mon, 14 Sep 2026 10:00:00 +0200") == "2026-09-14 08:00:00"
    assert parse_rss_datetime("2026-09-14T10:00:00Z") == "2026-09-14 10:00:00"
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    assert parse_rss_datetime("boh", now=now) == "2026-09-14 12:00:00"


def test_detect_source_prefers_declared_feed_over_scraping(fake_sources):
    fake_sources["https://site.example/news/"] = html_list_page([{"title": "Notizia lunga numero uno", "link": "/-/1"}] * 5,
                                                                feed_href="https://site.example/feed/", base="https://site.example")
    fake_sources["https://site.example/feed/"] = rss([{"title": "Dal feed", "link": "https://site.example/f/1"}])
    d = detect_source("site.example/news/")            # senza schema
    assert d["type"] == "rss" and d["url"] == "https://site.example/feed/" and d["items"][0]["title"] == "Dal feed"


# --- dedup e ricerca ------------------------------------------------------------------

def test_add_news_dedup_is_by_link_only_and_search_is_case_insensitive():
    assert add_news("Uno", "https://x/1", "S", "", "contenuto ALFA") is not None
    assert add_news("Uno bis", "https://x/1", "S", "", "") is None
    assert add_news("Uno", "https://x/2", "S", "", "") is not None              # stesso titolo, link diverso → nuova
    assert search_news(query="alfa")[1] == 1 and search_news(query="%")[1] == 2  # il jolly LIKE non fa male


def test_delivery_dedup_across_kinds_and_channels():
    assert record_delivery(1, 5, "email", "digest") and not record_delivery(1, 5, "email", "digest")
    assert record_delivery(1, 5, "email", "alert")
    assert delivered_news_ids(1, kind="digest") == {5} and delivered_news_ids(1, channel="telegram") == set()


# --- notifier: nessun canale, utente disattivo ------------------------------------------

def test_notifier_with_no_channels_sends_nothing(sent_messages):
    assert notifier.send_alert({"id": 1, "email": None, "telegram_id": None}, {"title": "t"}, ["k"]) == []
    assert notifier.send_digest({"id": 1, "email": "a@b.it", "notify_email": False}, []) == []
    assert sent_messages == []


# --- Telegram: input strani ------------------------------------------------------------

def test_telegram_commands_survive_odd_input(sent_messages):
    assert tc.handle_update({}) is None
    assert tc.handle_update({"update_id": 1, "message": {"text": "/setkeywords", "chat": {"id": 1}}}) == "setkeywords"
    assert "Usa: /setkeywords" in sent_messages[-1]["text"]
    tc.handle_update({"update_id": 2, "message": {"text": "/setkeywords " + "x" * 5000, "chat": {"id": 1}}})
    assert get_user(1) and len(get_user(1)["keywords"]) == 1
    tc.handle_update({"update_id": 3, "message": {"text": "/latest abc", "chat": {"id": 1}}})
    tc.handle_update({"update_id": 4, "message": {"text": "/follow 999999", "chat": {"id": 1}}})
    assert "Nessuna fonte valida" in sent_messages[-1]["text"]
    tc.handle_update({"update_id": 5, "message": {"text": "/link", "chat": {"id": 1}}})
    assert "Usa: /link" in sent_messages[-1]["text"]
