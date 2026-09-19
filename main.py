from sfm.config_loader import get_config
from sfm.db import init_db
from sfm.db_news import cleanup_old_news
from sfm.db_sources import get_source, sync_config_sources
from sfm.news_fetcher import fetch_news, fetch_source
from sfm.digest import run_digests
from sfm.watchdog import JOB_DIGEST, JOB_FETCH, run_watchdog, tracked, weekly_summary
from sfm.logger import log, cleanup_logs
from sfm.telegram_commands import start_telegram_listener, build_help_message
from sfm.telegram import send_message
from sfm.utils import escape_html
import schedule
import time
import traceback

# === Configurazione iniziale ===
init_db()
CONFIG = get_config()
MACHINE_NAME = CONFIG["machine_name"]
DAILY_REPORT_TIME = CONFIG["daily_report_time"]
CLEANUP_DAYS = CONFIG["data_retention_days"]
POLLING_MINUTES = CONFIG["polling_minutes"]

n_sources, new_source_ids = sync_config_sources(CONFIG["sites"])
log(f"🔄 Servizio avviato su {MACHINE_NAME} ({n_sources} fonti da config).")

# Fonti appena aggiunte in config: prima lettura senza notifiche, per non
# inviare una raffica di alert sulle notizie già pubblicate.
for sid in new_source_ids:
    source = get_source(sid)
    try:
        seeded = fetch_source(source, notify=False)
        log(f"🌱 Fonte nuova '{source['name']}': salvate {seeded} notizie senza notifica.")
    except Exception as e:
        log(f"❌ Errore nella lettura iniziale di '{source['name']}': {e}")

# === Scheduler ===
schedule.every(POLLING_MINUTES).minutes.do(tracked(JOB_FETCH, fetch_news))
schedule.every(1).minutes.do(tracked(JOB_DIGEST, run_digests))  # digest all'orario di ogni utente (default DAILY_REPORT_TIME)
schedule.every(30).minutes.do(tracked("watchdog", run_watchdog))  # avvisa l'admin se fonti o job si rompono
schedule.every().monday.at("08:00").do(tracked("weekly_summary", weekly_summary))
schedule.every().day.at("20:00").do(lambda: cleanup_logs(CLEANUP_DAYS))
schedule.every().day.at("20:30").do(lambda: cleanup_old_news(CLEANUP_DAYS))  # N.B. si fa riferimento alla data di fetch

# === Listener Telegram ===
start_telegram_listener()

# Recap di avvio agli utenti attivi (comandi + feed monitorati)
send_message(f"🔄 Servizio avviato su <b>{escape_html(MACHINE_NAME)}</b>.\n\n{build_help_message()}", parse_mode="HTML")

# Primo fetch subito all'avvio, senza attendere il primo intervallo
# (tracked cattura e logga eventuali errori)
tracked(JOB_FETCH, fetch_news)()

while True:
    try:
        schedule.run_pending()
        time.sleep(60)  # Controlla ogni minuto
    except Exception as e:
        err = traceback.format_exc()
        log(f"❌ Errore nel loop principale: {e}\n{err}")
        send_message(f"❌ Errore nel loop principale:\n<pre>{escape_html(e)}</pre>", parse_mode="HTML")
        time.sleep(10)
