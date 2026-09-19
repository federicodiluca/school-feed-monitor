"""Setup condiviso dei test.

I moduli `sfm.*` leggono config, DB e cartella log a import-time, quindi
impostiamo le variabili d'ambiente PRIMA di importarli.
"""
import json
import os
import tempfile

import pytest

_SESSION_DIR = tempfile.mkdtemp(prefix="sfm-tests-")
_CONFIG_PATH = os.path.join(_SESSION_DIR, "config.json")

TEST_CONFIG = {
    "telegram_token": "123456:TEST-TOKEN",
    "catalog": False,  # i test usano solo le due fonti qui sotto
    "machine_name": "Test-Machine",
    "sites": [
        {"name": "Feed Uno", "url": "https://example.org/uno/feed/"},
        {"name": "Feed Due", "url": "https://example.org/due/feed/"},
    ],
    "daily_report_time": "18:00",
    "polling_minutes": 15,
    "data_retention_days": 3,
    "disable_web_page_preview": True,
}

with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(TEST_CONFIG, f)

os.environ["SFM_CONFIG"] = _CONFIG_PATH
os.environ["SFM_DB_PATH"] = os.path.join(_SESSION_DIR, "test.db")
os.environ["SFM_LOG_DIR"] = os.path.join(_SESSION_DIR, "logs")
os.environ["SFM_ENV_FILE"] = os.path.join(_SESSION_DIR, "no.env")  # i test non leggono il .env reale

# Solo ora è sicuro importare i moduli del bot
import sfm.db as db  # noqa: E402
import sfm.telegram as telegram  # noqa: E402
import sfm.telegram_commands as telegram_commands  # noqa: E402
import sfm.channels.telegram_channel as telegram_channel  # noqa: E402
import sfm.source_parser as source_parser  # noqa: E402
from sfm.db_sources import sync_config_sources  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nessun test deve raggiungere la rete: requests.* e feedparser.parse falliscono di default."""
    def _blocked(*args, **kwargs):
        raise AssertionError(f"Accesso di rete non previsto: {args} {kwargs}")

    monkeypatch.setattr("requests.post", _blocked)
    monkeypatch.setattr("requests.get", _blocked)
    yield


@pytest.fixture(autouse=True)
def fresh_db():
    """Database SQLite vuoto per ogni test."""
    _remove_db_files()
    db.init_db()
    sync_config_sources(TEST_CONFIG["sites"])
    yield
    _remove_db_files()


def _remove_db_files():
    for suffix in ("", "-wal", "-shm"):
        path = db.DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def fake_sources(monkeypatch):
    """Mappa url -> bytes|str|Exception servita al posto della rete da source_parser.fetch_url.
    Ritorna il dict (modificabile dal test) e registra le url richieste in ['__calls__']."""
    table = {"__calls__": []}

    def fake_fetch(url):
        table["__calls__"].append(url)
        result = table.get(url)
        if result is None:
            raise source_parser.SourceError(f"404 {url}")
        if isinstance(result, Exception):
            raise result
        if isinstance(result, tuple):
            data, ct = result
        else:
            data, ct = result, ""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return data, ct

    monkeypatch.setattr(source_parser, "fetch_url", fake_fetch)
    return table


@pytest.fixture
def sent_messages(monkeypatch):
    """Cattura i messaggi che il bot invierebbe su Telegram, ovunque venga usato send_message."""
    messages = []

    def fake_send(text, parse_mode=None, chat_id=None, disable_web_page_preview=None, reply_markup=None):
        messages.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})
        return {"ok": True, "result": {}}

    # send_long_message di sfm.telegram chiama send_message dello stesso modulo
    monkeypatch.setattr(telegram, "send_message", fake_send)
    monkeypatch.setattr(telegram_commands, "send_message", fake_send)
    monkeypatch.setattr(telegram_channel, "send_message", fake_send)
    monkeypatch.setattr(telegram, "SLEEP_BETWEEN_MSGS", 0)
    return messages
