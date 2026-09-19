"""Watchdog: controlla fonti e job e avvisa l'amministratore quando qualcosa si rompe.

Avvisa UNA volta all'apertura di un problema e una volta quando rientra
(gli incidenti aperti stanno in watchdog_incidents). Configurazione via ambiente:

    ADMIN_TELEGRAM_ID               chat Telegram dell'admin (opzionale)
    ADMIN_EMAIL                     email dell'admin (opzionale; richiede EMAIL_BACKEND)
    WATCHDOG_SOURCE_FAILURES        fallimenti consecutivi prima dell'avviso (default 3)
    WATCHDOG_SOURCE_SILENCE_HOURS   ore senza notizie nuove prima dell'avviso (default 72)
    WATCHDOG_JOB_STALE_MINUTES      minuti senza esecuzione di fetch_news prima dell'avviso
                                    (default: 3 x polling_minutes)
    HEALTHCHECK_PING_URL            URL da "pingare" a ogni fetch riuscito (es. healthchecks.io):
                                    un monitor esterno si accorge anche se il processo muore

Il ping esterno esiste perché un watchdog interno non può segnalare la morte
del proprio processo.
"""
import traceback
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from sfm import mailer
from sfm.config_loader import get_config
from sfm.db_health import (
    close_incident,
    get_job_runs,
    get_open_incidents,
    get_source_health,
    open_incident,
    record_job_end,
    record_job_start,
)
from sfm.db_news import get_recent_news, search_news
from sfm.db_sources import get_sources
from sfm.db_user import get_users
from sfm.env import env
from sfm.logger import log
from sfm import telegram
from sfm.utils import escape_html

JOB_FETCH = "fetch_news"
JOB_DIGEST = "run_digests"
PING_TIMEOUT = 10


def _int_env(key, default):
    try:
        return int(env(key) or default)
    except ValueError:
        return default


def thresholds():
    polling = int(get_config().get("polling_minutes", 10))
    return {
        "failures": _int_env("WATCHDOG_SOURCE_FAILURES", 3),
        "silence_hours": _int_env("WATCHDOG_SOURCE_SILENCE_HOURS", 72),
        "job_stale_minutes": _int_env("WATCHDOG_JOB_STALE_MINUTES", polling * 3),
    }


# --- heartbeat dei job ----------------------------------------------------

def tracked(name, fn):
    """Avvolge un job schedulato: registra inizio/fine in job_runs e cattura le eccezioni
    (un job che fallisce non deve fermare lo scheduler)."""
    def run(*args, **kwargs):
        record_job_start(name)
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            log(f"❌ Errore nel job {name}: {e}\n{traceback.format_exc()}")
            record_job_end(name, ok=False, error=e)
            return None
        record_job_end(name, ok=True)
        if name == JOB_FETCH:
            ping_healthcheck()
        return result
    run.__name__ = f"tracked_{name}"
    return run


def ping_healthcheck():
    url = env("HEALTHCHECK_PING_URL")
    if not url:
        return False
    try:
        requests.get(url, timeout=PING_TIMEOUT)
        return True
    except requests.RequestException as e:
        log(f"⚠️ Ping healthcheck fallito: {e}")
        return False


# --- controlli ------------------------------------------------------------

_SECOND_LEVEL = {"gov", "edu", "com", "org", "net", "co"}
DRIFT_SAMPLE = 10


def site_of(url):
    """Dominio 'registrabile' di una URL: bo.istruzioneer.gov.it -> istruzioneer.gov.it,
    www.usr.sicilia.it -> sicilia.it, uspmc.sinp.net -> sinp.net."""
    host = (urlparse(url).hostname or "").lower()
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def source_drift(source, news=None):
    """True se la maggioranza delle ultime notizie della fonte punta a un altro dominio:
    tipico di un dominio scaduto/venduto o di un feed che ha cambiato natura."""
    news = news if news is not None else get_recent_news(limit=DRIFT_SAMPLE, source_ids={source["id"]})
    if len(news) < 3:
        return False
    expected = site_of(source["url"])
    foreign = sum(1 for n in news if site_of(n.get("link") or "") != expected)
    return foreign * 2 > len(news)

def _parse_utc(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _hours_ago(value, now):
    dt = _parse_utc(value)
    return None if dt is None else (now - dt).total_seconds() / 3600


def find_problems(now=None):
    """Ritorna {key: messaggio} dei problemi attuali."""
    now = now or datetime.now(timezone.utc)
    th = thresholds()
    problems = {}

    health = {h["source_id"]: h for h in get_source_health()}
    for source in get_sources():
        name = source["name"]
        if source_drift(source):
            problems[f"source:{source['id']}:drift"] = (
                f"la fonte «{name}» pubblica notizie che puntano a un altro sito "
                f"(atteso {site_of(source['url'])}): dominio scaduto o feed cambiato?"
            )
        h = health.get(source["id"])
        if not h:
            continue
        if h["consecutive_failures"] >= th["failures"]:
            problems[f"source:{source['id']}:failing"] = (
                f"la fonte «{name}» fallisce da {h['consecutive_failures']} letture consecutive: {h.get('last_error') or '?'}"
            )
            continue  # se fallisce, la silenziosità è una conseguenza
        since = _hours_ago(h.get("last_new_item_at") or h.get("first_seen_at"), now)
        if since is not None and since >= th["silence_hours"]:
            problems[f"source:{source['id']}:silent"] = (
                f"la fonte «{name}» non produce notizie nuove da {int(since)} ore "
                f"(letture ok, {h.get('last_items') or 0} elementi): forse è cambiata la struttura della pagina"
            )

    runs = get_job_runs()
    fetch = runs.get(JOB_FETCH)
    if fetch:
        last = _parse_utc(fetch.get("finished_at")) or _parse_utc(fetch.get("started_at"))
        if last and now - last > timedelta(minutes=th["job_stale_minutes"]):
            problems[f"job:{JOB_FETCH}:stale"] = (
                f"il job {JOB_FETCH} non termina da {int((now - last).total_seconds() // 60)} minuti "
                f"(soglia {th['job_stale_minutes']})"
            )
        elif fetch.get("ok") == 0:
            problems[f"job:{JOB_FETCH}:error"] = f"l'ultima esecuzione di {JOB_FETCH} è fallita: {fetch.get('error') or '?'}"
    digest = runs.get(JOB_DIGEST)
    if digest and digest.get("ok") == 0:
        problems[f"job:{JOB_DIGEST}:error"] = f"l'ultima esecuzione di {JOB_DIGEST} è fallita: {digest.get('error') or '?'}"

    return problems


# --- avvisi ---------------------------------------------------------------

def admin_targets():
    tg = env("ADMIN_TELEGRAM_ID")
    return {"telegram_id": int(tg) if tg and tg.strip().lstrip("-").isdigit() else None,
            "email": (env("ADMIN_EMAIL") or "").strip() or None}


def notify_admin(subject, lines):
    """Invia un avviso all'admin su Telegram e/o email. Ritorna i canali usati."""
    targets = admin_targets()
    used = []
    text = "\n".join(lines)
    if targets["telegram_id"]:
        body = f"<b>{escape_html(subject)}</b>\n" + "\n".join(f"• {escape_html(l)}" for l in lines)
        res = telegram.send_message(body, parse_mode="HTML", chat_id=targets["telegram_id"])
        if res and res.get("ok"):
            used.append("telegram")
    if targets["email"] and mailer.is_enabled():
        try:
            html = f"<p><b>{escape_html(subject)}</b></p><ul>" + "".join(f"<li>{escape_html(l)}</li>" for l in lines) + "</ul>"
            if mailer.send_email(targets["email"], f"[School Feed Monitor] {subject}", html, f"{subject}\n\n{text}"):
                used.append("email")
        except mailer.EmailError as e:
            log(f"❌ Avviso admin via email fallito: {e}")
    if not used:
        log(f"🐶 Watchdog (nessun admin configurato): {subject}\n{text}")
    return used


def weekly_summary(now=None):
    """Riepilogo settimanale all'admin: stato fonti, notizie raccolte, utenti."""
    now = now or datetime.now(timezone.utc)
    sources = get_sources()
    health = {h["source_id"]: h for h in get_source_health()}
    th = thresholds()
    failing = [s["name"] for s in sources if health.get(s["id"], {}).get("consecutive_failures", 0) >= th["failures"]]
    silent = [s["name"] for s in sources
              if s["id"] in health and health[s["id"]].get("consecutive_failures", 0) < th["failures"]
              and (_hours_ago(health[s["id"]].get("last_new_item_at") or health[s["id"]].get("first_seen_at"), now) or 0) >= th["silence_hours"]]
    never = [s["name"] for s in sources if s["id"] not in health]
    _, n_news = search_news(days=7, page=1, per_page=1)
    users = get_users(active_only=False)
    active = sum(1 for u in users if u["active"])
    lines = [
        f"Fonti attive: {len(sources)} — in errore: {len(failing)}, silenziose da {th['silence_hours']}h: {len(silent)}, mai lette: {len(never)}",
        f"Notizie raccolte negli ultimi 7 giorni: {n_news}",
        f"Utenti: {len(users)} ({active} attivi; {sum(1 for u in users if u.get('email'))} con email, {sum(1 for u in users if u.get('telegram_id'))} con Telegram)",
    ]
    if failing:
        lines.append("In errore: " + ", ".join(failing[:15]) + (" …" if len(failing) > 15 else ""))
    if silent:
        lines.append("Silenziose: " + ", ".join(silent[:15]) + (" …" if len(silent) > 15 else ""))
    notify_admin("📊 Riepilogo settimanale", lines)
    return lines


def run_watchdog(now=None):
    """Job periodico: confronta i problemi attuali con gli incidenti aperti;
    avvisa per i nuovi e per quelli rientrati. Ritorna (nuovi, rientrati)."""
    now = now or datetime.now(timezone.utc)
    problems = find_problems(now)
    open_ = get_open_incidents()

    new_keys = [k for k in problems if k not in open_]
    resolved = [k for k in open_ if k not in problems]

    for k in new_keys:
        open_incident(k, problems[k], now)
    for k in resolved:
        close_incident(k)

    if new_keys:
        log(f"🐶 Watchdog: {len(new_keys)} nuovi problemi.")
        notify_admin(f"🚨 Watchdog: {len(new_keys)} problem{'a' if len(new_keys) == 1 else 'i'}",
                     [problems[k] for k in new_keys])
    if resolved:
        log(f"🐶 Watchdog: {len(resolved)} problemi rientrati.")
        notify_admin("✅ Watchdog: rientrato", [f"risolto: {open_[k]['message']}" for k in resolved])
    return len(new_keys), len(resolved)
