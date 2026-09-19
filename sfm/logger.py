import os
from datetime import timedelta, datetime

from sfm.settings import LOG_DIR  # SFM_LOG_DIR (o CHECKFEED_LOG_DIR, deprecata)  # noqa: E402


def log(message: str):
    """Scrive un messaggio su console e sul file di log giornaliero."""
    now = datetime.now()
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"{now.date()}.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {message}\n")
    try:
        print(message)
    except UnicodeEncodeError:
        # console senza supporto UTF-8 (es. Windows cp1252): non perdiamo il log
        print(message.encode("ascii", "replace").decode("ascii"))


def cleanup_logs(retention_days: int):
    """Elimina i file di log (YYYY-MM-DD.log) più vecchi di retention_days.
    Ritorna il numero di file rimossi."""
    if not os.path.isdir(LOG_DIR):
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for file in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, file)
        if not (os.path.isfile(path) and file.endswith(".log")):
            continue
        try:
            file_date = datetime.strptime(file[:-len(".log")], "%Y-%m-%d")
        except ValueError:
            continue  # file non nel formato atteso: lo ignoriamo
        if file_date < cutoff:
            os.remove(path)
            removed += 1
            log(f"🗑️ Rimosso log vecchio: {file}")
    return removed
