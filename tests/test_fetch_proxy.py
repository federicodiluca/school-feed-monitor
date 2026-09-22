"""Lettura delle fonti attraverso il ponte europeo (deploy/eu-proxy).

Alcuni siti non rispondono agli IP esteri: i domini configurati passano sempre dal ponte,
gli altri solo come seconda possibilità dopo un errore di rete.
"""
import pytest
import requests

from sfm import source_parser
from sfm.source_parser import SourceError, fetch_url

PROXY = "https://proxy.example"
CALABRIA = "https://www.istruzione.calabria.it/feed/"


class FakeResponse:
    def __init__(self, content=b"ok", status=200, content_type="application/rss+xml"):
        self.content = content
        self.status_code = status
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


@pytest.fixture
def calls(monkeypatch):
    """Registra le richieste HTTP e serve risposte finte. `calls['answer']` decide l'esito."""
    recorded = []

    def fake_get(url, headers=None, params=None, timeout=None):
        recorded.append({"url": url, "params": params or {}, "headers": headers or {}})
        answer = recorded_answer[0](url)
        if isinstance(answer, Exception):
            raise answer
        return answer

    recorded_answer = [lambda url: FakeResponse()]
    monkeypatch.setattr(requests, "get", fake_get)
    return {"calls": recorded, "answer": recorded_answer}


@pytest.fixture
def proxy_env(monkeypatch):
    values = {"SFM_FETCH_PROXY": PROXY, "SFM_FETCH_PROXY_KEY": "segreto",
              "SFM_FETCH_PROXY_HOSTS": "istruzione.calabria.it,uspmc.sinp.net"}
    monkeypatch.setattr(source_parser, "env", lambda key, default=None: values.get(key, default))
    return values


def test_configured_hosts_go_straight_through_the_bridge(calls, proxy_env):
    data, content_type = fetch_url(CALABRIA)
    assert data == b"ok" and content_type == "application/rss+xml"
    (call,) = calls["calls"]
    assert call["url"] == PROXY + "/fetch" and call["params"] == {"url": CALABRIA}
    assert call["headers"]["X-Sfm-Key"] == "segreto"


def test_subdomains_of_a_configured_host_use_the_bridge_too(calls, proxy_env):
    fetch_url("https://qualcosa.istruzione.calabria.it/x/")
    assert calls["calls"][0]["url"] == PROXY + "/fetch"


def test_other_sites_are_read_directly(calls, proxy_env):
    fetch_url("https://www.mim.gov.it/web/guest/news")
    assert calls["calls"][0]["url"] == "https://www.mim.gov.it/web/guest/news"
    assert "X-Sfm-Key" not in calls["calls"][0]["headers"]


def test_a_network_error_gets_a_second_chance_from_europe(calls, proxy_env):
    calls["answer"][0] = lambda url: (FakeResponse(b"dal ponte") if url.startswith(PROXY)
                                      else requests.ConnectTimeout("timeout"))
    data, _ = fetch_url("https://www.istruzionepotenza.it/")
    assert data == b"dal ponte"
    assert [c["url"] for c in calls["calls"]] == ["https://www.istruzionepotenza.it/", PROXY + "/fetch"]


def test_if_the_bridge_fails_too_the_original_error_is_reported(calls, proxy_env):
    calls["answer"][0] = lambda url: requests.ConnectTimeout("timeout")
    with pytest.raises(SourceError, match="istruzionepotenza"):
        fetch_url("https://www.istruzionepotenza.it/")
    assert len(calls["calls"]) == 2


def test_a_configured_host_is_not_retried_directly(calls, proxy_env):
    """Se il ponte non risponde è inutile provare in diretta: quel sito ci blocca."""
    calls["answer"][0] = lambda url: requests.ConnectTimeout("timeout")
    with pytest.raises(SourceError):
        fetch_url(CALABRIA)
    assert len(calls["calls"]) == 1


def test_without_a_bridge_nothing_changes(calls, monkeypatch):
    monkeypatch.setattr(source_parser, "env", lambda key, default=None: default)
    calls["answer"][0] = lambda url: requests.ConnectTimeout("timeout")
    with pytest.raises(SourceError):
        fetch_url(CALABRIA)
    assert len(calls["calls"]) == 1 and calls["calls"][0]["url"] == CALABRIA
