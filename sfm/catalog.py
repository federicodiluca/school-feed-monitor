"""Catalogo delle fonti italiane (USR regionali, USP provinciali, MIM).

I dati stanno in bot/catalog/<nome>.json: una lista di voci
    {"name", "url", "type": "rss"|"html", "kind": "usr"|"usp"|"mim"|"other",
     "region": ..., "province": ..., "default_follow": bool (opzionale)}
Il catalogo viene unito alle fonti di config.json quando quest'ultimo contiene
"catalog": "italy" (le voci di config vincono sulle omonime del catalogo).
"""
import json
import os

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "catalog")

REGIONS = [
    "Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia-Romagna", "Friuli-Venezia Giulia", "Lazio", "Liguria",
    "Lombardia", "Marche", "Molise", "Piemonte", "Puglia", "Sardegna", "Sicilia", "Toscana",
    "Trentino-Alto Adige", "Umbria", "Valle d'Aosta", "Veneto",
]


PROVINCE_SEP = "|"   # un ufficio può coprire più province: "Alessandria|Asti"


def _province(value):
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        return PROVINCE_SEP.join(v.strip() for v in value if v and v.strip()) or None
    return str(value).strip() or None


def provinces_of(source):
    """Lista delle province coperte da una fonte (vuota se non è un USP)."""
    return [p for p in (source.get("province") or "").split(PROVINCE_SEP) if p]


def load_catalog(name="italy"):
    """Lista delle voci del catalogo (già normalizzate come le 'sites' di config)."""
    path = os.path.join(CATALOG_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"catalogo fonti non trovato: {path}")
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    out = []
    for e in entries:
        out.append({
            "name": e["name"].strip(),
            "url": e["url"].strip(),
            "type": (e.get("type") or "rss").lower(),
            "kind": (e.get("kind") or "other").lower(),
            "region": e.get("region") or None,
            "province": _province(e.get("province")),
            # USR/USP sono opt-in (l'utente sceglie regione/provincia); MIM e nazionali seguiti da tutti
            "default_follow": bool(e.get("default_follow", e.get("kind") in ("mim", "other"))),
        })
    return out


def merge_sites(config_sites, catalog_entries):
    """Unisce config e catalogo per URL: le voci di config hanno la precedenza e vengono prima."""
    config_urls = {s["url"] for s in config_sites}
    return list(config_sites) + [e for e in catalog_entries if e["url"] not in config_urls]


# --- raggruppamento e scelta per area ---------------------------------------

NATIONAL_GROUP = "Nazionali"
OTHER_GROUP = "Altre fonti"


def group_sources(sources):
    """Raggruppa le fonti per area: 'Nazionali' (MIM), poi le regioni in ordine alfabetico
    (USR prima degli USP, USP per nome), infine 'Altre fonti' (custom, senza regione).
    Ritorna una lista di (gruppo, [fonti])."""
    groups = {}
    for s in sources:
        if s.get("kind") == "mim":
            key = NATIONAL_GROUP
        elif s.get("kind") in ("usr", "usp") and s.get("region"):
            key = s["region"]
        else:
            key = OTHER_GROUP
        groups.setdefault(key, []).append(s)
    order = [NATIONAL_GROUP] + sorted(k for k in groups if k not in (NATIONAL_GROUP, OTHER_GROUP)) + [OTHER_GROUP]
    out = []
    for key in order:
        if key not in groups:
            continue
        items = sorted(groups[key], key=lambda s: (0 if s.get("kind") in ("mim", "usr") else 1, s["name"].lower()))
        out.append((key, items))
    return out


def provinces_by_region(sources):
    """{regione: [province...]} dalle fonti USP disponibili (per il form 'Dove insegni?')."""
    out = {}
    for s in sources:
        if s.get("kind") == "usp" and s.get("region"):
            for p in provinces_of(s):
                out.setdefault(s["region"], set()).add(p)
    return {r: sorted(ps) for r, ps in sorted(out.items())}


def sources_for_areas(sources, areas):
    """Fonti da seguire per una o più aree. areas = {regione: [province...]} (lista vuota =
    tutta la regione). Sempre incluse le nazionali (MIM 'default'); per ogni regione l'USR
    e gli USP che coprono almeno una delle province indicate."""
    areas = {r: {p for p in (ps or []) if p} for r, ps in areas.items()}
    chosen = []
    for s in sources:
        kind, region = s.get("kind"), s.get("region")
        if kind == "mim" and s.get("default_follow", True):
            chosen.append(s)
        elif kind == "usr" and region in areas:
            chosen.append(s)
        elif kind == "usp" and region in areas:
            wanted = areas[region]
            if not wanted or wanted & set(provinces_of(s)):
                chosen.append(s)
    return chosen


def sources_for_area(sources, region, provinces=()):
    """Scorciatoia per una sola area."""
    return sources_for_areas(sources, {region: list(provinces)})
