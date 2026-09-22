from datetime import datetime

import sfm.digest as digest
import sfm.news_fetcher as news_fetcher
import sfm.report_generator as report_generator
from sfm.db_deliveries import delivered_news_ids
from sfm.db_news import add_news
from sfm.db_sources import set_user_source
from sfm.db_user import add_user, get_user_by_id, set_digest_time, update_keywords
from tests.fixtures import rss

UNO = "https://example.org/uno/feed/"


def insert_today(title, link, content="", source="Feed Uno", source_id=1):
    return add_news(title, link, source, datetime.now().astimezone().isoformat(), content, source_id=source_id)


# --- alert immediati -----------------------------------------------------------

def test_annotate_marks_matches_first_and_already_alerted():
    user = {"id": 1, "keywords": ["A041", "trasferimenti"]}
    items = [
        {"id": 1, "title": "Nulla", "content": ""},
        {"id": 2, "title": "Trasferimenti 2026", "content": ""},
        {"id": 3, "title": "Cattedre A041", "content": "<p>classe A041</p>"},
    ]
    out = digest.annotate(items, user, alerted_ids={3})
    assert [n["id"] for n in out] == [2, 3, 1]
    assert out[0]["matched_keywords"] == ["trasferimenti"] and out[0]["already_alerted"] is False
    assert out[1]["matched_keywords"] == ["A041"] and out[1]["already_alerted"] is True
    assert out[2]["matched_keywords"] == []


def test_build_user_digest_filters_sources_and_highlights():
    add_user(1); update_keywords(1, ["docenti"])
    set_user_source(1, 2, False)
    insert_today("Concorso docenti", "https://x/1", source_id=1)
    insert_today("Altro", "https://x/2", source_id=1)
    insert_today("Da Due docenti", "https://x/3", source="Feed Due", source_id=2)
    items = digest.build_user_digest(get_user_by_id(1))
    assert [n["link"] for n in items] == ["https://x/1", "https://x/2"]
    assert items[0]["matched_keywords"] == ["docenti"]


def test_is_due_uses_user_time_or_global_default_and_daily_guard():
    today = f"{datetime.now():%Y-%m-%d}"
    at = lambda h, m: datetime.now().replace(hour=h, minute=m)
    # default globale del test config: 18:00
    assert digest.is_due({"digest_time": None}, at(17, 59)) is False
    assert digest.is_due({"digest_time": None}, at(18, 0)) is True
    assert digest.is_due({"digest_time": "07:30"}, at(7, 29)) is False
    assert digest.is_due({"digest_time": "07:30"}, at(9, 0)) is True
    assert digest.is_due({"digest_time": "boh"}, at(18, 5)) is True      # orario non valido → default
    assert digest.is_due({"digest_time": "07:30", "last_digest_date": today}, at(9, 0)) is False


def test_run_digests_sends_once_per_day_and_respects_time(sent_messages):
    add_user(1)                                    # id 1: default 18:00
    add_user(2); set_digest_time(2, "08:00")
    insert_today("Oggi", "https://x/1")
    at = lambda h, m: datetime.now().replace(hour=h, minute=m)

    assert digest.run_digests(now=at(7, 0)) == 0
    assert digest.run_digests(now=at(8, 0)) == 1
    assert [m["chat_id"] for m in sent_messages] == [2]
    assert digest.run_digests(now=at(8, 1)) == 0        # già inviato oggi
    assert digest.run_digests(now=at(18, 30)) == 1
    assert [m["chat_id"] for m in sent_messages] == [2, 1]
    assert digest.run_digests(now=at(23, 0)) == 0


def test_run_digests_force_sends_to_everyone(sent_messages):
    add_user(1); add_user(2)
    assert digest.run_digests(force=True) == 2
    assert sorted(m["chat_id"] for m in sent_messages) == [1, 2]


def test_run_digests_isolates_user_errors(sent_messages, monkeypatch):
    add_user(1); add_user(2)
    original = digest.send_user_digest

    def flaky(user, now=None, mark=True):
        if user["id"] == 1:
            raise RuntimeError("boom")
        return original(user, now=now, mark=mark)

    monkeypatch.setattr(digest, "send_user_digest", flaky)
    assert digest.run_digests(force=True) == 1
    assert [m["chat_id"] for m in sent_messages] == [2]


def test_manual_report_does_not_consume_daily_guard(sent_messages):
    add_user(5)
    report_generator.generate_report(target_chat_id=5)
    assert [m["chat_id"] for m in sent_messages] == [5]
    assert get_user_by_id(1)["last_digest_date"] is None


