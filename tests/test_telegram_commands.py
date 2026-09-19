import pytest

import sfm.db as db
import sfm.telegram_commands as tc
from sfm.db_user import add_user, get_user, update_keywords


def update(text, chat_id=1, username="alice", update_id=1):
    return {
        "update_id": update_id,
        "message": {"text": text, "chat": {"id": chat_id, "username": username}},
    }


# --- parse_command --------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("/start", ("start", "")),
    ("  /Start  ", ("start", "")),
    ("/setkeywords a, b", ("setkeywords", "a, b")),
    ("/setkeywords@CheckFeedBot a, b", ("setkeywords", "a, b")),
    ("/latest 3", ("latest", "3")),
    ("ciao", (None, "")),
    ("", (None, "")),
    (None, (None, "")),
    ("/", (None, "")),
])
def test_parse_command(text, expected):
    assert tc.parse_command(text) == expected


# --- handle_update dispatch ----------------------------------------------

def test_handle_update_ignores_non_messages_and_plain_text(sent_messages):
    assert tc.handle_update({"update_id": 1, "edited_message": {"text": "/start"}}) is None
    assert tc.handle_update(update("ciao bot")) is None
    assert tc.handle_update({"update_id": 1, "message": {"text": "/start"}}) is None  # senza chat
    assert sent_messages == []


def test_unknown_command_replies(sent_messages):
    assert tc.handle_update(update("/startfoo")) == "startfoo"
    assert "non riconosciuto" in sent_messages[0]["text"]
    assert "/startfoo" in sent_messages[0]["text"]


# --- /start /stop ---------------------------------------------------------

def test_start_registers_user_and_sends_help(sent_messages):
    tc.handle_update(update("/start"))
    user = get_user(1)
    assert user and user["active"] and user["username"] == "alice"
    assert len(sent_messages) == 2
    assert "Benvenuto" in sent_messages[0]["text"]
    help_text = sent_messages[1]["text"]
    assert sent_messages[1]["parse_mode"] == "HTML"
    assert "• ✅ Feed Uno" in help_text and "• ✅ Feed Due" in help_text
    assert "/sources" in help_text and "/addsource" in help_text
    assert "Fetch ogni 15 minuti" in help_text
    assert "Report giornaliero alle 18:00" in help_text
    assert "Retention notizie e log: 3 giorni" in help_text


def test_stop_then_start_reactivates(sent_messages):
    tc.handle_update(update("/start"))
    tc.handle_update(update("/stop"))
    assert get_user(1)["active"] is False
    assert "disattivato" in sent_messages[-1]["text"]
    tc.handle_update(update("/start"))
    assert get_user(1)["active"] is True
    assert "Bentornato" in sent_messages[-2]["text"]


# --- keywords -------------------------------------------------------------

def test_setkeywords_adds_and_dedupes_case_insensitively(sent_messages):
    add_user(1)
    tc.handle_update(update("/setkeywords scuola, Docenti, GRADUATORIA FINALE"))
    assert get_user(1)["keywords"] == ["scuola", "Docenti", "GRADUATORIA FINALE"]
    assert "✅ Keyword aggiunte: scuola, Docenti, GRADUATORIA FINALE" in sent_messages[-1]["text"]
    assert "Totale keyword: 3" in sent_messages[-1]["text"]

    tc.handle_update(update("/setkeywords SCUOLA, prova"))
    assert get_user(1)["keywords"] == ["scuola", "Docenti", "GRADUATORIA FINALE", "prova"]
    assert "Già presenti: SCUOLA" in sent_messages[-1]["text"]

    tc.handle_update(update("/setkeywords scuola"))
    assert "già presenti" in sent_messages[-1]["text"]
    assert get_user(1)["keywords"] == ["scuola", "Docenti", "GRADUATORIA FINALE", "prova"]


def test_setkeywords_without_args_shows_usage(sent_messages):
    add_user(1)
    tc.handle_update(update("/setkeywords"))
    tc.handle_update(update("/setkeywords , ,"))
    assert all("Usa: /setkeywords" in m["text"] for m in sent_messages)
    assert get_user(1)["keywords"] == []


def test_setkeywords_registers_unknown_user_on_the_fly(sent_messages):
    tc.handle_update(update("/setkeywords scuola", chat_id=77))
    assert get_user(77)["keywords"] == ["scuola"]


def test_removekeywords(sent_messages):
    add_user(1)
    update_keywords(1, ["scuola", "Docenti", "prova"])

    tc.handle_update(update("/removekeywords DOCENTI, inesistente"))
    assert get_user(1)["keywords"] == ["scuola", "prova"]
    assert "Keyword rimosse: Docenti" in sent_messages[-1]["text"]
    assert "Non trovate: inesistente" in sent_messages[-1]["text"]
    assert "Keyword rimanenti: scuola, prova" in sent_messages[-1]["text"]

    tc.handle_update(update("/removekeywords nulla"))
    assert "Nessuna delle keyword" in sent_messages[-1]["text"]

    tc.handle_update(update("/removekeywords scuola, prova"))
    assert get_user(1)["keywords"] == []
    assert "Non hai più keyword" in sent_messages[-1]["text"]

    tc.handle_update(update("/removekeywords scuola"))
    assert "Non hai keyword impostate" in sent_messages[-1]["text"]

    tc.handle_update(update("/removekeywords"))
    assert "Usa: /removekeywords" in sent_messages[-1]["text"]


def test_keywords_command_lists_or_reports_none(sent_messages):
    """Regressione: con keywords vuote rispondeva 'Le tue keyword attive (0)'."""
    add_user(1)
    tc.handle_update(update("/keywords"))
    assert "Non hai keyword impostate" in sent_messages[-1]["text"]

    update_keywords(1, ["scuola", "A & B"])
    tc.handle_update(update("/keywords"))
    text = sent_messages[-1]["text"]
    assert "Le tue keyword attive (2)" in text
    assert "• scuola" in text and "• A &amp; B" in text
    assert sent_messages[-1]["parse_mode"] == "HTML"


def test_keywords_command_not_confused_with_setkeywords(sent_messages):
    add_user(1)
    update_keywords(1, ["x"])
    assert tc.handle_update(update("/keywords")) == "keywords"
    assert tc.handle_update(update("/setkeywords y")) == "setkeywords"
    assert get_user(1)["keywords"] == ["x", "y"]


# --- /commands /fetch /report /latest ------------------------------------

def test_commands_message(sent_messages):
    tc.handle_update(update("/commands"))
    assert "/setkeywords" in sent_messages[0]["text"]
    assert sent_messages[0]["parse_mode"] == "HTML"
    tc.handle_update(update("/help"))
    assert sent_messages[1]["text"] == sent_messages[0]["text"]


def test_fetch_command_reports_count(sent_messages, monkeypatch):
    monkeypatch.setattr(tc, "fetch_news", lambda: 3)
    tc.handle_update(update("/fetch"))
    assert "3 nuove" in sent_messages[-1]["text"]


def test_report_command_targets_requesting_chat(sent_messages, monkeypatch):
    called = []
    monkeypatch.setattr(tc, "generate_report", lambda target_chat_id=None: called.append(target_chat_id))
    tc.handle_update(update("/report", chat_id=5))
    assert called == [5]


def insert_news(n, source_id=1):
    conn = db.get_conn()
    for i in range(n):
        conn.execute(
            "INSERT INTO news (title, link, source, published_at, content, source_id) VALUES (?, ?, ?, ?, ?, ?)",
            (f"News {i} & co", f"https://x/{i}", "Src", f"2025-10-{(i % 28) + 1:02d} 10:00:00", "<p>c</p>", source_id),
        )
    conn.commit()
    conn.close()


def test_latest_default_and_bounds(sent_messages):
    tc.handle_update(update("/latest"))
    assert "Nessuna notizia" in sent_messages[-1]["text"]

    insert_news(8)
    tc.handle_update(update("/latest"))
    assert "Ultime 5 notizie" in sent_messages[-1]["text"]

    tc.handle_update(update("/latest 2"))
    assert "Ultime 2 notizie" in sent_messages[-1]["text"]

    tc.handle_update(update("/latest 0"))
    assert "Ultime 1 notizie" in sent_messages[-1]["text"]

    tc.handle_update(update("/latest 9999"))
    assert "Ultime 8 notizie" in sent_messages[-1]["text"]

    tc.handle_update(update("/latest abc"))
    assert "Ultime 5 notizie" in sent_messages[-1]["text"]


def test_latest_is_filtered_by_followed_sources(sent_messages):
    insert_news(3, source_id=1)
    tc.handle_update(update("/unfollow 1"))
    tc.handle_update(update("/latest"))
    assert "Nessuna notizia disponibile dalle fonti che segui" in sent_messages[-1]["text"]
    tc.handle_update(update("/follow 1"))
    tc.handle_update(update("/latest"))
    assert "Ultime 3 notizie" in sent_messages[-1]["text"]


def test_latest_escapes_html(sent_messages):
    insert_news(1)
    tc.handle_update(update("/latest 1"))
    text = sent_messages[-1]["text"]
    assert "<b>News 0 &amp; co</b>" in text
    assert '<a href="https://x/0">Src</a>' in text
    assert "<i>c</i>" in text


# --- handle_commands polling loop ----------------------------------------

def test_handle_commands_polls_with_timeout_and_advances_offset(monkeypatch):
    calls = []
    handled = []

    class Stop(Exception):
        pass

    responses = iter([
        {"ok": True, "result": [update("/commands", update_id=10), update("/commands", update_id=11)]},
        {"ok": False, "error_code": 409, "description": "Conflict"},
    ])

    def fake_get(url, params=None, timeout=None, **kw):
        calls.append({"params": dict(params), "timeout": timeout})
        try:
            payload = next(responses)
        except StopIteration:
            raise Stop()
        from tests.conftest import FakeResponse
        return FakeResponse(payload)

    slept = []

    def fake_sleep(s):
        slept.append(s)
        if len(slept) >= 2:
            raise Stop()

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(tc, "handle_update", lambda u: handled.append(u["update_id"]))
    monkeypatch.setattr(tc.time, "sleep", fake_sleep)

    with pytest.raises(Stop):
        tc.handle_commands()

    assert handled == [10, 11]
    assert calls[0]["params"]["offset"] is None
    assert calls[1]["params"]["offset"] == 12
    assert all(c["timeout"] > c["params"]["timeout"] for c in calls)
    assert slept and slept[0] == 5  # ok=False -> pausa, niente busy loop


# --- fonti ----------------------------------------------------------------

from sfm.db_sources import get_followed_source_ids, get_source, get_sources  # noqa: E402
from tests.fixtures import html_list_page, rss  # noqa: E402


def test_sources_lists_with_marks(sent_messages):
    add_user(1)
    tc.handle_update(update("/sources"))
    text = sent_messages[-1]["text"]
    assert "2/2 seguite" in text
    assert "✅ <b>1</b>. Feed Uno" in text and "✅ <b>2</b>. Feed Due" in text
    assert sent_messages[-1]["parse_mode"] == "HTML"


def test_follow_unfollow_flow(sent_messages):
    add_user(1)
    tc.handle_update(update("/unfollow 2"))
    assert get_followed_source_ids(1) == {1}
    assert "Non segui più: Feed Due" in sent_messages[-1]["text"]
    assert "❌ <b>2</b>. Feed Due" in sent_messages[-1]["text"]

    tc.handle_update(update("/unfollow all"))
    assert get_followed_source_ids(1) == set()
    assert "0/2 seguite" in sent_messages[-1]["text"]

    tc.handle_update(update("/follow 1, 2, 99, x"))
    assert get_followed_source_ids(1) == {1, 2}
    assert "Ora segui: Feed Uno, Feed Due" in sent_messages[-1]["text"]
    assert "Ignorate (non valide): 99, x" in sent_messages[-1]["text"]

    tc.handle_update(update("/follow"))
    assert "Usa: /follow" in sent_messages[-1]["text"]
    tc.handle_update(update("/unfollow 99"))
    assert "Nessuna fonte valida" in sent_messages[-1]["text"]


def test_follow_registers_unknown_user(sent_messages):
    tc.handle_update(update("/unfollow 1", chat_id=77))
    user = get_user(77)
    assert user is not None
    assert get_followed_source_ids(user["id"]) == {2}


def test_addsource_rss_via_autodiscovery_seeds_without_notifications(sent_messages, fake_sources):
    add_user(1)
    update_keywords(1, ["notizia"])
    fake_sources["https://fc.example.org/tutte-le-notizie/"] = html_list_page([], feed_href="https://fc.example.org/feed/")
    fake_sources["https://fc.example.org/feed/"] = rss(
        [{"title": "Prima notizia", "link": "https://fc.example.org/1"}, {"title": "Seconda notizia", "link": "https://fc.example.org/2"}],
        title="Ufficio VII",
    )

    tc.handle_update(update("/addsource https://fc.example.org/tutte-le-notizie/"))

    src = get_source(3)
    assert src["type"] == "rss" and src["url"] == "https://fc.example.org/feed/" and src["name"] == "Ufficio VII"
    assert src["origin"] == "user" and src["added_by"] == 1
    assert get_followed_source_ids(1) == {1, 2, 3}
    texts = [m["text"] for m in sent_messages]
    assert any("Controllo la fonte" in t for t in texts)
    done = texts[-1]
    assert "Fonte aggiunta: <b>Ufficio VII</b> (n. 3)" in done
    assert "Tipo: feed RSS" in done and "Notizie trovate: 2 (salvate 2 nuove, senza notifica)" in done
    assert not any("🚨" in t for t in texts)  # nessun alert per le notizie già pubblicate
    assert len(db.get_conn().execute("SELECT * FROM news WHERE source_id=3").fetchall()) == 2


def test_addsource_html_with_custom_name(sent_messages, fake_sources):
    add_user(1)
    items = [{"title": f"Notizia numero {i} abbastanza lunga", "link": f"/-/n{i}"} for i in range(3)]
    fake_sources["https://mim.example/novita"] = html_list_page(items, base="https://mim.example")
    tc.handle_update(update("/addsource https://mim.example/novita USR Marche"))
    src = get_source(3)
    assert src["type"] == "html" and src["name"] == "USR Marche"
    assert "Tipo: pagina HTML (scraping)" in sent_messages[-1]["text"]
    # nella lista è marcata come HTML e custom (tua)
    tc.handle_update(update("/sources"))
    assert "✅ <b>3</b>. USR Marche · HTML · custom (tua)" in sent_messages[-1]["text"]


def test_addsource_rejects_unreadable_url(sent_messages, fake_sources):
    add_user(1)
    fake_sources["https://www.example.org/"] = html_list_page([])
    tc.handle_update(update("/addsource https://www.example.org/"))
    assert "Non riesco a leggere notizie" in sent_messages[-1]["text"]
    assert len(get_sources()) == 2

    tc.handle_update(update("/addsource"))
    assert "Usa: /addsource" in sent_messages[-1]["text"]
    tc.handle_update(update("/addsource ciao"))
    assert "Usa: /addsource" in sent_messages[-1]["text"]


def test_addsource_existing_url_just_follows(sent_messages, fake_sources):
    add_user(1)
    tc.handle_update(update("/unfollow 1"))
    tc.handle_update(update("/addsource https://example.org/uno/feed/"))
    assert "Fonte già presente: Feed Uno (n. 1). Ora la segui." in sent_messages[-1]["text"]
    assert get_followed_source_ids(1) == {1, 2}
    assert fake_sources["__calls__"] == []  # nessun download


def test_removesource_rules(sent_messages, fake_sources):
    add_user(1)
    add_user(2)
    fake_sources["https://c.example.org/feed/"] = rss([{"title": "A", "link": "https://c.example.org/1"}])
    tc.handle_update(update("/addsource https://c.example.org/feed/ Custom", chat_id=1))

    tc.handle_update(update("/removesource 1", chat_id=1))
    assert "configurazione del bot" in sent_messages[-1]["text"]
    tc.handle_update(update("/removesource 3", chat_id=2))
    assert "solo le fonti che hai aggiunto tu" in sent_messages[-1]["text"]
    tc.handle_update(update("/removesource 3", chat_id=1))
    assert "Fonte rimossa: Custom" in sent_messages[-1]["text"]
    assert [s["id"] for s in get_sources()] == [1, 2]
    tc.handle_update(update("/removesource 3", chat_id=1))
    assert "Fonte non trovata" in sent_messages[-1]["text"]
    tc.handle_update(update("/removesource", chat_id=1))
    assert "Usa: /removesource" in sent_messages[-1]["text"]


# --- pulsanti inline di /sources -----------------------------------------

def callback(data, chat_id=1, message_id=555, cq_id="cq1"):
    return {
        "update_id": 9,
        "callback_query": {
            "id": cq_id,
            "from": {"id": chat_id, "username": "alice"},
            "message": {"message_id": message_id, "chat": {"id": chat_id}},
            "data": data,
        },
    }


@pytest.fixture
def callback_calls(monkeypatch):
    calls = {"edits": [], "answers": []}
    monkeypatch.setattr(tc, "edit_message_text", lambda chat_id, message_id, text, parse_mode=None, reply_markup=None:
                        calls["edits"].append({"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup}))
    monkeypatch.setattr(tc, "answer_callback_query", lambda cq_id, text=None: calls["answers"].append({"id": cq_id, "text": text}))
    return calls


def test_sources_sends_inline_keyboard(sent_messages):
    add_user(1)
    tc.handle_update(update("/sources"))
    kb = sent_messages[-1]["reply_markup"]["inline_keyboard"]
    assert [b["text"] for row in kb[:-1] for b in row] == ["✅ Feed Uno", "✅ Feed Due"]
    assert [b["callback_data"] for row in kb[:-1] for b in row] == ["src:t:1", "src:t:2"]
    assert [b["callback_data"] for b in kb[-1]] == ["src:all:1", "src:all:0"]
    assert "Tocca una fonte" in sent_messages[-1]["text"]


def test_callback_toggle_updates_message_and_answers(sent_messages, callback_calls):
    add_user(1)
    assert tc.handle_update(callback("src:t:2")) == "callback"
    assert get_followed_source_ids(1) == {1}
    assert callback_calls["answers"] == [{"id": "cq1", "text": "❌ Non segui più: Feed Due"}]
    edit = callback_calls["edits"][-1]
    assert edit["chat_id"] == 1 and edit["message_id"] == 555
    assert "1/2 seguite" in edit["text"] and "❌ <b>2</b>. Feed Due" in edit["text"]
    assert [b["text"] for row in edit["reply_markup"]["inline_keyboard"][:-1] for b in row] == ["✅ Feed Uno", "❌ Feed Due"]

    tc.handle_update(callback("src:t:2", cq_id="cq2"))
    assert get_followed_source_ids(1) == {1, 2}
    assert callback_calls["answers"][-1]["text"] == "✅ Ora segui: Feed Due"
    assert sent_messages == []  # nessun nuovo messaggio: si modifica quello esistente


def test_callback_all_none_and_invalid(sent_messages, callback_calls):
    add_user(1)
    tc.handle_update(callback("src:all:0"))
    assert get_followed_source_ids(1) == set()
    assert "Non segui nessuna" in callback_calls["answers"][-1]["text"]
    tc.handle_update(callback("src:all:1"))
    assert get_followed_source_ids(1) == {1, 2}
    n_edits = len(callback_calls["edits"])
    tc.handle_update(callback("src:all:1"))          # già tutte: niente edit (Telegram lo rifiuterebbe)
    assert len(callback_calls["edits"]) == n_edits
    assert "Segui tutte" in callback_calls["answers"][-1]["text"]

    tc.handle_update(callback("src:t:999"))
    assert callback_calls["answers"][-1]["text"] == "Fonte non più disponibile"
    n_edits = len(callback_calls["edits"])
    tc.handle_update(callback("boh"))
    assert callback_calls["answers"][-1]["text"] is None   # sconosciuto: chiude lo spinner e basta
    assert len(callback_calls["edits"]) == n_edits


def test_callback_registers_unknown_user(sent_messages, callback_calls):
    tc.handle_update(callback("src:t:1", chat_id=42))
    user = get_user(42)
    assert user is not None
    assert get_followed_source_ids(user["id"]) == {2}


def test_callback_error_is_answered_not_raised(sent_messages, callback_calls, monkeypatch):
    add_user(1)
    monkeypatch.setattr(tc, "set_user_source", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db")))
    tc.handle_update(callback("src:t:1"))
    assert callback_calls["answers"][-1]["text"] == "Errore, riprova"
