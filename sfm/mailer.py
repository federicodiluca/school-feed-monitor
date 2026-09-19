"""Invio email con backend intercambiabile, scelto da EMAIL_BACKEND:

    smtp    -> server SMTP standard (es. Brevo, Mailjet): SMTP_HOST, SMTP_PORT,
               SMTP_USER, SMTP_PASSWORD, SMTP_TLS (starttls, default) | ssl | none
    resend  -> API HTTP di Resend: RESEND_API_KEY
    none    -> disabilitato: le email vengono solo loggate (default se non configurato)

Comuni: EMAIL_FROM (es. "School Feed Monitor <noreply@tuodominio.it>"), EMAIL_REPLY_TO (opz.).
Le credenziali stanno solo nell'ambiente / .env, mai nel repo.
"""
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import requests

from sfm.env import env
from sfm.logger import log

RESEND_API_URL = "https://api.resend.com/emails"
SMTP_TIMEOUT = 20
REQUEST_TIMEOUT = 20


class EmailError(Exception):
    """Invio fallito (configurazione mancante, rifiuto del server, rete)."""


def _config():
    return {
        "backend": (env("EMAIL_BACKEND") or "none").strip().lower(),
        "from": env("EMAIL_FROM") or "",
        "reply_to": env("EMAIL_REPLY_TO") or "",
    }


def is_enabled():
    cfg = _config()
    return cfg["backend"] in ("smtp", "resend") and bool(cfg["from"])


def send_email(to, subject, html, text=None):
    """Invia una email. Ritorna True se accettata dal backend, solleva EmailError altrimenti."""
    cfg = _config()
    if not to:
        raise EmailError("destinatario mancante")
    if cfg["backend"] == "smtp":
        return _send_smtp(cfg, to, subject, html, text)
    if cfg["backend"] == "resend":
        return _send_resend(cfg, to, subject, html, text)
    if cfg["backend"] == "none":
        log(f"✉️ [email disabilitata] a {to}: {subject}")
        return False
    raise EmailError(f"EMAIL_BACKEND non valido: {cfg['backend']}")


# --- SMTP -----------------------------------------------------------------

def build_message(sender, to, subject, html, text=None, reply_to=None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text or "")
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _send_smtp(cfg, to, subject, html, text):
    host = env("SMTP_HOST")
    if not host or not cfg["from"]:
        raise EmailError("SMTP non configurato: servono SMTP_HOST ed EMAIL_FROM")
    port = int(env("SMTP_PORT") or 587)
    user, password = env("SMTP_USER"), env("SMTP_PASSWORD")
    tls = (env("SMTP_TLS") or "starttls").strip().lower()

    msg = build_message(cfg["from"], to, subject, html, text, cfg["reply_to"])
    try:
        if tls == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT)
        else:
            server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
        with server:
            server.ehlo()
            if tls == "starttls":
                server.starttls()
                server.ehlo()
            if user:
                server.login(user, password or "")
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"SMTP {host}:{port}: {e}") from e
    return True


# --- Resend ---------------------------------------------------------------

def _send_resend(cfg, to, subject, html, text):
    api_key = env("RESEND_API_KEY")
    if not api_key or not cfg["from"]:
        raise EmailError("Resend non configurato: servono RESEND_API_KEY ed EMAIL_FROM")
    payload = {"from": cfg["from"], "to": [to], "subject": subject, "html": html}
    if text:
        payload["text"] = text
    if cfg["reply_to"]:
        payload["reply_to"] = cfg["reply_to"]
    try:
        resp = requests.post(RESEND_API_URL, json=payload, timeout=REQUEST_TIMEOUT,
                             headers={"Authorization": f"Bearer {api_key}"})
    except requests.RequestException as e:
        raise EmailError(f"Resend: {e}") from e
    if not resp.ok:
        raise EmailError(f"Resend HTTP {resp.status_code}: {resp.text[:200]}")
    return True
