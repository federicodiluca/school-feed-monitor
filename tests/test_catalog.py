"""Catalogo fonti italiane + parser sui campioni HTML reali (tests/fixtures_html/)."""
import json
import os
from collections import Counter
from urllib.parse import urlparse

import pytest

from sfm.catalog import REGIONS, load_catalog, merge_sites
from sfm.config_loader import load_config
from sfm.db_sources import get_sources, sync_config_sources
from sfm.source_parser import parse_html_articles

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures_html")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


# --- catalogo ---------------------------------------------------------------

def test_catalog_entries_are_well_formed():
    entries = load_catalog()
    assert len(entries) >= 20
    urls = [e["url"] for e in entries]
    assert len(urls) == len(set(urls)), "URL duplicati nel catalogo"
    names = [e["name"] for e in entries]
    assert len(names) == len(set(names)), "nomi duplicati nel catalogo"
    for e in entries:
        assert e["type"] in ("rss", "html") and e["kind"] in ("usr", "usp", "mim", "other"), e
        assert urlparse(e["url"]).scheme == "https", e["url"]
        if e["kind"] in ("usr", "usp"):
            assert e["region"] in REGIONS, e
            assert e["default_follow"] is False       # opt-in: l'utente sceglie regione/provincia
        if e["kind"] == "usp":
            assert e["province"], e
    assert any(e["kind"] == "mim" and e["default_follow"] for e in entries)


def test_catalog_covers_all_regions_with_a_usr():
    regions = {e["region"] for e in load_catalog() if e["kind"] == "usr"}
    # Trentino-Alto Adige e Valle d'Aosta non hanno un USR (competenza provinciale/regionale)
    expected = set(REGIONS) - {"Trentino-Alto Adige", "Valle d'Aosta"}
    assert regions == expected


def test_merge_sites_config_wins():
    catalog = [{"name": "USR X", "url": "https://x/feed/", "type": "rss", "kind": "usr", "region": "Lazio", "province": None, "default_follow": False}]
    cfg = [{"name": "Mio USR X", "url": "https://x/feed/", "type": "rss", "default_follow": True}]
    merged = merge_sites(cfg, catalog)
    assert len(merged) == 1 and merged[0]["name"] == "Mio USR X" and merged[0]["default_follow"] is True


def test_config_loads_catalog_by_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"telegram_token": "t", "sites": [{"name": "Mia", "url": "https://mia.example/feed/"}]}), encoding="utf-8")
    cfg = load_config(str(path))
    kinds = Counter(s["kind"] for s in cfg["sites"])
    assert kinds["usr"] >= 18 and kinds["mim"] >= 1 and kinds["other"] == 1
    path.write_text(json.dumps({"telegram_token": "t", "catalog": False, "sites": []}), encoding="utf-8")
    assert load_config(str(path))["sites"] == []


def test_sync_stores_kind_region_province():
    sync_config_sources(load_catalog())
    by_name = {s["name"]: s for s in get_sources()}
    usr = by_name["USR Emilia-Romagna"]
    assert usr["kind"] == "usr" and usr["region"] == "Emilia-Romagna" and usr["default_follow"] is False
    assert by_name["MIM — Notizie"]["kind"] == "mim" and by_name["MIM — Notizie"]["default_follow"] is True


# --- parser sui campioni reali ------------------------------------------------------

def test_parse_usr_fvg_anchor_wrapped_headings():
    items, title = parse_html_articles(fixture("usrfvg.html"), "https://usrfvg.gov.it/it/home/menu/notizie/")
    assert len(items) >= 10
    first = items[0]
    assert first["link"].startswith("https://usrfvg.gov.it/it/home/menu/notizie/article/")
    assert first["title"].startswith("Individuazione del personale docente")
    assert first["published"].startswith("2026-09-14")
    assert first["content"].startswith("Pubblicazione esiti operazioni")   # teaser in <div>, senza <p>
    assert len({i["link"] for i in items}) == len(items)


def test_parse_usr_liguria_gov():
    items, title = parse_html_articles(fixture("liguria.html"), "https://www.istruzioneliguria.gov.it/archivio-news")
    assert len(items) >= 15 and "Liguria" in title
    assert all(i["link"].startswith("https://www.istruzioneliguria.gov.it/") for i in items)
    assert any("PNRR3" in i["title"] for i in items)
    assert all(i["published"] for i in items)


def test_parse_mim_liferay_notizie():
    items, title = parse_html_articles(fixture("mim_molise.html"), "https://www.mim.gov.it/web/molise/notizie")
    assert len(items) == 12 and "MOLISE" in title
    assert all(i["link"].startswith("https://www.mim.gov.it/") for i in items)
    assert all(i["published"].startswith("2026") for i in items)
    assert all(len(i["title"]) >= 10 for i in items)
