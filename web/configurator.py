"""Configuratore: scegli area, fonti e parole chiave; salva nel tuo browser e, se vuoi,
porta la stessa configurazione sul bot Telegram con un codice usa-e-getta."""
import json

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from sfm.catalog import REGIONS, group_sources, load_catalog, provinces_by_region, sources_for_areas
from sfm.db_configs import TTL_HOURS, save_config
from sfm.db_sources import get_sources
from sfm.utils import parse_keywords
from web import prefs

bp = Blueprint("config", __name__)


def catalog_positions():
    """{url della fonte: posizione nel catalogo}. La posizione è quella che finisce nel link
    di Telegram quando il sito è statico (vedi sfm/config_link.py)."""
    return {entry["url"]: i for i, entry in enumerate(load_catalog())}


def _sources_with_selection():
    chosen = prefs.selected_source_ids()
    positions = catalog_positions()
    return [dict(s, followed=s["id"] in chosen, catalog_index=positions.get(s["url"]))
            for s in get_sources()]


@bp.get("/configura")
def show():
    sources = _sources_with_selection()
    return render_template("configura.html", sources=sources, groups=group_sources(sources),
                           keywords=prefs.selected_keywords(), regions=REGIONS,
                           provinces_by_region=provinces_by_region(sources),
                           code=request.args.get("codice"), ttl_hours=TTL_HOURS)


@bp.post("/configura")
def save():
    """Salva la scelta nel browser. Con 'telegram' genera anche il codice per il bot."""
    valid = {s["id"] for s in get_sources()}
    source_ids = [int(v) for v in request.form.getlist("sources") if v.isdigit() and int(v) in valid]
    keywords = prefs.clean_keywords(parse_keywords(request.form.get("keywords", "")))

    if request.form.get("azione") == "telegram":
        if not source_ids:
            flash("Scegli almeno una fonte prima di portare la configurazione su Telegram.", "error")
            return prefs.store(redirect(url_for("config.show")), source_ids, keywords)
        code = save_config(source_ids, keywords)
        response = redirect(url_for("config.show", codice=code) + "#telegram")
    else:
        flash(f"Fatto: {len(source_ids)} fonti e {len(keywords)} parole chiave, salvate in questo browser.", "success")
        response = redirect(url_for("news.mine"))
    return prefs.store(response, source_ids, keywords)


@bp.post("/configura/area")
def area():
    """Scorciatoia: seleziona MIM + USR + USP di una o più aree e torna al configuratore."""
    regions = [r for r in request.form.getlist("regions") if r in REGIONS]
    if not regions:
        flash("Scegli almeno una regione.", "error")
        return redirect(url_for("config.show"))
    areas = {r: [] for r in regions}
    for value in request.form.getlist("provinces"):
        region, _, province = value.partition("|")
        if region in areas and province:
            areas[region].append(province)
    chosen = [s["id"] for s in sources_for_areas(get_sources(), areas)]
    where = "; ".join(r + (f" ({', '.join(ps)})" if ps else "") for r, ps in areas.items())
    flash(f"Selezionate {len(chosen)} fonti per: {where}. Aggiungi le parole chiave e salva.", "success")
    return prefs.store(redirect(url_for("config.show") + "#fonti"), chosen, prefs.selected_keywords())


@bp.post("/configura/dimentica")
def forget():
    flash("Preferenze cancellate da questo browser.", "info")
    return prefs.forget(redirect(url_for("config.show")))


@bp.get("/configura/esporta.json")
def export():
    """Le preferenze salvate nel browser, in chiaro: sono tue, puoi portartele via."""
    sources = {s["id"]: s["name"] for s in get_sources()}
    chosen = prefs.selected_source_ids()
    data = {"fonti": [{"id": i, "nome": sources.get(i)} for i in sorted(chosen)],
            "parole_chiave": prefs.selected_keywords()}
    resp = current_app.response_class(response=json.dumps(data, ensure_ascii=False, indent=1),
                                      mimetype="application/json")
    resp.headers["Content-Disposition"] = "attachment; filename=school-feed-monitor-preferenze.json"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def telegram_link(code):
    """Deep link che apre il bot e applica la configurazione (t.me/BOT?start=CODICE)."""
    bot = (current_app.config.get("TELEGRAM_BOT_USERNAME") or "").lstrip("@")
    return f"https://t.me/{bot}?start={code}" if bot and code else ""
