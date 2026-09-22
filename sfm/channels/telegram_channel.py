"""Canale Telegram: formatta e invia alert e report tramite sfm.telegram."""
from datetime import datetime

from sfm.env import site_url
from sfm.telegram import send_long_message, send_message
from sfm.utils import cleanHTMLPreview, escape_html, format_local_datetime

NAME = "telegram"


def no_news_message():
    return ("🗓️ Nessuna notizia per oggi dalle fonti che segui.\n"
            f"Tutte le notizie, anche delle altre fonti: {site_url()}/notizie")


def format_alert(news):
    """Messaggio HTML per una notizia che ha fatto match."""
    preview = cleanHTMLPreview(news.get("content") or "")
    return (
        f"🚨 <a href=\"{escape_html(news.get('link'))}\">{escape_html(news.get('source'))}</a>\n"
        f"<b>{escape_html(news.get('title'))}</b>\n<i>{preview}</i>"
    )


def build_report(news_list):
    """Testo HTML del report giornaliero. Ritorna None se non ci sono notizie."""
    if not news_list:
        return None

    matched = sum(1 for n in news_list if n.get("matched_keywords"))
    head = f"📢 <b>Report del {datetime.now():%d/%m/%Y}</b> — {len(news_list)} notizie trovate"
    if matched:
        head += f" (🔔 {matched} con le tue parole chiave)"
    lines = [head + "\n"]
    for n in news_list:
        title = escape_html((n.get("title") or "Titolo non disponibile").strip())
        source = escape_html(n.get("source") or "Sorgente sconosciuta")
        link = escape_html(n.get("link") or "")
        preview = cleanHTMLPreview(n.get("content") or "")
        published = format_local_datetime(n.get("published_at"))
        kws = n.get("matched_keywords") or []
        icon = "🔔" if kws else "🗞️"
        hint = f" · <b>{escape_html(', '.join(kws))}</b>" if kws else ""
        if n.get("already_alerted"):
            hint += " · <i>già segnalata</i>"
        lines.append(f"{icon} <a href=\"{link}\">{source}</a> — {published}{hint}\n<b>{title}</b>\n<i>{preview}</i>\n")

    lines.append(f"🌐 Cerca fra tutte le notizie, anche delle fonti che non segui: {site_url()}/notizie")
    return "\n".join(lines).strip()


def send_alert(user, news, matched_keywords):
    return send_message(format_alert(news), parse_mode="HTML", chat_id=user["telegram_id"])


def send_digest(user, news_list):
    text = build_report(news_list) or no_news_message()
    return send_long_message(text, chat_id=user["telegram_id"], parse_mode="HTML")
