"""Il sito statico provato in un browser finto (jsdom): è l'unico modo per accorgersi che
un filtro o il configuratore si sono rotti, visto che lì la logica è tutta JavaScript.
Si salta se node o jsdom non sono disponibili."""
import json
import os
import shutil
import subprocess

import pytest

from scripts.build_site import build
from sfm.catalog import load_catalog
from sfm.db_news import add_news
from sfm.db_sources import get_sources, sync_config_sources

CHECK = os.path.join(os.path.dirname(__file__), "site_check.js")


def _has_jsdom():
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require.resolve('jsdom')"], capture_output=True, text=True)
    return probe.returncode == 0


@pytest.mark.skipif(not _has_jsdom(), reason="node con jsdom non disponibile")
def test_the_static_site_works_in_a_browser(tmp_path, monkeypatch):
    catalog = [e for e in load_catalog() if e["kind"] == "mim" or e["region"] in ("Sicilia", "Emilia-Romagna")]
    monkeypatch.setattr("web.get_config", lambda: {"sites": catalog})
    sync_config_sources(catalog)
    sources = {s["name"]: s for s in get_sources()}
    for i in range(40):
        s = sources["USP Bologna"] if i % 2 else sources["USP Palermo"]
        add_news(f"Graduatorie A041 numero {i}" if i % 3 else f"Convocazione sostegno {i}",
                 f"https://esempio.it/n/{i}", s["name"], "2026-09-21 09:00:00",
                 "testo con trasferimenti e graduatorie", source_id=s["id"])

    site = build(str(tmp_path / "site"), base_url="https://esempio.github.io/school-feed-monitor",
                 bot_username="SfmBot")
    result = subprocess.run(["node", CHECK, site], capture_output=True, text=True, timeout=180,
                            cwd=_jsdom_dir())
    print(result.stdout, result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def _jsdom_dir():
    """jsdom può essere installato nel progetto o globalmente: node lo cerca risalendo."""
    return os.path.dirname(os.path.dirname(os.path.abspath(CHECK)))
