"""Caricamento delle variabili d'ambiente da un file .env (opzionale).

Non sovrascrive variabili già presenti nell'ambiente. Il file .env è in
.gitignore: contiene credenziali (SMTP, API key) e non va mai committato.
"""
import os

from sfm.settings import ENV_FILE  # SFM_ENV_FILE (o CHECKFEED_ENV_FILE, deprecata)  # noqa: E402
_loaded = False


def load_env(path=None, override=False):
    """Legge `path` (default .env) riga per riga: KEY=value, commenti con #,
    valori opzionalmente tra virgolette. Ritorna il numero di variabili impostate."""
    path = path or ENV_FILE
    if not os.path.isfile(path):
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].rstrip()  # commento in coda: KEY=valore  # nota
            if key and (override or key not in os.environ):
                os.environ[key] = value
                count += 1
    return count


DEFAULT_SITE_URL = "https://federicodiluca.github.io/school-feed-monitor"


def site_url():
    """Indirizzo pubblico del sito, da APP_BASE_URL (senza barra finale)."""
    return (env("APP_BASE_URL") or DEFAULT_SITE_URL).rstrip("/")


def env(key, default=None):
    """Variabile d'ambiente, caricando .env la prima volta."""
    global _loaded
    if not _loaded:
        load_env()
        _loaded = True
    return os.environ.get(key, default)


def env_bool(key, default=False):
    value = env(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")
