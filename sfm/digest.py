"""Digest giornaliero: per ogni utente, le notizie del giorno dalle fonti che segue,
con evidenziate quelle che contengono le sue parole chiave. Inviato su tutti i
canali dell'utente all'orario scelto (digest_time) o a quello globale.

Guard anti-doppio-invio: users.last_digest_date = giorno locale dell'ultimo invio.
Se il bot era fermo all'orario previsto, il digest parte al primo giro utile.
"""
from datetime import datetime

from sfm import notifier
from sfm.config_loader import get_config
from sfm.db_deliveries import delivered_news_ids, record_delivery
from sfm.db_news import get_today_news
from sfm.db_sources import get_followed_source_ids
from sfm.db_user import get_users, set_last_digest_date
from sfm.logger import log
from sfm.matching import is_excluded, news_text
from sfm.utils import find_matching_keywords


def annotate(news_list, user, alerted_ids=None):
    """Aggiunge a ogni news 'matched_keywords' e 'already_alerted'; le notizie con
    match vengono messe per prime (a parità, ordine originale = più recenti prima)."""
    alerted_ids = alerted_ids or set()
    out = []
    for n in news_list:
        n = dict(n)
        n["matched_keywords"] = find_matching_keywords(news_text(n), user.get("keywords") or [])
        n["already_alerted"] = n.get("id") in alerted_ids
        out.append(n)
    out.sort(key=lambda n: 0 if n["matched_keywords"] else 1)
    return out


def build_user_digest(user, now=None):
    """Lista annotata delle notizie di oggi per l'utente (fonti seguite, senza le escluse)."""
    news = get_today_news(now=now, source_ids=get_followed_source_ids(user.get("id")))
    news = [n for n in news if not is_excluded(n, user)]
    alerted = delivered_news_ids(user["id"], kind="alert", news_ids=[n["id"] for n in news]) if user.get("id") else set()
    return annotate(news, user, alerted)


def send_user_digest(user, now=None, mark=True):
    """Invia il digest a un utente su tutti i suoi canali. Ritorna (n_notizie, canali_riusciti)."""
    items = build_user_digest(user, now=now)
    channels = notifier.send_digest(user, items)
    if user.get("id"):
        for ch in channels:
            for n in items:
                record_delivery(user["id"], n["id"], ch, "digest")
        if mark and channels:
            set_last_digest_date(user["id"], _day(now))
    return len(items), channels


# --- scheduling -----------------------------------------------------------

def _day(now=None):
    return f"{(now or datetime.now()):%Y-%m-%d}"


def _parse_hhmm(value):
    try:
        h, m = value.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except (AttributeError, ValueError):
        pass
    return None


def default_digest_time():
    return get_config().get("daily_report_time", "18:00")


def is_due(user, now=None):
    """True se all'utente spetta il digest di oggi: orario raggiunto e non ancora inviato oggi."""
    now = now or datetime.now()
    if user.get("last_digest_date") == _day(now):
        return False
    minutes = _parse_hhmm(user.get("digest_time") or "") or _parse_hhmm(default_digest_time()) or 18 * 60
    return now.hour * 60 + now.minute >= minutes


def run_digests(now=None, force=False):
    """Job periodico (ogni minuto): invia il digest agli utenti attivi a cui è dovuto.
    force=True → a tutti gli attivi, ignorando orario e guard. Ritorna il numero di digest inviati."""
    now = now or datetime.now()
    sent = 0
    for user in get_users():
        if not force and not is_due(user, now):
            continue
        if not notifier.channels_for(user):
            set_last_digest_date(user["id"], _day(now))  # nessun canale: niente da inviare oggi
            continue
        try:
            count, channels = send_user_digest(user, now=now)
            if channels:
                sent += 1
                log(f"📄 Digest a {notifier.user_label(user)}: {count} notizie via {', '.join(channels)}.")
            elif notifier.channels_for(user):
                log(f"⚠️ Digest non consegnato a {notifier.user_label(user)} (tutti i canali in errore).")
        except Exception as e:
            log(f"⚠️ Errore digest per {notifier.user_label(user)}: {e}")
    if sent:
        log(f"📄 Digest inviati: {sent}.")
    return sent
