"""Percorsi e variabili d'ambiente del progetto (School Feed Monitor).

Le variabili nuove sono SFM_*; le vecchie CHECKFEED_* vengono ancora lette (con un
avviso) per non rompere i deploy esistenti. Questo modulo non deve importare nulla
del progetto: viene letto a import-time da config, DB, logger e .env.
"""
import os
import sys

_LEGACY_PREFIX = "CHECKFEED_"
_PREFIX = "SFM_"


def env_setting(name, default=None):
    """Legge SFM_<name>, altrimenti CHECKFEED_<name> (deprecata), altrimenti default."""
    value = os.environ.get(_PREFIX + name)
    if value is not None:
        return value
    legacy = os.environ.get(_LEGACY_PREFIX + name)
    if legacy is not None:
        print(f"⚠️ {_LEGACY_PREFIX}{name} è deprecata: usa {_PREFIX}{name}", file=sys.stderr)
        return legacy
    return default


CONFIG_FILE = env_setting("CONFIG", "config.json")
ENV_FILE = env_setting("ENV_FILE", ".env")
LOG_DIR = env_setting("LOG_DIR", "data/logs")

DEFAULT_DB_PATH = "data/sfm.db"
LEGACY_DB_PATH = "data/checkfeed.db"
DB_PATH = env_setting("DB_PATH", DEFAULT_DB_PATH)


def other_db_files():
    """Altri file .db nella cartella del database in uso. Se ce ne sono, quasi sempre
    significa che il servizio sta scrivendo su un database nuovo mentre quello vero è lì
    accanto: meglio dirlo forte all'avvio che scoprirlo dagli utenti spariti."""
    folder = os.path.dirname(DB_PATH) or "."
    if not os.path.isdir(folder):
        return []
    in_use = os.path.basename(DB_PATH)
    return sorted(name for name in os.listdir(folder)
                  if name.endswith(".db") and name != in_use)


def warn_about_other_db_files():
    others = other_db_files()
    if others:
        print(f"⚠️ Sto usando {DB_PATH}, ma nella stessa cartella ci sono anche: "
              f"{', '.join(others)}. Se gli utenti sembrano spariti, il database buono è uno di quelli.",
              file=sys.stderr)
    return others


def migrate_legacy_db_file():
    """Se il DB è ancora al vecchio percorso predefinito e quello nuovo non esiste,
    lo sposta (con i file -wal/-shm). Ritorna True se ha spostato qualcosa."""
    if DB_PATH != DEFAULT_DB_PATH or os.path.exists(DEFAULT_DB_PATH) or not os.path.exists(LEGACY_DB_PATH):
        return False
    os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(LEGACY_DB_PATH + suffix):
            os.replace(LEGACY_DB_PATH + suffix, DEFAULT_DB_PATH + suffix)
    print(f"ℹ️ Database spostato da {LEGACY_DB_PATH} a {DEFAULT_DB_PATH}", file=sys.stderr)
    return True
