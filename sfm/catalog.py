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


# Le 107 province italiane per regione. È l'elenco che l'utente vede quando sceglie "dove":
# deve essere quello reale, non quello delle fonti che abbiamo. Per le province senza un
# ufficio provinciale con sito proprio si ricade sulle notizie regionali dell'USR.
PROVINCES = {
    "Abruzzo": ["Chieti", "L'Aquila", "Pescara", "Teramo"],
    "Basilicata": ["Matera", "Potenza"],
    "Calabria": ["Catanzaro", "Cosenza", "Crotone", "Reggio Calabria", "Vibo Valentia"],
    "Campania": ["Avellino", "Benevento", "Caserta", "Napoli", "Salerno"],
    "Emilia-Romagna": ["Bologna", "Ferrara", "Forlì-Cesena", "Modena", "Parma", "Piacenza",
                       "Ravenna", "Reggio Emilia", "Rimini"],
    "Friuli-Venezia Giulia": ["Gorizia", "Pordenone", "Trieste", "Udine"],
    "Lazio": ["Frosinone", "Latina", "Rieti", "Roma", "Viterbo"],
    "Liguria": ["Genova", "Imperia", "La Spezia", "Savona"],
    "Lombardia": ["Bergamo", "Brescia", "Como", "Cremona", "Lecco", "Lodi", "Mantova", "Milano",
                  "Monza e Brianza", "Pavia", "Sondrio", "Varese"],
    "Marche": ["Ancona", "Ascoli Piceno", "Fermo", "Macerata", "Pesaro e Urbino"],
    "Molise": ["Campobasso", "Isernia"],
    "Piemonte": ["Alessandria", "Asti", "Biella", "Cuneo", "Novara", "Torino",
                 "Verbano-Cusio-Ossola", "Vercelli"],
    "Puglia": ["Bari", "Barletta-Andria-Trani", "Brindisi", "Foggia", "Lecce", "Taranto"],
    "Sardegna": ["Cagliari", "Nuoro", "Oristano", "Sassari", "Sud Sardegna"],
    "Sicilia": ["Agrigento", "Caltanissetta", "Catania", "Enna", "Messina", "Palermo", "Ragusa",
                "Siracusa", "Trapani"],
    "Toscana": ["Arezzo", "Firenze", "Grosseto", "Livorno", "Lucca", "Massa-Carrara", "Pisa",
                "Pistoia", "Prato", "Siena"],
    "Trentino-Alto Adige": ["Bolzano", "Trento"],
    "Umbria": ["Perugia", "Terni"],
    "Valle d'Aosta": ["Aosta"],
    "Veneto": ["Belluno", "Padova", "Rovigo", "Treviso", "Venezia", "Verona", "Vicenza"],
}


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


def _norm_url(url):
    """URL confrontabile: senza schema, senza www., senza barra finale."""
    u = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def _norm_name(name):
    """Nome confrontabile: solo lettere e cifre minuscole ('USR Emilia Romagna' == 'USR Emilia-Romagna')."""
    return "".join(c for c in (name or "").lower() if c.isalnum())


def merge_sites(config_sites, catalog_entries):
    """Unisce le fonti di config.json con il catalogo.

    Una voce di config che corrisponde a una del catalogo — stesso URL o stesso nome — è la
    *stessa fonte*: tiene il suo URL (le notizie già salvate restano collegate) ma eredita dal
    catalogo tipo, regione, provincia e il fatto di essere opt-in. Senza questo, gli USP
    elencati in config.json finivano tra le "Altre fonti", fuori dalla loro regione, e per
    giunta seguiti da tutti per impostazione predefinita.
    Le voci di config che non corrispondono a niente restano come sono, in testa all'elenco.
    """
    by_url = {_norm_url(e["url"]): e for e in catalog_entries}
    by_name = {_norm_name(e["name"]): e for e in catalog_entries}
    merged, used = [], set()
    for site in config_sites:
        twin = by_url.get(_norm_url(site.get("url"))) or by_name.get(_norm_name(site.get("name")))
        if twin is None:
            merged.append(site)
            continue
        used.add(twin["url"])
        entry = dict(site)
        for field in ("kind", "region", "province", "default_follow"):
            if site.get(field) in (None, ""):          # quello che config dice esplicitamente vince
                entry[field] = twin.get(field)
        entry.setdefault("name", twin["name"])
        merged.append(entry)
    return merged + [e for e in catalog_entries if e["url"] not in used]


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


def provinces_by_region(sources=None):
    """{regione: [province...]}: tutte le province italiane, non solo quelle con un ufficio
    provinciale nel catalogo. `sources` è accettato per compatibilità e non viene usato."""
    return {region: list(provinces) for region, provinces in sorted(PROVINCES.items())}


def provinces_with_own_office(sources):
    """{regione: {province con una fonte USP dedicata}}: il resto è coperto solo dall'USR."""
    out = {}
    for s in sources:
        if s.get("kind") == "usp" and s.get("region"):
            out.setdefault(s["region"], set()).update(provinces_of(s))
    return out


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
