import sfm.db as db
import sfm.report_generator as report_generator
from sfm.utils import format_local_datetime
from sfm.db_sources import set_user_source
from sfm.db_user import add_user, deactivate_user


def insert_today(title, link, content="", source="S", source_id=1):
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO news (title, link, source, published_at, content, source_id) VALUES (?, ?, ?, datetime('now'), ?, ?)",
        (title, link, source, content, source_id),
    )
    conn.commit()
    conn.close()


def test_build_report_empty_returns_none():
    assert report_generator.build_report([]) is None


def test_build_report_escapes_fields_and_handles_missing_values():
    text = report_generator.build_report([
        {"title": "A & B <c>", "link": "https://x/?a=1&b=2", "source": "Src <1>", "content": "<p>Ciao</p>", "published_at": "2025-10-05 10:00:00"},
        {"title": None, "link": None, "source": None, "content": None, "published_at": None},
    ])
    assert "2 notizie trovate" in text
    assert "<b>A &amp; B &lt;c&gt;</b>" in text
    assert '<a href="https://x/?a=1&amp;b=2">Src &lt;1&gt;</a> — ' + format_local_datetime("2025-10-05 10:00:00") in text
    assert "<i>Ciao</i>" in text
    assert "Titolo non disponibile" in text
    assert "Sorgente sconosciuta" in text


def test_generate_report_to_target_chat(sent_messages):
    insert_today("Oggi", "https://x/today", "contenuto")
    report_generator.generate_report(target_chat_id=99)
    assert len(sent_messages) == 1
    assert sent_messages[0]["chat_id"] == 99
    assert "<b>Oggi</b>" in sent_messages[0]["text"]


def test_generate_report_no_news_broadcasts_placeholder(sent_messages):
    add_user(1)
    add_user(2)
    deactivate_user(2)
    report_generator.generate_report()
    assert [m["chat_id"] for m in sent_messages] == [1]
    assert "Nessuna notizia" in sent_messages[0]["text"]


def test_generate_report_broadcast_to_active_users(sent_messages):
    insert_today("Oggi", "https://x/today")
    add_user(1)
    add_user(2)
    add_user(3)
    deactivate_user(3)
    report_generator.generate_report()
    assert sorted(m["chat_id"] for m in sent_messages) == [1, 2]


def test_generate_report_without_users_sends_nothing(sent_messages):
    insert_today("Oggi", "https://x/today")
    report_generator.generate_report()
    assert sent_messages == []


def test_report_is_filtered_per_user_sources(sent_messages):
    insert_today("Da Uno", "https://x/1", source="Feed Uno", source_id=1)
    insert_today("Da Due", "https://x/2", source="Feed Due", source_id=2)
    add_user(1)
    add_user(2)
    set_user_source(2, 1, False)   # utente 2 non segue Feed Uno
    add_user(3)
    set_user_source(3, 1, False)
    set_user_source(3, 2, False)   # utente 3 non segue nulla

    report_generator.generate_report()

    by_chat = {m["chat_id"]: m["text"] for m in sent_messages}
    assert "Da Uno" in by_chat[1] and "Da Due" in by_chat[1] and "2 notizie" in by_chat[1]
    assert "Da Uno" not in by_chat[2] and "Da Due" in by_chat[2] and "1 notizie" in by_chat[2]
    assert "Nessuna notizia" in by_chat[3]


def test_manual_report_filtered_for_target(sent_messages):
    insert_today("Da Uno", "https://x/1", source_id=1)
    add_user(7)
    set_user_source(1, 1, False)   # user id 1 = telegram 7
    report_generator.generate_report(target_chat_id=7)
    assert [m["chat_id"] for m in sent_messages] == [7]
    assert "Nessuna notizia" in sent_messages[0]["text"]
