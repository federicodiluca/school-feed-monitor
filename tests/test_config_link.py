"""Configurazione dentro il link di /start (serve quando il sito è statico)."""
from sfm import config_link
from sfm.catalog import load_catalog


def test_roundtrip_keeps_sources_and_keywords():
    catalog = load_catalog()
    urls = [catalog[0]["url"], catalog[5]["url"], catalog[-1]["url"]]
    payload = config_link.encode(urls, ["A041", "trasferimenti"], catalog=catalog)
    assert payload and len(payload) <= config_link.MAX_PAYLOAD
    assert config_link.decode(payload, catalog=catalog) == {"urls": urls, "keywords": ["A041", "trasferimenti"]}


def test_payload_of_a_whole_region_still_fits():
    catalog = load_catalog()
    urls = [e["url"] for e in catalog if e.get("region") == "Sicilia" or e["kind"] == "mim"]
    assert len(urls) > 5
    payload = config_link.encode(urls, ["graduatorie"], catalog=catalog)
    assert payload and len(payload) <= config_link.MAX_PAYLOAD


def test_too_many_keywords_do_not_fit_and_are_refused():
    catalog = load_catalog()
    long_words = ["assegnazioni provvisorie", "utilizzazioni", "graduatorie di istituto"]
    assert config_link.encode([catalog[0]["url"]], long_words, catalog=catalog) is None
    # senza parole chiave le stesse fonti ci stanno
    assert config_link.encode([catalog[0]["url"]], [], catalog=catalog)


def test_broken_or_foreign_payloads_are_rejected():
    assert config_link.decode("") is None
    assert config_link.decode("ABCD1234") is None            # codice usa-e-getta, non un payload
    assert config_link.decode("C1***") is None
    assert config_link.decode("C1" + "AA") is None           # troppo corto
    assert config_link.encode(["https://sito.sconosciuto/x"], []) is None
    assert not config_link.looks_like_payload("ABCD1234")


def test_unknown_sources_are_ignored_not_shifted():
    catalog = load_catalog()
    payload = config_link.encode([catalog[3]["url"], "https://non-in-catalogo/x"], catalog=catalog)
    assert config_link.decode(payload, catalog=catalog)["urls"] == [catalog[3]["url"]]


def test_catalog_growth_does_not_move_existing_sources():
    catalog = load_catalog()
    payload = config_link.encode([catalog[2]["url"]], ["x"], catalog=catalog)
    grown = catalog + [{"url": "https://nuova.fonte/x", "name": "Nuova", "kind": "other", "region": None}]
    assert config_link.decode(payload, catalog=grown)["urls"] == [catalog[2]["url"]]
