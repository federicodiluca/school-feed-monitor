"""Sito pubblico senza account: pagine, preferenze nel browser, configuratore."""
import re

from markupsafe import Markup

import pytest

from sfm.db_configs import load_config
from sfm.db_sources import get_sources, sync_config_sources
from sfm.catalog import load_catalog
from web import create_app, prefs


@pytest.fixture
def app():
    return create_app({"TESTING": True, "BASE_URL": "https://sfm.example", "TELEGRAM_BOT_USERNAME": "SfmBot"})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def catalog_db():
    sync_config_sources(load_catalog())
    return {s["name"]: s for s in get_sources()}


def csrf(client, path="/configura"):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert m, "token CSRF non trovato"
    return m.group(1)


def cookie(client, name):
    """Valore del cookie nel browser di prova (già decodificato), None se assente."""
    c = client.get_cookie(name)
    return c.decoded_value if c else None


def choose(client, source_ids, keywords="", azione=None):
    data = {"_csrf": csrf(client), "sources": [str(s) for s in source_ids], "keywords": keywords}
    if azione:
        data["azione"] = azione
    return client.post("/configura", data=data, follow_redirects=False)


# --- pagine pubbliche ---------------------------------------------------------------

def test_public_pages_render_with_seo_tags(client):
    html = client.get("/").get_data(as_text=True)
    assert "<title>School Feed Monitor" in html and '<html lang="it">' in html
    assert '<link rel="canonical" href="https://sfm.example/">' in html
    assert "Scegli le tue fonti" in html and "Nessuna registrazione" in html
    for path in ("/notizie", "/configura", "/le-mie-notizie", "/privacy", "/termini", "/chi-siamo"):
        r = client.get(path)
        assert r.status_code == 200 and "<h1>" in r.get_data(as_text=True), path


def test_no_account_pages_left(client):
    for path in ("/accedi", "/registrati", "/account", "/preferenze", "/password-dimenticata"):
        assert client.get(path).status_code == 404, path


def test_robots_and_sitemap(client):
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Sitemap: https://sfm.example/sitemap.xml" in robots and "Disallow: /le-mie-notizie" in robots
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "<loc>https://sfm.example/configura</loc>" in body and "<loc>https://sfm.example/chi-siamo</loc>" in body


def test_security_headers_and_pwa(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"]
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and sw.headers["Service-Worker-Allowed"] == "/"
    manifest = client.get("/static/site.webmanifest")
    assert manifest.status_code == 200 and b"standalone" in manifest.data


def test_no_session_cookie_without_forms(client):
    """Visitare le pagine non deve lasciare cookie: la sessione nasce solo con il token CSRF."""
    r = client.get("/notizie")
    assert "Set-Cookie" not in r.headers


# --- preferenze nel browser ------------------------------------------------------------

def test_choose_sources_stores_cookies_and_filters_news(client, catalog_db):
    bo = catalog_db["USP Bologna"]["id"]
    r = choose(client, [bo], "A041, trasferimenti")
    assert r.status_code == 302 and r.headers["Location"].endswith("/le-mie-notizie")
    assert cookie(client, "sfm_fonti") == str(bo)
    assert cookie(client, "sfm_parole") == "A041,trasferimenti"

    html = client.get("/le-mie-notizie").get_data(as_text=True)
    assert "1 fonti che hai scelto" in html and "A041, trasferimenti" in html
    html = client.get("/configura").get_data(as_text=True)
    assert f'value="{bo}"' in html and "checked" in html and "A041, trasferimenti" in html
    assert "Le mie notizie" in client.get("/").get_data(as_text=True)   # voce di menu quando ci sono preferenze


def test_my_news_without_preferences_invites_to_choose(client):
    html = client.get("/le-mie-notizie").get_data(as_text=True)
    assert "Non hai ancora scelto le fonti" in html and 'content="noindex' in html


def test_area_shortcut_selects_sources(client, catalog_db):
    r = client.post("/configura/area", data={"_csrf": csrf(client), "regions": ["Sicilia"],
                                             "provinces": ["Sicilia|Enna"]}, follow_redirects=False)
    assert r.status_code == 302
    ids = {int(x) for x in cookie(client, "sfm_fonti").split(",")}
    assert ids == {catalog_db["MIM — Notizie"]["id"], catalog_db["USR Sicilia"]["id"],
                   catalog_db["USP Caltanissetta ed Enna"]["id"]}


def test_forget_and_export(client, catalog_db):
    bo = catalog_db["USP Bologna"]["id"]
    choose(client, [bo], "A041")
    data = client.get("/configura/esporta.json").get_json()
    assert data["fonti"] == [{"id": bo, "nome": "USP Bologna"}] and data["parole_chiave"] == ["A041"]

    client.post("/configura/dimentica", data={"_csrf": csrf(client)}, follow_redirects=False)
    assert cookie(client, "sfm_fonti") is None and cookie(client, "sfm_parole") is None
    assert "Non hai ancora scelto le fonti" in client.get("/le-mie-notizie").get_data(as_text=True)


def test_invalid_sources_and_too_many_keywords_are_ignored(client, catalog_db):
    bo = catalog_db["USP Bologna"]["id"]
    client.post("/configura", data={"_csrf": csrf(client), "sources": [str(bo), "99999", "x"],
                                    "keywords": ", ".join(f"k{i}" for i in range(50))})
    assert cookie(client, "sfm_fonti") == str(bo)
    assert len(prefs.clean_keywords([f"k{i}" for i in range(50)])) == prefs.MAX_KEYWORDS


# --- configuratore → Telegram ------------------------------------------------------------

def test_telegram_code_is_generated_and_readable_by_the_bot(client, catalog_db):
    bo = catalog_db["USP Bologna"]["id"]
    r = choose(client, [bo], "A041", azione="telegram")
    assert "/configura?codice=" in r.headers["Location"]
    code = r.headers["Location"].split("codice=")[1].split("#")[0]

    html = client.get(f"/configura?codice={code}").get_data(as_text=True)
    assert f"/start {code}" in html and f"https://t.me/SfmBot?start={code}" in html and "24 ore" in html

    config = load_config(code)                      # è quello che farà il bot
    assert config == {"sources": [bo], "keywords": ["A041"]}
    assert load_config(code) is None                # usa-e-getta


def test_telegram_code_requires_sources(client):
    r = choose(client, [], "A041", azione="telegram")
    assert "codice=" not in r.headers["Location"]
    assert "Scegli almeno una fonte" in client.get("/configura").get_data(as_text=True)


def test_csrf_required_on_every_post(client):
    for path in ("/configura", "/configura/area", "/configura/dimentica"):
        assert client.post(path, data={"sources": ["1"]}).status_code == 403, path


# --- catalogo e aree ---------------------------------------------------------------------

def test_every_italian_province_is_offered(client, catalog_db):
    """L'elenco delle province è quello dell'Italia, non quello delle fonti che abbiamo:
    chi cerca Udine o Aosta deve trovarle (riceverà le notizie regionali)."""
    from sfm.catalog import PROVINCES
    html = client.get("/configura").get_data(as_text=True)
    assert sum(len(p) for p in PROVINCES.values()) == 107
    for value in ("Friuli-Venezia Giulia|Udine", "Valle d'Aosta|Aosta", "Campania|Salerno",
                  "Puglia|Lecce", "Trentino-Alto Adige|Trento", "Emilia-Romagna|Bologna"):
        assert f'value="{Markup.escape(value)}"' in html, value
    assert "solo notizie regionali" in html      # avviso sulle province senza ufficio dedicato


def test_the_configurator_is_one_form(client):
    """Una sola compilazione: aree, fonti e parole chiave stanno nello stesso form."""
    html = client.get("/configura").get_data(as_text=True)
    assert html.count('<form method="post" action="/configura"') == 1
    assert 'formaction="/configura/area"' in html
    assert html.count('name="azione" value="telegram"') == 1
