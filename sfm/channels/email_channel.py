"""Canale email: costruisce alert e report (HTML + testo) e li invia con sfm.mailer."""
from datetime import datetime

from sfm.env import env
from sfm.mailer import send_email
from sfm.utils import cleanHTMLPreview, escape_html, format_local_datetime, strip_html

NAME = "email"
APP_NAME = "School Feed Monitor"
PREVIEW_LEN = 300

_STYLE = (
    "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
    "font-size:15px;line-height:1.5;color:#222;max-width:640px;margin:0 auto;padding:16px"
)


def _preferences_url():
    base = (env("APP_BASE_URL") or "").rstrip("/")
    return f"{base}/preferenze" if base else ""


def _footer_html():
    url = _preferences_url()
    manage = f' · <a href="{escape_html(url)}">Gestisci preferenze o disiscriviti</a>' if url else ""
    return (f'<p style="font-size:12px;color:#777;margin-top:24px">'
            f"Ricevi questa email perché sei iscritto a {APP_NAME}{manage}.</p>")


def _footer_text():
    url = _preferences_url()
    manage = f"\nGestisci preferenze o disiscriviti: {url}" if url else ""
    return f"\n--\nRicevi questa email perché sei iscritto a {APP_NAME}.{manage}\n"


def _item_html(n):
    title = escape_html((n.get("title") or "Titolo non disponibile").strip())
    source = escape_html(n.get("source") or "Fonte sconosciuta")
    link = escape_html(n.get("link") or "")
    preview = cleanHTMLPreview(n.get("content") or "", max_len=PREVIEW_LEN)
    published = format_local_datetime(n.get("published_at"))
    when = f" — {published}" if published else ""
    kws = n.get("matched_keywords") or []
    hint = f' · <b style="color:#b45309">🔔 {escape_html(", ".join(kws))}</b>' if kws else ""
    box = "border-left:3px solid #f59e0b;padding-left:10px;" if kws else ""
    return (f'<p style="margin:0 0 16px;{box}"><span style="color:#777;font-size:13px">{source}{when}{hint}</span><br>'
            f'<a href="{link}" style="font-weight:600;color:#1a56db">{title}</a><br>'
            f'<span style="color:#444">{preview}</span></p>')


def _item_text(n):
    title = (n.get("title") or "Titolo non disponibile").strip()
    source = n.get("source") or "Fonte sconosciuta"
    published = format_local_datetime(n.get("published_at"))
    when = f" — {published}" if published else ""
    kws = n.get("matched_keywords") or []
    hint = f" · parole chiave: {', '.join(kws)}" if kws else ""
    preview = strip_html(n.get("content") or "")[:PREVIEW_LEN]
    return f"[{source}{when}{hint}]\n{title}\n{n.get('link') or ''}\n{preview}\n"


# --- alert ----------------------------------------------------------------

def format_alert(news, matched_keywords):
    """Ritorna (subject, html, text) per una notizia che ha fatto match."""
    title = (news.get("title") or "").strip()
    kws = ", ".join(matched_keywords or [])
    subject = f"[{APP_NAME}] {title}"[:200]
    html = (f'<div style="{_STYLE}"><p style="margin:0 0 8px;font-size:13px;color:#777">'
            f"🔔 Parole chiave: <b>{escape_html(kws)}</b></p>{_item_html(news)}{_footer_html()}</div>")
    text = f"Parole chiave: {kws}\n\n{_item_text(news)}{_footer_text()}"
    return subject, html, text


# --- digest ---------------------------------------------------------------

def format_digest(news_list, when=None):
    """Ritorna (subject, html, text) del report giornaliero (anche vuoto)."""
    when = when or datetime.now()
    day = f"{when:%d/%m/%Y}"
    count = len(news_list)
    if count:
        subject = f"[{APP_NAME}] Report del {day}: {count} notizie"
        body_html = "".join(_item_html(n) for n in news_list)
        body_text = "\n".join(_item_text(n) for n in news_list)
        matched = sum(1 for n in news_list if n.get("matched_keywords"))
        intro = f"{count} notizie dalle fonti che segui"
        if matched:
            intro += f", {matched} con le tue parole chiave"
    else:
        subject = f"[{APP_NAME}] Report del {day}: nessuna notizia"
        body_html = '<p style="color:#777">Nessuna notizia per oggi dalle fonti che segui.</p>'
        body_text = "Nessuna notizia per oggi dalle fonti che segui.\n"
        intro = "nessuna notizia dalle fonti che segui"
    html = (f'<div style="{_STYLE}"><h2 style="margin:0 0 16px">📢 Report del {day}</h2>'
            f'<p style="color:#777;margin:0 0 16px">{intro}.</p>{body_html}{_footer_html()}</div>')
    text = f"Report del {day} — {intro}.\n\n{body_text}{_footer_text()}"
    return subject, html, text


# --- verifica indirizzo ---------------------------------------------------

def format_verification(link):
    """Email di conferma dell'indirizzo (double opt-in). Ritorna (subject, html, text)."""
    subject = f"[{APP_NAME}] Conferma il tuo indirizzo email"
    html = (f'<div style="{_STYLE}"><h2 style="margin:0 0 16px">Conferma il tuo indirizzo</h2>'
            f"<p>Per ricevere le notifiche di {APP_NAME} conferma che questo indirizzo è tuo:</p>"
            f'<p><a href="{escape_html(link)}" style="display:inline-block;padding:10px 16px;background:#1e3a8a;color:#fff;'
            f'text-decoration:none;border-radius:6px">Conferma indirizzo</a></p>'
            f'<p style="color:#777;font-size:13px">Il link vale 48 ore. Se non ti sei registrato tu, ignora questa email: '
            f"non riceverai nulla.</p></div>")
    text = (f"Per ricevere le notifiche di {APP_NAME} conferma il tuo indirizzo aprendo questo link (valido 48 ore):\n"
            f"{link}\n\nSe non ti sei registrato tu, ignora questa email.\n")
    return subject, html, text


# --- interfaccia canale ---------------------------------------------------

def send_alert(user, news, matched_keywords):
    subject, html, text = format_alert(news, matched_keywords)
    return send_email(user["email"], subject, html, text)


def send_digest(user, news_list):
    subject, html, text = format_digest(news_list)
    return send_email(user["email"], subject, html, text)
