"""Quanto sono fresche le notizie mostrate: ultimo aggiornamento e prossimo previsto.

Sul sito statico l'ultimo aggiornamento è il momento in cui la pagina viene generata
(scripts/publish_site.sh, dal cron sulla VM), e il prossimo arriva dopo SITE_PUBLISH_MINUTES
(default 60, come il cron in docs/deploy.md). Servito da Flask, le pagine sono sempre
fresche: conta l'ultima lettura delle fonti, e la prossima arriva dopo polling_minutes.
In entrambi i casi si dice anche quando il bot ha letto le fonti l'ultima volta."""
from datetime import datetime, timedelta, timezone

from flask import current_app

from sfm.config_loader import get_config
from sfm.db_health import get_job_runs, utcnow_str
from sfm.env import env
from sfm.utils import format_local_datetime
from sfm.watchdog import JOB_FETCH

DEFAULT_PUBLISH_MINUTES = 60


def _parse(utc_str):
    try:
        return datetime.strptime(utc_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _every(minutes):
    if minutes == 60:
        return "ogni ora"
    if minutes % 60 == 0:
        return f"ogni {minutes // 60} ore"
    return f"ogni {minutes} minuti"


def _stamp(dt):
    s = dt.strftime("%Y-%m-%d %H:%M:%S")
    return {"iso": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "date": format_local_datetime(s, "%d/%m/%Y"),
            "time": format_local_datetime(s, "%H:%M")}


def freshness(now=None):
    """Dati per _freshness.html, o None se il bot non ha mai letto le fonti (sito di prova vuoto)."""
    polling = int(get_config().get("polling_minutes", 60))
    fetched = _parse((get_job_runs().get(JOB_FETCH) or {}).get("finished_at"))
    if current_app.config.get("STATIC"):
        updated = _parse(utcnow_str(now))
        every = int(env("SITE_PUBLISH_MINUTES") or DEFAULT_PUBLISH_MINUTES)
    else:
        if fetched is None:
            return None
        updated, every = fetched, polling
    return {
        "updated": _stamp(updated),
        "next": _stamp(updated + timedelta(minutes=every)),
        "fetched": _stamp(fetched) if fetched and fetched != updated else None,
        "every": _every(every),
        "polling": _every(polling),
        # oltre questo ritardo la pagina avvisa che l'aggiornamento non è arrivato (app.js)
        "late_after_minutes": every + 30,
    }
