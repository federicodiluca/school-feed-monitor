"""Pagine notizie: /notizie (pubblica, con filtri e pagine per fonte) e
/le-mie-notizie (recap personale, per giorno, con le parole chiave evidenziate)."""
import re
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, redirect, render_template, request, url_for

from sfm.catalog import REGIONS, group_sources, province_codes, provinces_of
from sfm.db_news import count_per_source, get_today_news, latest_per_source, search_news
from sfm.db_sources import get_source, get_sources
from sfm.digest import annotate
from sfm.matching import is_excluded
from sfm.utils import slugify, strip_html
from sfm.watchdog import source_states, thresholds
from web import prefs

bp = Blueprint("news", __name__)

PER_PAGE = 20
DAYS_CHOICES = (1, 3, 7, 30)
DEFAULT_DAYS = 7
MAX_QUERY_LEN = 80


def _filters(default_days=DEFAULT_DAYS):
    """Filtri comuni da query string: q, giorni, pagina. Valori fuori range → default."""
    q = (request.args.get("q") or "").strip()[:MAX_QUERY_LEN]
    try:
        days = int(request.args.get("giorni") or default_days)
    except ValueError:
        days = default_days
    if days not in DAYS_CHOICES:
        days = default_days
    try:
        page = max(1, int(request.args.get("pagina") or 1))
    except ValueError:
        page = 1
    return q, days, page


def _pages(total, page):
    last = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return {"current": min(page, last), "last": last, "total": total}


def _clamp_page(total, page):
    """Se la pagina richiesta è oltre l'ultima, redirect all'ultima (niente pagine vuote)."""
    last = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    if page > last:
        args = request.args.to_dict()
        args["pagina"] = last
        return redirect(url_for(request.endpoint, **request.view_args, **args))
    return None


SOURCE_DAYS = 30


def _join_places(names):
    """["Alessandria", "Asti"] → "Alessandria e Asti"; tre o più: "A, B e C"."""
    return " e ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


def office_info(source):
    """Come la gente chiama un ufficio quando lo cerca: nome per esteso, province e sigle.
    Chi cerca «usp al», «ust mn» o «provveditorato asti» deve ritrovare queste parole nella pagina."""
    kind, name = source.get("kind"), source.get("name") or ""
    if kind == "usr":
        full = f"Ufficio Scolastico Regionale {source.get('region') or ''}".strip()
        return {"kind": "usr", "full": full, "places": source.get("region") or "", "codes": [], "codes_label": "",
                "aliases": [full]}
    if kind != "usp":
        return None
    places, codes = _join_places(provinces_of(source)), province_codes(source)
    full = "Ufficio Scolastico Territoriale" if name.upper().startswith("UST") else "Ufficio Scolastico Provinciale"
    aliases = []
    if places:
        aliases += [f"{full} di {places}", f"Ambito Territoriale di {places}", f"ex Provveditorato agli Studi di {places}"]
    aliases += [f"{name.split()[0]} {c}" for c in codes]      # «USP AL», «UST MN»
    return {"kind": "usp", "full": full, "places": places, "codes": codes, "aliases": aliases,
            "codes_label": f" ({', '.join(codes)})" if codes else ""}


def source_url(source):
    return url_for("news.by_source", source_id=source["id"], slug=slugify(source["name"]))


REGION_NEWS = 40      # notizie mostrate nella pagina di una regione
REGION_DAYS = 30


def region_url(region):
    return url_for("news.by_region", slug=slugify(region))


def region_sources(region, sources=None):
    """USR e USP della regione, USR prima (stesso ordine di /fonti)."""
    items = [s for s in (sources if sources is not None else get_sources())
             if s.get("region") == region and s.get("kind") in ("usr", "usp")]
    return dict(group_sources(items)).get(region, [])


SOURCE_GROUPS = (("mim", "Ministero"), ("usr", "Uffici scolastici regionali"),
                 ("usp", "Uffici scolastici provinciali"), ("other", "Altre fonti"))


def source_options(sources):
    """Le fonti del menù «Fonte», per tipo e in ordine alfabetico del luogo: «USP Bari» e
    «UST Bergamo» vanno sotto B, senza che la sigla le separi."""
    def key(s):
        return slugify(re.sub(r"^(USP|UST|USR|MIM)\s+", "", s["name"]))
    known = {k for k, _ in SOURCE_GROUPS}
    groups = []
    for kind, label in SOURCE_GROUPS:
        items = [s for s in sources if (s.get("kind") if s.get("kind") in known else "other") == kind]
        if items:
            groups.append((label, sorted(items, key=key)))
    return groups


def regions_with_sources(sources=None):
    """Le regioni che hanno almeno una fonte: solo loro hanno una pagina."""
    sources = sources if sources is not None else get_sources()
    return [r for r in REGIONS if region_sources(r, sources)]


@bp.get("/notizie")
def index():
    q, days, page = _filters()
    sources = get_sources()
    try:
        source_id = int(request.args.get("fonte") or 0) or None
    except ValueError:
        source_id = None
    if source_id and not any(s["id"] == source_id for s in sources):
        source_id = None
    rows, total = search_news(source_ids={source_id} if source_id else None, query=q, days=days, page=page, per_page=PER_PAGE)
    if (r := _clamp_page(total, page)):
        return r
    return render_template("notizie.html", news=rows, sources=sources, source_groups=source_options(sources), q=q, days=days, days_choices=DAYS_CHOICES,
                           selected_source=source_id, pages=_pages(total, page), source=None,
                           noindex=bool(q or source_id))


@bp.get("/fonti")
def sources():
    """Elenco completo delle fonti, per regione. È la pagina che rende raggiungibili — a un
    lettore come a un motore di ricerca — le oltre cento pagine per fonte."""
    items = get_sources()
    last, counts = latest_per_source(), count_per_source()
    states = source_states(sources=items)
    items = [dict(s, last_news=last.get(s["id"]), n_news=counts.get(s["id"], 0), health=states[s["id"]])
             for s in items]
    by_state = {}
    for s in items:
        by_state.setdefault(s["health"]["state"], []).append(s)
    return render_template("fonti.html", groups=group_sources(items), total=len(items), by_state=by_state,
                           regions=regions_with_sources(items),
                           silence_days=thresholds()["silence_hours"] // 24, failures=thresholds()["failures"])


@bp.get("/notizie/fonte/<int:source_id>")
@bp.get("/notizie/fonte/<int:source_id>/<slug>")
def by_source(source_id, slug=None):
    source = get_source(source_id)
    if not source or not source["enabled"]:
        abort(404)
    expected = slugify(source["name"])
    if slug != expected:
        return redirect(url_for("news.by_source", source_id=source_id, slug=expected, **request.args), 301)
    # un ufficio che pubblica poco, a 7 giorni, lascia la pagina quasi vuota: qui si parte da 30
    q, days, page = _filters(default_days=SOURCE_DAYS)
    rows, total = search_news(source_ids={source_id}, query=q, days=days, page=page, per_page=PER_PAGE)
    if (r := _clamp_page(total, page)):
        return r
    latest = search_news(source_ids={source_id}, page=1, per_page=1)[0]
    return render_template("notizie.html", news=rows, sources=get_sources(), q=q, days=days, days_choices=DAYS_CHOICES,
                           selected_source=source_id, pages=_pages(total, page), source=source, noindex=bool(q),
                           office=office_info(source), latest=latest[0] if latest else None)


@bp.get("/notizie/regione/<slug>")
def by_region(slug):
    """Tutte le notizie di una regione (USR + uffici provinciali) in una pagina: è quella che
    risponde a ricerche come «ufficio scolastico Sicilia notizie»."""
    sources = get_sources()
    region = next((r for r in regions_with_sources(sources) if slugify(r) == slug), None)
    if region is None:
        abort(404)
    items = region_sources(region, sources)
    last, counts = latest_per_source(), count_per_source()
    items = [dict(s, last_news=last.get(s["id"]), n_news=counts.get(s["id"], 0)) for s in items]
    rows, total = search_news(source_ids={s["id"] for s in items}, days=REGION_DAYS, page=1, per_page=REGION_NEWS)
    provinces = sorted({p for s in items if s["kind"] == "usp" for p in (s.get("province") or "").split("|") if p})
    return render_template("regione.html", region=region, region_sources=items, news=rows, total=total,
                           provinces=provinces, days=REGION_DAYS)


# --- interpelli ------------------------------------------------------------------

INTERPELLI_DAYS = 14       # scadono in pochi giorni, e ne escono una ventina al giorno
INTERPELLI_MAX = 300
# Classi di concorso: A053, B015, AK56, AM56, le ADSS/ADMM/ADEE/ADAA del sostegno; «A-22» → A022
_CLASS_RE = re.compile(r"\b(AD(?:AA|EE|MM|SS)|[AB][A-Z]\d{2}|[AB]-?\d{2,3})\b")


def interpello_tags(news):
    """Le classi di concorso (e «DSGA») citate in titolo o testo, senza doppioni."""
    text = f"{news.get('title') or ''} {strip_html(news.get('content') or '')}"
    text = re.sub(r"\S*(?:://|www\.)\S*", " ", text).upper()     # niente codici presi dentro un link
    tags = []
    for code in _CLASS_RE.findall(text):
        if code[1].isdigit() or code[1] == "-":
            code = code[0] + code.lstrip("AB-").zfill(3)
        if code not in tags:
            tags.append(code)
    if "DSGA" in text:
        tags.append("DSGA")
    return tags


@bp.get("/interpelli")
def interpelli():
    """Gli interpelli di tutti gli uffici in una pagina. Escono provincia per provincia, ma chi
    li cerca («interpello AM56», «interpello dsga sicilia») li vuole vedere tutti insieme:
    è l'unica ricerca a cui il sito risponde meglio dei siti ufficiali."""
    sources = {s["id"]: s for s in get_sources()}
    rows, total, page = [], 0, 1
    while len(rows) < INTERPELLI_MAX:             # search_news dà al massimo 100 righe a pagina
        batch, total = search_news(query="interpell", days=INTERPELLI_DAYS, page=page, per_page=100)
        rows += batch
        if len(batch) < 100:
            break
        page += 1
    rows = rows[:INTERPELLI_MAX]
    groups = {}
    for n in rows:
        n["tags"] = interpello_tags(n)
        src = sources.get(n.get("source_id")) or {}
        groups.setdefault(src.get("region") or "Nazionali", []).append(n)
    order = {r: i for i, r in enumerate(["Nazionali"] + REGIONS)}
    groups = sorted(groups.items(), key=lambda g: order.get(g[0], len(order)))
    classes = {}
    for n in rows:
        for t in n["tags"]:
            classes[t] = classes.get(t, 0) + 1
    return render_template("interpelli.html", groups=groups, total=total, shown=len(rows), days=INTERPELLI_DAYS,
                           classes=sorted(classes.items()))


# --- le mie notizie (preferenze nel browser, nessun account) ------------------

def _parse_day(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@bp.get("/le-mie-notizie")
def mine():
    """Notizie dalle fonti scelte in questo browser, con le parole chiave evidenziate."""
    followed = prefs.selected_source_ids()
    user = {"id": None, "keywords": prefs.selected_keywords(), "excluded": prefs.selected_excluded()}
    q, days, page = _filters()
    view = request.args.get("vista") or "oggi"
    if not followed:
        return render_template("le_mie_notizie.html", view=view, news=[], user=user, day=date.today(),
                               prev_day=None, next_day=None, q="", days=None, days_choices=DAYS_CHOICES,
                               pages=None, n_sources=0)

    if view == "tutte":
        rows, total = search_news(source_ids=followed, query=q, days=days, page=page, per_page=PER_PAGE)
        if (r := _clamp_page(total, page)):
            return r
        rows = annotate([r for r in rows if not is_excluded(r, user)], user)
        rows.sort(key=lambda n: (n.get("published_at") or ""), reverse=True)
        return render_template("le_mie_notizie.html", user=user, view="tutte", news=rows, q=q, days=days,
                               days_choices=DAYS_CHOICES, pages=_pages(total, page), day=None, n_sources=len(followed))

    day = _parse_day(request.args.get("giorno")) or date.today()
    if day > date.today():
        day = date.today()
    at = datetime.combine(day, datetime.min.time()).astimezone() + timedelta(hours=12)
    rows = annotate([r for r in get_today_news(now=at, source_ids=followed) if not is_excluded(r, user)], user)
    return render_template("le_mie_notizie.html", user=user, view="oggi", news=rows, day=day,
                           prev_day=day - timedelta(days=1), next_day=(day + timedelta(days=1)) if day < date.today() else None,
                           q="", days=None, days_choices=DAYS_CHOICES, pages=None, n_sources=len(followed))
