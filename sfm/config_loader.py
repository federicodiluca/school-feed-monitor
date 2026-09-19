import json
import os

from sfm.settings import CONFIG_FILE  # SFM_CONFIG (o CHECKFEED_CONFIG, deprecata)

REQUIRED_KEYS = ("telegram_token",)
SITE_TYPES = ("rss", "html")  # rss = feed RSS/Atom; html = pagina "lista notizie" da scrapare
SITE_KINDS = ("usr", "usp", "mim", "other")

DEFAULTS = {
    "machine_name": "School Feed Monitor",
    "daily_report_time": "18:00",
    "polling_minutes": 10,
    "data_retention_days": 7,
    "disable_web_page_preview": True,
    "sites": [],
}

_cache = None


def load_config(path=None):
    """Legge e valida il file di configurazione, applicando i default."""
    path = path or CONFIG_FILE
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"❌ Configurazione mancante: {path}.\n"
            f"Copia 'config.example.json' in '{path}' e personalizzalo."
        )
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        raise ValueError(f"❌ Configurazione incompleta: campi mancanti {', '.join(missing)}")
    cfg.setdefault("sites", [])
    if not isinstance(cfg["sites"], list):
        raise ValueError("❌ Configurazione non valida: 'sites' deve essere una lista")
    for site in cfg["sites"]:
        if not isinstance(site, dict) or not site.get("url"):
            raise ValueError(f"❌ Configurazione non valida: feed senza 'url' ({site!r})")
        site.setdefault("name", site["url"])
        site["type"] = str(site.get("type") or "rss").lower()
        if site["type"] not in SITE_TYPES:
            raise ValueError(f"❌ Configurazione non valida: type '{site['type']}' per {site['url']} (ammessi: {', '.join(SITE_TYPES)})")
        site["default_follow"] = bool(site.get("default_follow", True))
        site["kind"] = str(site.get("kind") or "other").lower()
        if site["kind"] not in SITE_KINDS:
            raise ValueError(f"❌ Configurazione non valida: kind '{site['kind']}' per {site['url']} (ammessi: {', '.join(SITE_KINDS)})")
        site["region"] = (site.get("region") or "").strip() or None
        site["province"] = (site.get("province") or "").strip() or None

    for key, value in DEFAULTS.items():
        cfg.setdefault(key, value)

    # Catalogo fonti italiane (USR/USP/MIM): "catalog": "italy" | false
    catalog = cfg.get("catalog", "italy")
    if catalog:
        from sfm.catalog import load_catalog, merge_sites
        cfg["sites"] = merge_sites(cfg["sites"], load_catalog(str(catalog)))
    return cfg


def get_config():
    """Restituisce la configurazione (letta una sola volta e messa in cache)."""
    global _cache
    if _cache is None:
        _cache = load_config()
    return _cache
