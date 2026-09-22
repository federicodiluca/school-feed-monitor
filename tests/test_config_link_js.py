"""Il link di configurazione lo costruisce il browser e lo rilegge il bot: le due
implementazioni (web/static/app.js e sfm/config_link.py) devono produrre lo stesso payload.
Se `node` non c'è (CI minimale, macchina di sviluppo senza Node) il test si salta."""
import json
import os
import shutil
import subprocess

import pytest

from sfm import config_link
from sfm.catalog import load_catalog

APP_JS = os.path.join(os.path.dirname(__file__), "..", "web", "static", "app.js")
RUNNER = """
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const fn = src.slice(src.indexOf("function encodePayload"), src.indexOf("// --- notizie"));
const encodePayload = new Function("var MAX_PAYLOAD = " + process.argv[4] + ";" + fn + "; return encodePayload;")();
const [indexes, size, keywords] = JSON.parse(process.argv[3]);
console.log(JSON.stringify(encodePayload(indexes, size, keywords)));
"""


def js_payload(tmp_path, indexes, size, keywords):
    runner = tmp_path / "runner.js"
    runner.write_text(RUNNER, encoding="utf-8")
    out = subprocess.run(["node", str(runner), os.path.abspath(APP_JS),
                          json.dumps([indexes, size, keywords]), str(config_link.MAX_PAYLOAD)],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout.strip())


@pytest.fixture(autouse=True)
def node_required():
    if not shutil.which("node"):
        pytest.skip("node non disponibile")


def test_browser_and_bot_agree_on_the_payload(tmp_path):
    catalog = load_catalog()
    cases = [([0], ["A041"]), ([0, 5, len(catalog) - 1], ["A041", "trasf"]), ([1, 2, 3], [])]
    for indexes, keywords in cases:
        from_js = js_payload(tmp_path, indexes, len(catalog), keywords)
        assert from_js == config_link.encode_indexes(indexes, len(catalog), keywords)
        decoded = config_link.decode(from_js, catalog=catalog)
        assert decoded["urls"] == [catalog[i]["url"] for i in indexes]
        assert decoded["keywords"] == keywords


def test_browser_refuses_payloads_the_bot_could_not_receive(tmp_path):
    catalog = load_catalog()
    long_keywords = ["assegnazioni provvisorie", "utilizzazioni", "graduatorie di istituto"]
    assert js_payload(tmp_path, [0], len(catalog), long_keywords) is None
    assert config_link.encode_indexes([0], len(catalog), long_keywords) is None
