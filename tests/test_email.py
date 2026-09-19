import os
import smtplib

import pytest

import sfm.mailer as mailer
import sfm.notifier as notifier
from sfm.channels import email_channel
from sfm.env import load_env
from tests.conftest import FakeResponse


@pytest.fixture
def email_env(monkeypatch):
    """Imposta l'ambiente email per un test; ripulito a fine test."""
    def _set(**values):
        for k in ("EMAIL_BACKEND", "EMAIL_FROM", "EMAIL_REPLY_TO", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
                  "SMTP_PASSWORD", "SMTP_TLS", "RESEND_API_KEY", "APP_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        for k, v in values.items():
            monkeypatch.setenv(k, v)
    return _set


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.calls, self.sent = [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.calls.append("quit")

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.sent.append(msg)


# --- .env -------------------------------------------------------------------

def test_load_env_parses_file_without_overriding(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# commento\nA=1   # nota in coda\nB="due parole # no"\nC=\'x\'\nEXISTING=new\nbroken\n', encoding="utf-8")
    monkeypatch.setenv("EXISTING", "old")
    monkeypatch.delenv("A", raising=False); monkeypatch.delenv("B", raising=False); monkeypatch.delenv("C", raising=False)
    assert load_env(str(f)) == 3
    assert os.environ["A"] == "1" and os.environ["B"] == "due parole # no" and os.environ["C"] == "x"
    assert os.environ["EXISTING"] == "old"
    assert load_env(str(tmp_path / "missing")) == 0


# --- mailer -----------------------------------------------------------------

def test_backend_none_logs_and_returns_false(email_env):
    email_env(EMAIL_BACKEND="none")
    assert mailer.is_enabled() is False
    assert mailer.send_email("a@b.it", "s", "<p>h</p>", "t") is False


def test_smtp_backend_sends_multipart_message(email_env, monkeypatch):
    email_env(EMAIL_BACKEND="smtp", EMAIL_FROM="CheckFeed <noreply@x.it>", EMAIL_REPLY_TO="me@x.it",
              SMTP_HOST="smtp.example", SMTP_PORT="587", SMTP_USER="u", SMTP_PASSWORD="p")
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    assert mailer.is_enabled() is True
    assert mailer.send_email("prof@scuola.it", "Oggetto & co", "<p>ciao</p>", "ciao") is True

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example", 587)
    assert smtp.calls == ["ehlo", "starttls", "ehlo", ("login", "u", "p"), "quit"]
    msg = smtp.sent[0]
    assert msg["To"] == "prof@scuola.it" and msg["From"] == "CheckFeed <noreply@x.it>"
    assert msg["Subject"] == "Oggetto & co" and msg["Reply-To"] == "me@x.it"
    parts = {p.get_content_type(): p.get_content() for p in msg.iter_parts()}
    assert parts["text/plain"].strip() == "ciao" and "<p>ciao</p>" in parts["text/html"]


def test_smtp_ssl_and_no_auth(email_env, monkeypatch):
    email_env(EMAIL_BACKEND="smtp", EMAIL_FROM="a@x.it", SMTP_HOST="smtp.example", SMTP_PORT="465", SMTP_TLS="ssl")
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", None)  # non deve essere usato
    assert mailer.send_email("b@x.it", "s", "<p>h</p>") is True
    assert FakeSMTP.instances[0].calls == ["ehlo", "quit"]


def test_smtp_errors_become_email_error(email_env, monkeypatch):
    email_env(EMAIL_BACKEND="smtp", EMAIL_FROM="a@x.it", SMTP_HOST="smtp.example")

    class Failing(FakeSMTP):
        def send_message(self, msg):
            raise smtplib.SMTPRecipientsRefused({"b@x.it": (550, b"no")})

    monkeypatch.setattr(smtplib, "SMTP", Failing)
    with pytest.raises(mailer.EmailError):
        mailer.send_email("b@x.it", "s", "<p>h</p>")

    email_env(EMAIL_BACKEND="smtp", EMAIL_FROM="a@x.it")  # manca SMTP_HOST
    with pytest.raises(mailer.EmailError):
        mailer.send_email("b@x.it", "s", "<p>h</p>")
    with pytest.raises(mailer.EmailError):
        mailer.send_email("", "s", "<p>h</p>")


def test_resend_backend_posts_json(email_env, monkeypatch):
    email_env(EMAIL_BACKEND="resend", EMAIL_FROM="CheckFeed <noreply@x.it>", RESEND_API_KEY="re_test")
    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append((url, json, headers))
        return FakeResponse({"id": "abc"})

    monkeypatch.setattr("requests.post", fake_post)
    assert mailer.send_email("b@x.it", "s", "<p>h</p>", "t") is True
    url, payload, headers = calls[0]
    assert url == mailer.RESEND_API_URL and headers["Authorization"] == "Bearer re_test"
    assert payload == {"from": "CheckFeed <noreply@x.it>", "to": ["b@x.it"], "subject": "s", "html": "<p>h</p>", "text": "t"}

    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResponse({"message": "bad"}, status_code=422))
    with pytest.raises(mailer.EmailError):
        mailer.send_email("b@x.it", "s", "<p>h</p>")


def test_invalid_backend_raises(email_env):
    email_env(EMAIL_BACKEND="piccione", EMAIL_FROM="a@x.it")
    with pytest.raises(mailer.EmailError):
        mailer.send_email("b@x.it", "s", "<p>h</p>")


# --- email_channel: formattazione -----------------------------------------------

NEWS = {"title": "Concorso <docenti> & ATA", "link": "https://x/1?a=1&b=2", "source": "USR <ER>",
        "content": "<p>Testo <b>breve</b></p>", "published_at": "2026-09-10 08:00:00"}


def test_format_alert_escapes_and_includes_keywords(email_env):
    email_env(APP_BASE_URL="https://app.example/")
    subject, html, text = email_channel.format_alert(NEWS, ["docenti", "ata"])
    assert subject == "[School Feed Monitor] Concorso <docenti> & ATA"
    assert "Concorso &lt;docenti&gt; &amp; ATA" in html and "USR &lt;ER&gt;" in html
    assert 'href="https://x/1?a=1&amp;b=2"' in html and "Testo breve" in html
    assert "<b>docenti, ata</b>" in html
    assert 'href="https://app.example/preferenze"' in html
    assert "Parole chiave: docenti, ata" in text and "https://x/1?a=1&b=2" in text and "<p>" not in text
    assert "https://app.example/preferenze" in text


def test_format_digest_with_and_without_news(email_env):
    email_env()  # nessun APP_BASE_URL → nessun link preferenze
    subject, html, text = email_channel.format_digest([NEWS, {**NEWS, "link": "https://x/2", "title": "Altra"}])
    assert "2 notizie" in subject and "2 notizie" in html and "Altra" in html and "Altra" in text
    assert "preferenze" not in html

    subject, html, text = email_channel.format_digest([])
    assert "nessuna notizia" in subject and "Nessuna notizia" in html and "Nessuna notizia" in text


def test_email_channel_sends_via_mailer(monkeypatch):
    sent = []
    monkeypatch.setattr(email_channel, "send_email", lambda to, subject, html, text=None: sent.append((to, subject)) or True)
    user = {"id": 1, "email": "prof@scuola.it"}
    email_channel.send_alert(user, NEWS, ["docenti"])
    email_channel.send_digest(user, [])
    assert [s[0] for s in sent] == ["prof@scuola.it"] * 2
    assert sent[0][1].startswith("[School Feed Monitor] Concorso") and "Report" in sent[1][1]


# --- notifier: scelta dei canali --------------------------------------------------

@pytest.mark.parametrize("user, expected", [
    ({"telegram_id": 5}, ["telegram"]),                                         # utente storico senza flag
    ({"telegram_id": 5, "notify_telegram": False}, []),
    ({"email": "a@b.it"}, []),                                                  # email ma notify_email off
    ({"email": "a@b.it", "notify_email": True}, ["email"]),
    ({"telegram_id": 5, "notify_telegram": True, "email": "a@b.it", "notify_email": True}, ["telegram", "email"]),
    ({"telegram_id": None, "email": None, "notify_email": True}, []),
])
def test_channels_for_respects_preferences(user, expected):
    assert notifier.channels_for(user) == expected


def test_notifier_dispatches_to_both_channels(sent_messages, monkeypatch):
    emails = []
    monkeypatch.setattr(email_channel, "send_email", lambda to, subject, html, text=None: emails.append(to) or True)
    user = {"id": 1, "telegram_id": 7, "notify_telegram": True, "email": "a@b.it", "notify_email": True}
    assert notifier.send_alert(user, NEWS, ["docenti"]) == ["telegram", "email"]
    assert [m["chat_id"] for m in sent_messages] == [7] and emails == ["a@b.it"]


def test_email_failure_does_not_block_telegram(sent_messages, monkeypatch):
    def boom(*a, **k):
        raise mailer.EmailError("smtp down")
    monkeypatch.setattr(email_channel, "send_email", boom)
    user = {"id": 1, "telegram_id": 7, "email": "a@b.it", "notify_email": True}
    assert notifier.send_digest(user, []) == ["telegram"]
    assert [m["chat_id"] for m in sent_messages] == [7]
