"""Pagine notizie: /notizie (pubblica, con filtri e pagine per fonte) e
/le-mie-notizie (recap personale, per giorno, con le parole chiave evidenziate)."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, redirect, render_template, request, url_for

from sfm.db_news import search_news
from sfm.db_sources import get_followed_source_ids, get_source, get_sources
from sfm.digest import annotate, build_user_digest
from sfm.utils import slugify
from web import security

bp = Blueprint("news", __name__)

PER_PAGE = 20
DAYS_CHOICES = (1, 3, 7, 30)
DEFAULT_DAYS = 7
MAX_QUERY_LEN = 80


def _filters():
    """Filtri comuni da query string: q, giorni, pagina. Valori fuori range → default."""
    q = (request.args.get("q") or "").strip()[:MAX_QUERY_LEN]
    try:
        days = int(request.args.get("giorni") or DEFAULT_DAYS)
    except ValueError:
        days = DEFAULT_DAYS
    if days not in DAYS_CHOICES:
        days = DEFAULT_DAYS
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


def source_url(source):
    return url_for("news.by_source", source_id=source["id"], slug=slugify(source["name"]))


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
    return render_template("notizie.html", news=rows, sources=sources, q=q, days=days, days_choices=DAYS_CHOICES,
                           selected_source=source_id, pages=_pages(total, page), source=None,
                           noindex=bool(q or source_id))


@bp.get("/notizie/fonte/<int:source_id>")
@bp.get("/notizie/fonte/<int:source_id>/<slug>")
def by_source(source_id, slug=None):
    source = get_source(source_id)
    if not source or not source["enabled"]:
        abort(404)
    expected = slugify(source["name"])
    if slug != expected:
        return redirect(url_for("news.by_source", source_id=source_id, slug=expected, **request.args), 301)
    q, days, page = _filters()
    rows, total = search_news(source_ids={source_id}, query=q, days=days, page=page, per_page=PER_PAGE)
    if (r := _clamp_page(total, page)):
        return r
    return render_template("notizie.html", news=rows, sources=get_sources(), q=q, days=days, days_choices=DAYS_CHOICES,
                           selected_source=source_id, pages=_pages(total, page), source=source, noindex=bool(q))


# --- area personale ---------------------------------------------------------

def _parse_day(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@bp.get("/le-mie-notizie")
@security.login_required
def mine():
    user = security.current_user()
    followed = get_followed_source_ids(user["id"])
    q, days, page = _filters()
    view = request.args.get("vista") or "oggi"

    if view == "tutte":
        rows, total = search_news(source_ids=followed, query=q, days=days, page=page, per_page=PER_PAGE)
        if (r := _clamp_page(total, page)):
            return r
        rows = annotate(rows, user)
        rows.sort(key=lambda n: (n.get("published_at") or ""), reverse=True)  # cronologico, evidenza sul singolo
        return render_template("le_mie_notizie.html", user=user, view="tutte", news=rows, q=q, days=days,
                               days_choices=DAYS_CHOICES, pages=_pages(total, page), day=None, n_sources=len(followed))

    day = _parse_day(request.args.get("giorno")) or date.today()
    if day > date.today():
        day = date.today()
    at = datetime.combine(day, datetime.min.time()).astimezone() + timedelta(hours=12)
    rows = build_user_digest(user, now=at)
    return render_template("le_mie_notizie.html", user=user, view="oggi", news=rows, day=day,
                           prev_day=day - timedelta(days=1), next_day=(day + timedelta(days=1)) if day < date.today() else None,
                           q="", days=None, days_choices=DAYS_CHOICES, pages=None, n_sources=len(followed))
