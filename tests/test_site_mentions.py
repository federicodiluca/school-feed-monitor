"""Il sito deve comparire dove l'utente lo cerca: benvenuto, aiuto, riepilogo, configurazione."""
import pytest

import sfm.telegram_commands as tc
from sfm.channels.telegram_channel import build_report, no_news_message
from sfm.env import site_url

SITE = "https://sito.esempio/sfm"


@pytest.fixture(autouse=True)
def site(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", SITE + "/")
    import sfm.env as env_module
    monkeypatch.setattr(env_module, "_loaded", True)     # non leggere il .env vero
    assert site_url() == SITE


def test_the_welcome_message_points_to_the_configurator(sent_messages):
    tc.handle_update({"update_id": 1, "message": {"text": "/start", "chat": {"id": 1},
                                                  "from": {"username": "alice"}}})
    assert f"{SITE}/configura" in sent_messages[1]["text"]


def test_the_help_message_carries_the_site(sent_messages):
    assert f"{SITE}" in tc.build_help_message()


def test_the_daily_report_ends_with_the_site(sent_messages):
    report = build_report([{"title": "T", "link": "https://x/1", "source": "S", "content": "c"}])
    assert report.rstrip().endswith(f"{SITE}/notizie")
    assert f"{SITE}/notizie" in no_news_message()


def test_the_report_flags_an_already_alerted_news_once(sent_messages):
    report = build_report([{"title": "T", "link": "https://x/1", "source": "S", "content": "c",
                            "matched_keywords": ["A041"], "already_alerted": True}])
    assert report.count("già segnalata") == 1
