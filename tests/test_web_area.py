"""Onboarding 'Dove insegni?' e fonti raggruppate per area (catalogo USR/USP)."""
import pytest

from sfm.catalog import group_sources, load_catalog, provinces_by_region, sources_for_area
from sfm.db_sources import add_user_source, follow_area, follow_areas, get_followed_source_ids, get_sources, get_user_sources, sync_config_sources, user_area, user_areas
from sfm.db_user import get_user_by_email
from tests.test_web import EMAIL, csrf, register
from web import create_app, security


@pytest.fixture
def catalog_db():
    sync_config_sources(load_catalog())   # sostituisce le due fonti di test con il catalogo reale
    return {s["name"]: s for s in get_sources()}


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})
    security.reset_rate_limits()
    return app


# --- logica pura ---------------------------------------------------------------

def test_group_sources_orders_national_regions_other():
    sources = [
        {"name": "Custom", "kind": "other", "region": None},
        {"name": "USP Bologna", "kind": "usp", "region": "Emilia-Romagna"},
        {"name": "USR Emilia-Romagna", "kind": "usr", "region": "Emilia-Romagna"},
        {"name": "MIM — Notizie", "kind": "mim", "region": None},
        {"name": "USR Abruzzo", "kind": "usr", "region": "Abruzzo"},
    ]
    groups = group_sources(sources)
    assert [g for g, _ in groups] == ["Nazionali", "Abruzzo", "Emilia-Romagna", "Altre fonti"]
    assert [s["name"] for s in dict(groups)["Emilia-Romagna"]] == ["USR Emilia-Romagna", "USP Bologna"]


def test_provinces_by_region_and_sources_for_area():
    cat = load_catalog()
    pbr = provinces_by_region(cat)
    assert "Bologna" in pbr["Emilia-Romagna"] and "Asti" in pbr["Piemonte"] and "Alessandria" in pbr["Piemonte"]
    chosen = sources_for_area(cat, "Piemonte", ["Asti"])
    names = {s["name"] for s in chosen}
    assert names == {"MIM — Notizie", "USR Piemonte", "USP Alessandria e Asti"}
    whole = sources_for_area(cat, "Emilia-Romagna")
    assert sum(1 for s in whole if s["kind"] == "usp") == 9 and any(s["kind"] == "mim" for s in whole)


# --- DB --------------------------------------------------------------------------

def test_follow_area_sets_follows_and_keeps_custom(catalog_db):
    register_user_id = 1
    from sfm.db_user import add_user
    add_user(1)
    custom, _ = add_user_source("Il mio sito", "https://custom.example/feed/", "rss", register_user_id)
    n = follow_area(register_user_id, "Emilia-Romagna", ["Bologna", "Rimini"])
    followed = get_followed_source_ids(register_user_id)
    assert n == 4   # MIM notizie + USR ER + USP BO + USP RN
    assert catalog_db["USP Bologna"]["id"] in followed and catalog_db["USP Rimini"]["id"] in followed
    assert catalog_db["USP Modena"]["id"] not in followed and catalog_db["USR Veneto"]["id"] not in followed
    assert custom["id"] in followed                                   # le custom non vengono toccate
    assert user_area(register_user_id) == ("Emilia-Romagna", ["Bologna", "Rimini"])

    follow_area(register_user_id, "Veneto")                            # cambio area: tutta la regione
    assert user_area(register_user_id)[0] == "Veneto"
    assert catalog_db["USP Bologna"]["id"] not in get_followed_source_ids(register_user_id)
    assert catalog_db["USP Verona"]["id"] in get_followed_source_ids(register_user_id)

    # più regioni: dove insegno + dove miro
    n = follow_areas(register_user_id, {"Marche": ["Pesaro e Urbino"], "Emilia-Romagna": ["Rimini"]})
    assert n == 5   # MIM + USR Marche + USP PU + USR ER + USP RN
    assert user_areas(register_user_id) == {"Emilia-Romagna": ["Rimini"], "Marche": ["Pesaro e Urbino"]}
    assert catalog_db["USP Verona"]["id"] not in get_followed_source_ids(register_user_id)


# --- web -----------------------------------------------------------------------------

def test_registration_leads_to_area_onboarding(app, catalog_db):
    c = app.test_client()
    r = register(c, follow=False)
    assert "/preferenze/area?benvenuto=1" in r.headers["Location"]
    html = c.get("/preferenze/area?benvenuto=1").get_data(as_text=True)
    assert "Iniziamo: dove insegni?" in html and 'name="regions" value="Emilia-Romagna"' in html
    assert 'data-region="Piemonte"' in html and 'value="Piemonte|Asti"' in html and "Salta" in html
    assert 'content="noindex, nofollow"' in html


def test_save_area_and_grouped_preferences(app, catalog_db):
    c = app.test_client()
    register(c)
    tok = csrf(c, "/preferenze/area")
    r = c.post("/preferenze/area", data={"_csrf": tok, "regions": ["Marte"]}, follow_redirects=True)
    assert "almeno una regione" in r.get_data(as_text=True)

    r = c.post("/preferenze/area", data={"_csrf": tok, "regions": ["Sicilia"], "provinces": ["Sicilia|Enna", "Lazio|Roma"]}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Area impostata: Sicilia (Enna)" in html and "segui 3 fonti" in html
    user = get_user_by_email(EMAIL)
    followed = {s["name"] for s in get_user_sources(user["id"]) if s["followed"]}
    assert followed == {"MIM — Notizie", "USR Sicilia", "USP Caltanissetta ed Enna"}

    # pagina preferenze: strip area, gruppi, gruppo Sicilia aperto, provincia mostrata
    # l'ufficio copre due province: l'area dedotta le mostra entrambe
    assert "Le tue aree:" in html and "Sicilia · Caltanissetta, Enna" in html
    assert 'class="source-group" open' in html and "<span>Sicilia</span>" in html and "<span>Nazionali</span>" in html
    assert "(Caltanissetta, Enna)" in html and 'id="sources-search"' in html
    # la form dell'area mostra la selezione corrente
    html = c.get("/preferenze/area").get_data(as_text=True)
    assert 'value="Sicilia" data-region="Sicilia" checked' in html and 'value="Sicilia|Enna" checked' in html and 'value="Sicilia|Caltanissetta" checked' in html
    assert 'value="Lazio" data-region="Lazio" checked' not in html


def test_preferences_save_still_works_with_catalog(app, catalog_db):
    c = app.test_client()
    register(c)
    tok = csrf(c, "/preferenze")
    bo = catalog_db["USP Bologna"]["id"]
    r = c.post("/preferenze", data={"_csrf": tok, "keywords": "A041", "sources": [str(bo)], "notify_email": "on", "alert_mode": "digest"}, follow_redirects=True)
    assert "Preferenze salvate" in r.get_data(as_text=True)
    user = get_user_by_email(EMAIL)
    assert get_followed_source_ids(user["id"]) == {bo}
