"""Il ponte europeo (deploy/eu-proxy) è esposto su internet: deve rispondere solo per i
domini ammessi e solo a chi ha la chiave."""
import importlib.util
import os
import sys

import pytest
import requests

MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "deploy", "eu-proxy", "main.py")
KEY = "chiave-di-prova"


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "istruzione.calabria.it, uspmc.sinp.net")
    monkeypatch.setenv("PROXY_KEY", KEY)
    spec = importlib.util.spec_from_file_location("eu_proxy_main", os.path.abspath(MODULE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["eu_proxy_main"] = module
    spec.loader.exec_module(module)
    module.app.config["TESTING"] = True
    return module


@pytest.fixture
def upstream(monkeypatch, proxy):
    """Sostituisce la lettura del sito di origine; registra le URL richieste."""
    asked = []

    class FakeRaw:
        def __init__(self, body):
            self._body = body

        def read(self, size, decode_content=True):
            return self._body[:size]

    class FakeResponse:
        def __init__(self, body):
            self.raw = FakeRaw(body)
            self.status_code = 200
            self.headers = {"content-type": "application/rss+xml"}

    def fake_get(url, headers=None, timeout=None, stream=None):
        asked.append(url)
        if url in _errors:
            raise requests.ConnectTimeout("timeout")
        return FakeResponse(_body[0])

    _body = [b"<rss>ok</rss>"]
    _errors = set()
    monkeypatch.setattr(proxy.requests, "get", fake_get)
    return {"asked": asked, "body": _body, "errors": _errors}


def get(proxy, url, key=KEY):
    headers = {"X-Sfm-Key": key} if key is not None else {}
    return proxy.app.test_client().get("/fetch", query_string={"url": url}, headers=headers)


def test_serves_an_allowed_domain_to_who_has_the_key(proxy, upstream):
    r = get(proxy, "https://www.istruzione.calabria.it/feed/")
    assert r.status_code == 200 and r.data == b"<rss>ok</rss>"
    assert r.mimetype == "application/rss+xml"
    assert upstream["asked"] == ["https://www.istruzione.calabria.it/feed/"]


def test_refuses_without_the_key_and_never_calls_the_origin(proxy, upstream):
    assert get(proxy, "https://www.istruzione.calabria.it/feed/", key=None).status_code == 403
    assert get(proxy, "https://www.istruzione.calabria.it/feed/", key="sbagliata").status_code == 403
    assert upstream["asked"] == []


def test_is_not_an_open_proxy(proxy, upstream):
    for url in ("https://example.com/", "http://169.254.169.254/latest/meta-data/",
                "file:///etc/passwd", "https://calabria.it.altro.example/x",
                "https://istruzione.calabria.it.evil.example/x", ""):
        assert get(proxy, url).status_code == 403, url
    assert upstream["asked"] == []


def test_accepts_subdomains_of_an_allowed_host(proxy, upstream):
    assert get(proxy, "https://www.uspmc.sinp.net/tutte-le-notizie/").status_code == 200


def test_refuses_answers_that_are_too_big(proxy, upstream):
    proxy.MAX_BYTES = 10
    upstream["body"][0] = b"x" * 50
    assert get(proxy, "https://www.uspmc.sinp.net/x").status_code == 502


def test_an_unreachable_origin_becomes_a_502(proxy, upstream):
    upstream["errors"].add("https://www.uspmc.sinp.net/x")
    assert get(proxy, "https://www.uspmc.sinp.net/x").status_code == 502


def test_health_says_which_domains_are_allowed(proxy):
    body = proxy.app.test_client().get("/health").get_json()
    assert body["ok"] and body["hosts"] == ["istruzione.calabria.it", "uspmc.sinp.net"]
