from datetime import datetime, timedelta, timezone

import pytest

from sfm.db_news import add_news, search_news
from sfm.db_sources import sync_config_sources
from sfm.utils import slugify
from tests.test_web import choose
from web import create_app


def _at(days_ago, hours=10):
    """Data di pubblicazione nel fuso *locale*: "oggi" nel riepilogo è il giorno locale, e
    con l'ora UTC il test falliva ogni notte fra mezzanotte e le due."""
    local = datetime.now().astimezone() - timedelta(days=days_ago)
    return local.replace(hour=hours, minute=0, second=0, microsecond=0).isoformat()


@pytest.fixture
def app():
    return create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def some_news():
    add_news("Graduatorie provinciali docenti", "https://x/1", "Feed Uno", _at(0), "<p>pubblicate le GPS</p>", source_id=1)
    add_news("Trasferimenti 2026 <A041>", "https://x/2", "Feed Uno", _at(1), "mobilità", source_id=1)
    add_news("Concorso ATA", "https://x/3", "Feed Due", _at(2), "", source_id=2)
    add_news("Vecchia", "https://x/4", "Feed Due", _at(20), "", source_id=2)


# --- query -----------------------------------------------------------------------

def test_search_news_filters_and_pagination(some_news):
    rows, total = search_news()
    assert total == 4 and [r["link"] for r in rows] == ["https://x/1", "https://x/2", "https://x/3", "https://x/4"]
    assert search_news(days=7)[1] == 3
    assert search_news(source_ids={2})[1] == 2
    assert search_news(query="gps")[1] == 1 and search_news(query="TRASFERIMENTI")[1] == 1
    rows, total = search_news(page=2, per_page=3)
    assert total == 4 and [r["link"] for r in rows] == ["https://x/4"]
    assert search_news(source_ids=set())[1] == 0


def test_slugify():
    assert slugify("USR Emilia-Romagna – Ufficio VII") == "usr-emilia-romagna-ufficio-vii"
    assert slugify("Città di Forlì!") == "citta-di-forli"
    assert slugify("") == "fonte"


# --- /notizie (pubblica) ---------------------------------------------------------

def test_public_news_page_lists_and_filters(client, some_news):
    html = client.get("/notizie").get_data(as_text=True)
    assert "Graduatorie provinciali docenti" in html and "Trasferimenti 2026 &lt;A041&gt;" in html
    assert "Vecchia" not in html                      # fuori dagli ultimi 7 giorni
    assert "3 notizie" in html and "pubblicate le GPS" in html
    assert 'name="robots"' not in html               # pagina base indicizzabile
    assert "Scegli le tue fonti" in html             # invito per chi non ha ancora scelto

    html = client.get("/notizie?giorni=30").get_data(as_text=True)
    assert "Vecchia" in html and "4 notizie" in html
    html = client.get("/notizie?q=ata").get_data(as_text=True)
    assert "Concorso ATA" in html and "Graduatorie" not in html and 'content="noindex, follow"' in html
    html = client.get("/notizie?fonte=2&giorni=30").get_data(as_text=True)
    assert "Concorso ATA" in html and "Graduatorie" not in html
    html = client.get("/notizie?giorni=999&pagina=abc&fonte=x").get_data(as_text=True)
    assert "3 notizie" in html                       # parametri invalidi → default


def test_public_news_pagination(client):
    for i in range(45):
        add_news(f"Notizia {i}", f"https://x/{i}", "Feed Uno", _at(0), "", source_id=1)
    html = client.get("/notizie").get_data(as_text=True)
    assert "pagina 1 di 3" in html and 'rel="next"' in html and 'rel="prev"' not in html
    html = client.get("/notizie?pagina=3").get_data(as_text=True)
    assert "pagina 3 di 3" in html and 'rel="prev"' in html and 'rel="next"' not in html
    assert 'content="noindex, follow"' in html
    r = client.get("/notizie?pagina=99")
    assert r.status_code == 302 and r.headers["Location"].endswith("/notizie?pagina=3")


def test_source_page_and_slug_redirect(client, some_news):
    r = client.get("/notizie/fonte/1")
    assert r.status_code == 301 and r.headers["Location"].endswith("/notizie/fonte/1/feed-uno")
    r = client.get("/notizie/fonte/1/sbagliato?giorni=30")
    assert r.status_code == 301 and "/notizie/fonte/1/feed-uno?giorni=30" in r.headers["Location"]
    html = client.get("/notizie/fonte/1/feed-uno").get_data(as_text=True)
    assert "<h1>Notizie da Feed Uno</h1>" in html and "Graduatorie" in html and "Concorso ATA" not in html
    assert '<link rel="canonical" href="https://sfm.example/notizie/fonte/1/feed-uno">' in html
    assert client.get("/notizie/fonte/999").status_code == 404
    sync_config_sources([{"name": "Feed Uno", "url": "https://example.org/uno/feed/"}])   # Feed Due disabilitata
    assert client.get("/notizie/fonte/2/feed-due").status_code == 404


def test_sitemap_and_home_include_news(client, some_news):
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "<loc>https://sfm.example/notizie</loc>" in body
    assert "<loc>https://sfm.example/notizie/fonte/1/feed-uno</loc>" in body
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /le-mie-notizie" in robots
    home = client.get("/").get_data(as_text=True)
    assert "Ultime notizie raccolte" in home and "Graduatorie provinciali docenti" in home and "Vecchia" not in home


# --- /le-mie-notizie ---------------------------------------------------------------

def test_my_news_without_choice_shows_invite(client):
    html = client.get("/le-mie-notizie").get_data(as_text=True)
    assert "Non hai ancora scelto le fonti" in html


def test_my_news_daily_recap_highlights_keywords(client, some_news):
    choose(client, [1, 2], "GPS, A041")
    html = client.get("/le-mie-notizie").get_data(as_text=True)
    assert "Riepilogo del giorno" in html and 'content="noindex, nofollow"' in html
    assert "Graduatorie provinciali docenti" in html and "</svg> GPS" in html
    assert "Trasferimenti" not in html                # è di ieri
    assert "1 notizie" in html and "1 con le tue parole chiave" in html

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    html = client.get(f"/le-mie-notizie?giorno={yesterday}").get_data(as_text=True)
    assert "Trasferimenti 2026" in html and "</svg> A041" in html and "Graduatorie" not in html
    html = client.get("/le-mie-notizie?giorno=2999-01-01").get_data(as_text=True)   # futuro → oggi
    assert "Graduatorie" in html
    html = client.get("/le-mie-notizie?giorno=boh").get_data(as_text=True)
    assert "Graduatorie" in html


def test_my_news_all_view_respects_followed_sources(client, some_news):
    choose(client, [1], "")
    html = client.get("/le-mie-notizie?vista=tutte&giorni=30").get_data(as_text=True)
    assert "Graduatorie" in html and "Trasferimenti" in html
    assert "Concorso ATA" not in html and "Vecchia" not in html
    assert "2 notizie" in html
    html = client.get("/le-mie-notizie?vista=tutte&q=mobilit").get_data(as_text=True)
    assert "Trasferimenti" in html and "Graduatorie" not in html
