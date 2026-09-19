import re

import pytest

import sfm.digest as digest
import web.auth as auth
from sfm import mailer, notifier
from sfm.channels import email_channel
from sfm.db_news import add_news
from sfm.db_user import consume_email_token, create_email_token, get_user_by_email
from tests.test_web import EMAIL, csrf, login, register
from web import create_app, security


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})
    security.reset_rate_limits()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_email", lambda to, subject, html, text=None: sent.append({"to": to, "subject": subject, "html": html, "text": text}) or True)
    return sent


def _link(mail):
    m = re.search(r"https://sfm\.example/verifica-email/[A-Za-z0-9_-]+", mail["text"])
    assert m
    return m.group(0).replace("https://sfm.example", "")


def test_email_tokens_roundtrip_and_resend_guard():
    assert create_email_token(1, "tok1") is True
    assert create_email_token(1, "tok2") is False        # troppo presto
    assert consume_email_token("tok1", "verify") == 1
    assert consume_email_token("tok1", "verify") is None  # usa-e-getta
    assert consume_email_token("nope") is None
    assert consume_email_token("tok1", "reset") is None


def test_register_sends_verification_and_channel_stays_off_until_verified(client, outbox):
    register(client)
    user = get_user_by_email(EMAIL)
    assert user["email_verified"] is False and user["notify_email"] is True
    assert notifier.channels_for(user) == []             # niente email finché non conferma
    assert len(outbox) == 1 and outbox[0]["to"] == EMAIL and "Conferma" in outbox[0]["subject"]
    html = client.get("/account").get_data(as_text=True)
    assert "Conferma il tuo indirizzo email" in html and "da confermare" in html

    r = client.get(_link(outbox[0]), follow_redirects=True)
    assert "Indirizzo confermato" in r.get_data(as_text=True)
    user = get_user_by_email(EMAIL)
    assert user["email_verified"] is True and notifier.channels_for(user) == ["email"]
    assert "Conferma il tuo indirizzo email" not in client.get("/account").get_data(as_text=True)
    assert "confermata" in client.get("/account").get_data(as_text=True)


def test_verification_link_invalid_or_reused(client, outbox):
    register(client)
    link = _link(outbox[0])
    client.get(link)
    r = client.get(link, follow_redirects=True)
    assert "non valido o scaduto" in r.get_data(as_text=True)
    r = client.get("/verifica-email/xyz", follow_redirects=True)
    assert "non valido o scaduto" in r.get_data(as_text=True)


def test_verification_works_when_logged_out(client, outbox):
    register(client)
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    r = client.get(_link(outbox[0]))
    assert r.status_code == 302 and r.headers["Location"].endswith("/accedi")
    assert get_user_by_email(EMAIL)["email_verified"] is True


def test_resend_verification(client, outbox, monkeypatch):
    register(client)
    tok = csrf(client, "/account")
    r = client.post("/account/verifica/reinvia", data={"_csrf": tok}, follow_redirects=True)
    assert "già inviata da poco" in r.get_data(as_text=True) and len(outbox) == 1
    monkeypatch.setattr("sfm.db_user.EMAIL_TOKEN_RESEND_SECONDS", 0)
    r = client.post("/account/verifica/reinvia", data={"_csrf": tok}, follow_redirects=True)
    assert "Email di conferma inviata" in r.get_data(as_text=True) and len(outbox) == 2
    client.get(_link(outbox[1]))
    r = client.post("/account/verifica/reinvia", data={"_csrf": tok}, follow_redirects=True)
    assert "già confermato" in r.get_data(as_text=True)


def test_mailer_failure_does_not_break_registration(client, monkeypatch):
    monkeypatch.setattr(mailer, "send_email", lambda *a, **k: (_ for _ in ()).throw(mailer.EmailError("smtp down")))
    r = register(client)
    assert r.status_code == 200 and get_user_by_email(EMAIL) is not None


def test_digest_skips_unverified_email_users(client, outbox, monkeypatch):
    register(client)
    add_news("Oggi", "https://x/1", "Feed Uno", None, "", source_id=1)
    digests = []
    monkeypatch.setattr(email_channel, "send_email", lambda to, subject, html, text=None: digests.append(to) or True)
    assert digest.run_digests(force=True) == 0
    client.get(_link(outbox[0]))
    assert digest.run_digests(force=True) == 1 and digests == [EMAIL]


def test_google_users_are_verified(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid"); monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})
    c = app.test_client()
    from web import google_auth
    monkeypatch.setattr(google_auth, "fetch_google_identity", lambda: {"email": "g@gmail.com", "sub": "s1"})
    c.get("/accedi/google/callback")
    html = c.get("/accedi/google/completa").get_data(as_text=True)
    tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
    c.post("/accedi/google/completa", data={"_csrf": tok, "consent": "on"})
    assert get_user_by_email("g@gmail.com")["email_verified"] is True


def test_verification_email_content():
    subject, html, text = email_channel.format_verification("https://sfm.example/verifica-email/abc")
    assert "Conferma" in subject and 'href="https://sfm.example/verifica-email/abc"' in html
    assert "https://sfm.example/verifica-email/abc" in text and "48 ore" in text


# --- password dimenticata --------------------------------------------------------------

def _reset_link(mail):
    m = re.search(r"https://sfm\.example/reimposta-password/[A-Za-z0-9_-]+", mail["text"])
    assert m
    return m.group(0).replace("https://sfm.example", "")


def test_forgot_password_flow(client, outbox):
    register(client)
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    outbox.clear()

    html = client.get("/accedi").get_data(as_text=True)
    assert "Password dimenticata?" in html
    tok = csrf(client, "/password-dimenticata")
    r = client.post("/password-dimenticata", data={"_csrf": tok, "email": "nessuno@scuola.it"}, follow_redirects=True)
    assert "indirizzo è registrato" in r.get_data(as_text=True) and outbox == []   # nessuna rivelazione

    r = client.post("/password-dimenticata", data={"_csrf": tok, "email": EMAIL}, follow_redirects=True)
    assert "indirizzo è registrato" in r.get_data(as_text=True)
    assert len(outbox) == 1 and "Reimposta" in outbox[0]["subject"] and "1 ora" in outbox[0]["text"]
    link = _reset_link(outbox[0])

    tok = csrf(client, link)
    r = client.post(link, data={"_csrf": tok, "new": "corta"})
    assert r.status_code == 400
    r = client.post(link, data={"_csrf": tok, "new": "nuovissima-password-1"}, follow_redirects=True)
    assert "Password aggiornata" in r.get_data(as_text=True)
    assert client.get("/account").status_code == 200                       # loggato
    assert get_user_by_email(EMAIL)["email_verified"] is True              # ha ricevuto l'email → verificata

    client.post("/esci", data={"_csrf": csrf(client, "/")})
    assert login(client, password="nuovissima-password-1").status_code == 302
    r = client.post(link, data={"_csrf": csrf(client, link), "new": "altra-password-lunga"}, follow_redirects=True)
    assert "non valido o scaduto" in r.get_data(as_text=True)                # usa-e-getta


def test_reset_token_has_short_ttl():
    from sfm.db import get_conn
    assert create_email_token(1, "r1", "reset") is True
    conn = get_conn()
    row = conn.execute("SELECT (julianday(expires_at) - julianday(created_at)) * 24 AS hours FROM email_tokens WHERE token='r1'").fetchone()
    conn.close()
    assert 0.9 < row["hours"] < 1.1
