"""Generatore del sito statico per GitHub Pages."""
import json
import os

import pytest

from scripts.build_site import build
from sfm.catalog import load_catalog
from sfm.db_news import add_news
from sfm.db_sources import get_sources, sync_config_sources

BASE_URL = "https://esempio.github.io/school-feed-monitor"
PREFIX = "/school-feed-monitor"


def _sample_catalog():
    """Poche fonti del catalogo vero: generare 113 pagine a ogni test non aggiunge nulla."""
    catalog = load_catalog()
    return [e for e in catalog if e["kind"] == "mim" or e["region"] in ("Emilia-Romagna", "Sicilia")]


@pytest.fixture
def site(tmp_path, monkeypatch):
    # create_app riallinea le fonti con la config: qui la config è il campione di catalogo
    sites = _sample_catalog()
    monkeypatch.setattr("web.get_config", lambda: {"sites": sites})
    sync_config_sources(sites)
    source = next(s for s in get_sources() if s["name"] == "USP Bologna")
    add_news("Graduatorie definitive A041", "https://x/1", source["name"], "2026-09-21 09:00:00",
             "testo della notizia", source_id=source["id"])
    out = build(str(tmp_path / "site"), base_url=BASE_URL, bot_username="SfmBot")
    return out


def read(site, *parts):
    with open(os.path.join(site, *parts), encoding="utf-8") as f:
        return f.read()


def test_every_public_page_becomes_a_file(site):
    for page in ("index.html", "notizie/index.html", "configura/index.html", "le-mie-notizie/index.html",
                 "chi-siamo/index.html", "privacy/index.html", "termini/index.html",
                 "robots.txt", "sitemap.xml", "404.html", ".nojekyll", "sw.js"):
        assert os.path.exists(os.path.join(site, page)), page
    assert os.path.exists(os.path.join(site, "static", "style.css"))


def test_links_and_canonical_carry_the_pages_prefix(site):
    html = read(site, "index.html")
    assert f'<link rel="canonical" href="{BASE_URL}/">' in html
    assert f'href="{PREFIX}/notizie/"' in html and f'href="{PREFIX}/static/style.css"' in html
    assert 'data-base="/school-feed-monitor"' in html and 'data-static="1"' in html
    # niente riferimenti alla radice del dominio, che su Pages è di un altro sito
    assert 'href="/notizie"' not in html and 'src="/static/' not in html


def test_sitemap_is_absolute_and_not_doubled(site):
    xml = read(site, "sitemap.xml")
    assert f"<loc>{BASE_URL}/notizie/</loc>" in xml
    assert f"{PREFIX}{PREFIX}" not in xml
    robots = read(site, "robots.txt")
    assert f"Disallow: {PREFIX}/le-mie-notizie" in robots and f"Sitemap: {BASE_URL}/sitemap.xml" in robots


def test_page_urls_end_with_a_slash_like_github_pages_wants(site):
    """Pages porta /notizie su /notizie/ con un 301: canonical e sitemap devono già avere la
    barra, altrimenti Google trova un canonical che punta a un redirect."""
    html = read(site, "notizie", "index.html")
    assert f'<link rel="canonical" href="{BASE_URL}/notizie/">' in html
    xml = read(site, "sitemap.xml")
    assert "/usp-bologna/</loc>" in xml and "/sitemap.xml/" not in xml
    home = read(site, "index.html")
    assert f'"url": "{BASE_URL}/"' in home          # JSON-LD senza il prefisso doppio
    assert f'href="{PREFIX}/static/style.css"' in home and f'href="{PREFIX}/privacy/"' in home


def test_source_pages_are_generated_and_indexable(site):
    html = read(site, "notizie", "fonte", *_source_path(site))
    assert "USP Bologna" in html and "Graduatorie definitive A041" in html


def _source_path(site):
    sources = json.loads(read(site, "data", "sources.json"))["items"]
    page = next(s["page"] for s in sources if s["name"] == "USP Bologna")
    return page.split("/notizie/fonte/")[1].split("/") + ["index.html"]


def test_news_dataset_has_what_the_browser_needs(site):
    data = json.loads(read(site, "data", "news.json"))
    item = next(i for i in data["items"] if i["t"] == "Graduatorie definitive A041")
    assert item["l"] == "https://x/1" and item["n"] == "USP Bologna" and item["p"]
    assert isinstance(item["s"], int)


def test_sources_dataset_carries_catalog_positions_for_the_telegram_link(site):
    data = json.loads(read(site, "data", "sources.json"))
    catalog = load_catalog()
    assert data["catalog_size"] == len(catalog)
    bologna = next(s for s in data["items"] if s["name"] == "USP Bologna")
    assert catalog[bologna["catalog"]]["name"] == "USP Bologna"
    assert bologna["region"] == "Emilia-Romagna" and bologna["kind"] == "usp"


def test_my_news_page_stays_out_of_the_index(site):
    assert '<meta name="robots" content="noindex, nofollow">' in read(site, "le-mie-notizie", "index.html")


def test_configurator_has_no_forms_to_post_to(site):
    html = read(site, "configura", "index.html")
    assert "_csrf" not in html and 'method="post"' not in html
    assert 'data-catalog="' in html            # serve a costruire il link di Telegram nel browser


def test_pages_say_when_they_were_updated_and_when_the_next_update_is(site):
    html = read(site, "notizie", "index.html")
    assert 'class="freshness"' in html and "Notizie aggiornate il" in html
    assert "Prossimo aggiornamento verso le" in html and "il sito si aggiorna ogni ora" in html
    assert "Notizie aggiornate il" in read(site, "privacy", "index.html")   # nel footer di ogni pagina


def test_region_pages_are_generated(site):
    html = read(site, "notizie", "regione", "emilia-romagna", "index.html")
    assert "Graduatorie definitive A041" in html
    assert f'<link rel="canonical" href="{BASE_URL}/notizie/regione/emilia-romagna/">' in html
    assert f"<loc>{BASE_URL}/notizie/regione/sicilia/</loc>" in read(site, "sitemap.xml")


def test_link_previews_have_an_image(site):
    html = read(site, "index.html")
    assert f'<meta property="og:image" content="{BASE_URL}/static/og-image.png">' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert os.path.getsize(os.path.join(site, "static", "og-image.png")) > 10_000


def test_a_custom_domain_gets_its_cname_file(tmp_path, monkeypatch):
    monkeypatch.setattr("web.get_config", lambda: {"sites": _sample_catalog()})
    out = build(str(tmp_path / "dom"), base_url="https://school-feed-monitor.it")
    assert read(out, "CNAME") == "school-feed-monitor.it\n"
    assert "Sitemap: https://school-feed-monitor.it/sitemap.xml" in read(out, "robots.txt")
    assert '<link rel="canonical" href="https://school-feed-monitor.it/notizie/">' in read(out, "notizie", "index.html")


def test_github_pages_has_no_cname(site):
    assert not os.path.exists(os.path.join(site, "CNAME"))
