import re

import pytest

import sfm.telegram_commands as tc
from sfm.db_deliveries import delivered_news_ids, record_delivery
from sfm.db_sources import get_followed_source_ids, get_source_by_url, get_user_sources, set_user_source
from sfm.db_user import add_user, consume_link_code, get_user, get_user_by_email, get_users, update_keywords
from tests.fixtures import rss
from tests.test_web import EMAIL, PASSWORD, csrf, login, register
from web import create_app, google_auth, security


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example", "TELEGRAM_BOT_USERNAME": "SfmBot"})
    security.reset_rate_limits()
    return app


@pytest.fixture
def client(app):
    c = app.test_client()
    register(c)
    return c


# --- preferenze ------------------------------------------------------------------

def test_preferences_page_shows_current_state(client):
    html = client.get("/preferenze").get_data(as_text=True)
    assert 'value="1" checked' in html and 'value="2" checked' in html      # fonti di default seguite
    assert 'name="notify_email" checked' in html
    assert 'name="notify_telegram"' in html and "collega prima la chat" in html
    assert 'value="digest" checked' in html
    assert 'content="noindex, nofollow"' in html


def test_save_preferences(client):
    tok = csrf(client, "/preferenze")
    r = client.post("/preferenze", data={
        "_csrf": tok, "keywords": " A041 , trasferimenti,, graduatorie ", "sources": ["2"],
        "notify_email": "on", "alert_mode": "instant", "digest_time": "07:30",
    }, follow_redirects=True)
    assert "Preferenze salvate" in r.get_data(as_text=True)
    user = get_user_by_email(EMAIL)
    assert user["keywords"] == ["A041", "trasferimenti", "graduatorie"]
    assert user["alert_mode"] == "instant" and user["digest_time"] == "07:30" and user["notify_email"]
    assert get_followed_source_ids(user["id"]) == {2}

    # nessuna fonte, nessun canale, orario vuoto → default
    r = client.post("/preferenze", data={"_csrf": tok, "keywords": "", "alert_mode": "digest", "digest_time": ""}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "nessun canale attivo" in html
    user = get_user_by_email(EMAIL)
    assert user["keywords"] == [] and user["digest_time"] is None and not user["notify_email"]
    assert get_followed_source_ids(user["id"]) == set()


def test_save_preferences_validation(client):
    tok = csrf(client, "/preferenze")
    r = client.post("/preferenze", data={"_csrf": tok, "keywords": "x" * 61, "alert_mode": "digest"}, follow_redirects=True)
    assert "Massimo" in r.get_data(as_text=True)
    r = client.post("/preferenze", data={"_csrf": tok, "keywords": "ok", "alert_mode": "digest", "digest_time": "25:99"}, follow_redirects=True)
    assert "Orario" in r.get_data(as_text=True)
    assert get_user_by_email(EMAIL)["keywords"] == []


def test_telegram_checkbox_ignored_when_not_linked(client):
    tok = csrf(client, "/preferenze")
    client.post("/preferenze", data={"_csrf": tok, "keywords": "", "alert_mode": "digest", "notify_telegram": "on"})
    assert get_user_by_email(EMAIL)["notify_telegram"] is False


def test_preferences_require_login(app):
    c = app.test_client()
    assert c.get("/preferenze").status_code == 302


# --- aggiunta fonte ---------------------------------------------------------------

def test_add_source_from_web(client, fake_sources, sent_messages):
    fake_sources["https://usp.example/feed/"] = rss([{"title": "Notizia uno", "link": "https://usp.example/1"}] * 1 +
                                                    [{"title": "Notizia due", "link": "https://usp.example/2"}], title="USP Esempio")
    tok = csrf(client, "/preferenze")
    r = client.post("/preferenze/fonti", data={"_csrf": tok, "url": "https://usp.example/feed/"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Fonte aggiunta: USP Esempio (2 notizie trovate)" in html
    src = get_source_by_url("https://usp.example/feed/")
    user = get_user_by_email(EMAIL)
    assert src["origin"] == "user" and src["added_by"] == user["id"] and src["id"] in get_followed_source_ids(user["id"])
    assert sent_messages == []   # prima lettura senza notifiche

    r = client.post("/preferenze/fonti", data={"_csrf": tok, "url": "https://usp.example/feed/"}, follow_redirects=True)
    assert "già presente" in r.get_data(as_text=True)
    r = client.post("/preferenze/fonti", data={"_csrf": tok, "url": "https://rotta.example/"}, follow_redirects=True)
    assert "Non riesco a leggere" in r.get_data(as_text=True)
    r = client.post("/preferenze/fonti", data={"_csrf": tok, "url": "boh"}, follow_redirects=True)
    assert "Inserisci" in r.get_data(as_text=True)


# --- collegamento Telegram ------------------------------------------------------

def _generate_code(client):
    tok = csrf(client, "/preferenze")
    r = client.post("/preferenze/telegram/codice", data={"_csrf": tok}, follow_redirects=True)
    html = r.get_data(as_text=True)
    m = re.search(r"/link ([A-Z2-9]{8})", html)
    assert m and "t.me/SfmBot" in html
    return m.group(1)


def test_link_telegram_end_to_end(client, sent_messages):
    code = _generate_code(client)
    tc.handle_update({"update_id": 1, "message": {"text": f"/link {code.lower()}", "chat": {"id": 555, "username": "prof"}}})
    assert "Chat collegata" in sent_messages[-1]["text"] and EMAIL in sent_messages[-1]["text"]
    user = get_user_by_email(EMAIL)
    assert user["telegram_id"] == 555 and user["notify_telegram"] and user["username"] == "prof"
    assert consume_link_code(code) is None   # usa-e-getta

    html = client.get("/preferenze").get_data(as_text=True)
    assert "Chat collegata" in html and "@prof" in html
    tok = csrf(client, "/preferenze")
    client.post("/preferenze/telegram/scollega", data={"_csrf": tok})
    user = get_user_by_email(EMAIL)
    assert user["telegram_id"] is None and not user["notify_telegram"]


def test_link_invalid_or_expired_code(client, sent_messages):
    tc.handle_update({"update_id": 1, "message": {"text": "/link", "chat": {"id": 555}}})
    assert "Usa: /link" in sent_messages[-1]["text"]
    tc.handle_update({"update_id": 2, "message": {"text": "/link ZZZZZZZZ", "chat": {"id": 555}}})
    assert "non valido o scaduto" in sent_messages[-1]["text"]
    assert get_user(555) is None


def test_link_merges_existing_telegram_only_user(client, sent_messages):
    add_user(777, "vecchio"); update_keywords(777, ["docenti", "ATA"])
    old = get_user(777)
    set_user_source(old["id"], 1, False)
    record_delivery(old["id"], 42, "telegram", "alert")
    web_user = get_user_by_email(EMAIL)
    tok = csrf(client, "/preferenze")
    client.post("/preferenze", data={"_csrf": tok, "keywords": "ata, trasferimenti", "sources": ["1", "2"], "notify_email": "on", "alert_mode": "digest"})

    code = _generate_code(client)
    tc.handle_update({"update_id": 1, "message": {"text": f"/link {code}", "chat": {"id": 777, "username": "vecchio"}}})
    assert "Chat collegata" in sent_messages[-1]["text"]

    merged = get_user_by_email(EMAIL)
    assert merged["id"] == web_user["id"] and merged["telegram_id"] == 777
    assert merged["keywords"] == ["ata", "trasferimenti", "docenti"]          # unione senza duplicati (case-insensitive)
    assert get_followed_source_ids(merged["id"]) == {1, 2}                    # le scelte dell'account web prevalgono
    assert delivered_news_ids(merged["id"]) == {42}                           # log invii ereditato
    assert [u["telegram_id"] for u in get_users(active_only=False)] == [777]  # il vecchio utente non esiste più


def test_link_refuses_chat_of_another_web_account(client, app, sent_messages):
    other = app.test_client()
    register(other, email="altro@scuola.it")
    code = _generate_code(other)
    tc.handle_update({"update_id": 1, "message": {"text": f"/link {code}", "chat": {"id": 888}}})
    assert get_user_by_email("altro@scuola.it")["telegram_id"] == 888

    code = _generate_code(client)
    tc.handle_update({"update_id": 2, "message": {"text": f"/link {code}", "chat": {"id": 888}}})
    assert "già collegata a un altro account" in sent_messages[-1]["text"]
    assert get_user_by_email(EMAIL)["telegram_id"] is None


# --- Google ----------------------------------------------------------------------

@pytest.fixture
def gapp(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})
    security.reset_rate_limits()
    return app


def test_google_button_hidden_without_config(app):
    html = app.test_client().get("/accedi").get_data(as_text=True)
    assert "Accedi con Google" not in html
    assert app.test_client().get("/accedi/google").status_code == 302


def test_google_new_user_needs_consent_then_created(gapp, monkeypatch):
    c = gapp.test_client()
    assert "Accedi con Google" in c.get("/accedi").get_data(as_text=True)
    monkeypatch.setattr(google_auth, "fetch_google_identity", lambda: {"email": "G.User@Gmail.com", "sub": "sub-123"})

    r = c.get("/accedi/google/callback")
    assert r.status_code == 302 and r.headers["Location"].endswith("/accedi/google/completa")
    assert get_user_by_email("g.user@gmail.com") is None          # niente dati prima del consenso

    r = c.get("/accedi/google/completa")
    html = r.get_data(as_text=True)
    assert r.status_code == 200, (r.status_code, r.headers.get("Location"))
    assert "g.user@gmail.com" in html
    tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
    r = c.post("/accedi/google/completa", data={"_csrf": tok})
    assert r.status_code == 400
    r = c.post("/accedi/google/completa", data={"_csrf": tok, "consent": "on"})
    assert "/preferenze/area" in r.headers["Location"]
    user = get_user_by_email("g.user@gmail.com")
    assert user["google_sub"] == "sub-123" and user["consent_at"] and user["notify_email"]
    assert c.get("/preferenze").status_code == 200

    # password non utilizzabile
    c.post("/esci", data={"_csrf": csrf(c, "/")})   # il login rigenera il token CSRF
    assert login(c, email="g.user@gmail.com", password="qualsiasi").status_code == 401


def test_google_existing_email_logs_in_and_links_sub(gapp, monkeypatch):
    c = gapp.test_client()
    register(c)
    c.post("/esci", data={"_csrf": csrf(c, "/")})
    monkeypatch.setattr(google_auth, "fetch_google_identity", lambda: {"email": EMAIL, "sub": "sub-999"})
    r = c.get("/accedi/google/callback")
    assert r.headers["Location"].endswith("/account")
    assert get_user_by_email(EMAIL)["google_sub"] == "sub-999"
    assert c.get("/account").status_code == 200


def test_google_failure_redirects_to_login(gapp, monkeypatch):
    c = gapp.test_client()
    monkeypatch.setattr(google_auth, "fetch_google_identity", lambda: (_ for _ in ()).throw(RuntimeError("bad state")))
    r = c.get("/accedi/google/callback", follow_redirects=True)
    assert "non riuscito" in r.get_data(as_text=True)
    monkeypatch.setattr(google_auth, "fetch_google_identity", lambda: None)   # email non verificata
    r = c.get("/accedi/google/callback", follow_redirects=True)
    assert "non riuscito" in r.get_data(as_text=True)
