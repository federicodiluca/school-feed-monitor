import pytest

import sfm.source_parser as sp
from tests.fixtures import html_list_page, rss

HTML_CT = "text/html; charset=UTF-8"
RSS_CT = "application/rss+xml; charset=UTF-8"


# --- parse_italian_date ---------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Pubblicato il 11 settembre 2026 alle 10", "2026-09-11T00:00:00"),
    ("3 Gennaio 2025", "2025-01-03T00:00:00"),
    ("1 dic. 2024", "2024-12-01T00:00:00"),
    ("Data: 05/10/2025", "2025-10-05T00:00:00"),
    ("05-10-2025", "2025-10-05T00:00:00"),
    ("2025-10-05T14:30:00+02:00", "2025-10-05T14:30:00"),
    ("2025-10-05", "2025-10-05T00:00:00"),
    ("31 febbraio 2025", None),          # data impossibile
    ("nessuna data qui", None),
    ("", None),
    (None, None),
])
def test_parse_italian_date(text, expected):
    assert sp.parse_italian_date(text) == expected


# --- parse_feed -----------------------------------------------------------

def test_parse_feed_normalizes_entries_and_reads_title():
    data = rss([
        {"title": "Uno &amp; due", "link": "https://x/1", "published": "Mon, 29 Sep 2025 10:05:28 +0000", "content": "<p>full</p>", "description": "desc"},
        {"title": "Solo descrizione", "link": "https://x/2", "description": "desc2"},
        {"title": "Senza link", "link": ""},
    ], title="Il mio feed")
    items, title = sp.parse_feed(data)
    assert title == "Il mio feed"
    assert [i["link"] for i in items] == ["https://x/1", "https://x/2"]
    assert items[0]["title"] == "Uno & due"
    assert items[0]["published"] == "Mon, 29 Sep 2025 10:05:28 +0000"
    assert items[0]["content"] == "<p>full</p>"     # content:encoded vince su description
    assert items[1]["content"] == "desc2"
    assert items[1]["published"]                     # fallback a now


def test_parse_feed_on_html_returns_nothing():
    items, _ = sp.parse_feed(html_list_page([]))
    assert items == []


# --- discover_feed_url ----------------------------------------------------

def test_discover_feed_url_skips_comments_feed_and_resolves_relative():
    page = html_list_page([], feed_href="/feed/")
    assert sp.discover_feed_url(page, "https://www.example.org/tutte-le-notizie/") == "https://www.example.org/feed/"
    assert sp.discover_feed_url(html_list_page([]), "https://www.example.org/") is None


# --- parse_html_articles --------------------------------------------------

def test_parse_html_articles_extracts_title_link_date_and_abstract():
    page = html_list_page([
        {"title": "Concorso docenti A-61: surroga di un componente", "link": "https://www.example.org/-/concorso-a61", "date": "11 settembre 2026", "abstract": "Testo breve"},
        {"title": "Seconda notizia molto interessante", "link": "/-/seconda", "date": "10 settembre 2026"},
        {"title": "Duplicato", "link": "https://www.example.org/-/concorso-a61"},
        {"title": "Corta", "link": "https://www.example.org/-/corta"},
        {"title": "Link esterno non deve passare", "link": "https://altro.example.com/x"},
    ])
    items, page_title = sp.parse_html_articles(page, "https://www.example.org/novita")
    assert page_title == "Novità dall'USR Prova"
    assert [i["link"] for i in items] == ["https://www.example.org/-/concorso-a61", "https://www.example.org/-/seconda"]
    assert items[0]["title"] == "Concorso docenti A-61: surroga di un componente"
    assert items[0]["published"] == "2026-09-11T00:00:00"
    assert items[0]["content"] == "Testo breve"          # il paragrafo dei tag (solo link) è escluso
    assert items[1]["published"] == "2026-09-10T00:00:00"
    assert items[1]["content"] == ""


def test_parse_html_articles_fallback_to_headings_and_time_tag():
    page = """<html><head><title>Lista</title></head><body>
      <div class="post"><h2><a href="/news/1">Prima notizia della lista</a></h2><time datetime="2025-10-05T09:00:00">5 ott</time><p>abstract 1</p></div>
      <div class="post"><h2><a href="/news/2">Seconda notizia della lista</a></h2><p>Pubblicata il 04/10/2025</p></div>
    </body></html>"""
    items, _ = sp.parse_html_articles(page, "https://www.example.org/lista")
    assert [i["link"] for i in items] == ["https://www.example.org/news/1", "https://www.example.org/news/2"]
    assert items[0]["published"] == "2025-10-05T09:00:00"
    assert items[1]["published"] == "2025-10-04T00:00:00"


# --- detect_source --------------------------------------------------------

def test_detect_source_direct_rss(fake_sources):
    fake_sources["https://www.example.org/feed/"] = (rss([{"title": "A", "link": "https://x/1"}], title="Feed X"), RSS_CT)
    d = sp.detect_source("https://www.example.org/feed/")
    assert d["type"] == "rss" and d["url"] == "https://www.example.org/feed/"
    assert d["name"] == "Feed X" and len(d["items"]) == 1


def test_detect_source_adds_scheme(fake_sources):
    fake_sources["https://www.example.org/feed/"] = rss([{"title": "A", "link": "https://x/1"}])
    assert sp.detect_source("www.example.org/feed/")["url"] == "https://www.example.org/feed/"


def test_detect_source_autodiscovers_feed_from_html_page(fake_sources):
    fake_sources["https://www.example.org/tutte-le-notizie/"] = (html_list_page([], feed_href="https://www.example.org/feed/"), HTML_CT)
    fake_sources["https://www.example.org/feed/"] = (rss([{"title": "A", "link": "https://x/1"}], title="Ufficio VII"), RSS_CT)
    d = sp.detect_source("https://www.example.org/tutte-le-notizie/")
    assert d["type"] == "rss"
    assert d["url"] == "https://www.example.org/feed/"
    assert d["name"] == "Ufficio VII"


def test_detect_source_falls_back_to_html_scraping(fake_sources):
    items = [{"title": f"Notizia numero {i} abbastanza lunga", "link": f"https://www.example.org/-/n{i}"} for i in range(3)]
    fake_sources["https://www.example.org/novita"] = (html_list_page(items), HTML_CT)
    d = sp.detect_source("https://www.example.org/novita")
    assert d["type"] == "html"
    assert d["url"] == "https://www.example.org/novita"
    assert d["name"] == "Novità dall'USR Prova"
    assert len(d["items"]) == 3


def test_detect_source_prefers_feed_even_if_declared_feed_is_broken(fake_sources):
    items = [{"title": f"Notizia numero {i} abbastanza lunga", "link": f"https://www.example.org/-/n{i}"} for i in range(3)]
    fake_sources["https://www.example.org/novita"] = (html_list_page(items, feed_href="/feed/"), HTML_CT)
    # /feed/ non è registrato → 404 → si ripiega sullo scraping
    assert sp.detect_source("https://www.example.org/novita")["type"] == "html"


def test_detect_source_rejects_pages_without_news(fake_sources):
    fake_sources["https://www.example.org/"] = (html_list_page([]), HTML_CT)
    with pytest.raises(sp.SourceError, match="non sembra una lista di notizie"):
        sp.detect_source("https://www.example.org/")

    fake_sources["https://www.example.org/x.json"] = ('{"a": 1}', "application/json")
    with pytest.raises(sp.SourceError, match="non è un feed"):
        sp.detect_source("https://www.example.org/x.json")


def test_detect_source_network_error(fake_sources):
    with pytest.raises(sp.SourceError, match="404"):
        sp.detect_source("https://www.example.org/missing")


# --- read_source ----------------------------------------------------------

def test_read_source_dispatches_on_type(fake_sources):
    fake_sources["https://www.example.org/feed/"] = rss([{"title": "A", "link": "https://x/1"}])
    fake_sources["https://www.example.org/novita"] = html_list_page([{"title": "Notizia abbastanza lunga", "link": "/-/n1"}])
    assert [i["link"] for i in sp.read_source({"url": "https://www.example.org/feed/", "type": "rss"})] == ["https://x/1"]
    assert [i["link"] for i in sp.read_source({"url": "https://www.example.org/novita", "type": "html"})] == ["https://www.example.org/-/n1"]
    with pytest.raises(sp.SourceError):
        sp.read_source({"url": "https://www.example.org/novita", "type": "rss"})  # HTML letto come RSS: vuoto


def test_fetch_url_uses_timeout_and_user_agent(monkeypatch):
    calls = {}

    class Resp:
        content = b"ok"
        headers = {"content-type": "text/plain"}

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, timeout=None):
        calls.update(url=url, headers=headers, timeout=timeout)
        return Resp()

    monkeypatch.setattr("requests.get", fake_get)
    assert sp.fetch_url("https://www.example.org/") == (b"ok", "text/plain")
    assert calls["timeout"] == sp.FETCH_TIMEOUT
    assert "SchoolFeedMonitor" in calls["headers"]["User-Agent"]


# --- date di pubblicazione: mai dal titolo, mai nel futuro --------------------------

def _page(block_html):
    return f"<html><head><title>T</title></head><body>{block_html}</body></html>".encode("utf-8")


def test_html_date_ignores_title_and_prefers_dated_element():
    html = _page("""
    <article><h3><a href="/a">Evento del 24 settembre 2099 per docenti</a></h3>
      <span class="article_data">10 settembre 2026</span><p>testo</p></article>
    <article><h3><a href="/c">Notizia con data solo nel titolo del 1 gennaio 2099</a></h3><p>corpo senza date</p></article>
    <article><h3><a href="/d">Notizia con time</a></h3><time datetime="2026-09-11T08:00:00">ieri</time><p>entro il 5 ottobre 2099</p></article>
    """)
    items, _ = sp.parse_html_articles(html, "https://x.example/")
    by_link = {i["link"]: i["published"] for i in items}
    assert by_link["https://x.example/a"].startswith("2026-09-10")   # elemento con classe "data", non il titolo
    assert by_link["https://x.example/c"] == ""                       # solo una data futura nel titolo → nessuna data
    assert by_link["https://x.example/d"].startswith("2026-09-11")   # <time> vince sulla scadenza nel corpo


def test_html_date_from_revision_line_not_title_deadline():
    # pagine senza <article> (es. USR Liguria): link che avvolge il titolo, data in una riga "Ultima revisione"
    html = _page("""
    <div class="media-body"><a href="/b"><h2>Scadenza domande 30 dicembre 2099</h2></a>
      <p><span class="small">Ultima revisione il 12-09-2026</span></p></div>
    <div class="media-body"><a href="/c"><h2>Altro avviso pubblicato oggi</h2></a>
      <p><span class="small">Ultima revisione il 13-09-2026</span></p></div>
    <div class="media-body"><a href="/d"><h2>Terzo avviso in elenco</h2></a>
      <p><span class="small">Ultima revisione il 13-09-2026</span></p></div>
    """)
    items, _ = sp.parse_html_articles(html, "https://x.example/")
    by_link = {i["link"]: i["published"] for i in items}
    assert by_link["https://x.example/b"].startswith("2026-09-12")   # non la scadenza nel titolo


def test_html_future_date_in_body_is_discarded():
    html = _page('<article><h3><a href="/a">Bando borse di studio</a></h3><p>Domande entro il 31 dicembre 2099</p></article>')
    items, _ = sp.parse_html_articles(html, "https://x.example/")
    assert items[0]["published"] == ""
