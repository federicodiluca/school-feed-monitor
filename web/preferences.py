"""Pagina preferenze: fonti, parole chiave, canali, frequenza, orario del digest,
aggiunta di fonti e collegamento con Telegram."""
import re
import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from sfm.catalog import REGIONS, group_sources, provinces_by_region
from sfm.db_sources import add_user_source, follow_area, get_source_by_url, get_sources, get_user_sources, set_user_source, user_area
from sfm.db_user import ALERT_MODES, create_link_code, set_keywords, set_preferences, unlink_telegram
from sfm.digest import default_digest_time
from sfm.logger import log
from sfm.news_fetcher import fetch_source
from sfm.source_parser import SourceError, detect_source
from sfm.utils import parse_keywords
from web import security

bp = Blueprint("prefs", __name__)

MAX_KEYWORDS = 50
MAX_KEYWORD_LEN = 60
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
LINK_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza 0/O e 1/I


@bp.get("/preferenze")
@security.login_required
def show():
    user = security.current_user()
    sources = get_user_sources(user["id"])
    region, provinces = user_area(user["id"])
    return render_template("preferenze.html", user=user, sources=sources, groups=group_sources(sources),
                           area_region=region, area_provinces=provinces,
                           default_time=default_digest_time(), link_code=request.args.get("codice"))


@bp.post("/preferenze")
@security.login_required
def save():
    user = security.current_user()
    form = request.form

    keywords = parse_keywords(form.get("keywords", ""))
    too_long = [k for k in keywords if len(k) > MAX_KEYWORD_LEN]
    if too_long or len(keywords) > MAX_KEYWORDS:
        flash(f"Massimo {MAX_KEYWORDS} parole chiave, ognuna al massimo di {MAX_KEYWORD_LEN} caratteri.", "error")
        return redirect(url_for("prefs.show"))

    alert_mode = form.get("alert_mode") or "digest"
    if alert_mode not in ALERT_MODES:
        alert_mode = "digest"
    digest_time = (form.get("digest_time") or "").strip()
    if digest_time and not TIME_RE.match(digest_time):
        flash("Orario del riepilogo non valido (usa il formato HH:MM).", "error")
        return redirect(url_for("prefs.show"))

    notify_email = form.get("notify_email") == "on" and bool(user["email"])
    notify_telegram = form.get("notify_telegram") == "on" and bool(user["telegram_id"])
    if not notify_email and not notify_telegram:
        flash("Attenzione: nessun canale attivo, non riceverai notifiche.", "info")

    followed = {int(v) for v in form.getlist("sources") if v.isdigit()}
    for s in get_user_sources(user["id"]):
        set_user_source(user["id"], s["id"], s["id"] in followed)

    set_keywords(user["id"], keywords)
    set_preferences(user["id"], notify_email=notify_email, notify_telegram=notify_telegram,
                    alert_mode=alert_mode, digest_time=digest_time)
    flash("Preferenze salvate.", "success")
    return redirect(url_for("prefs.show"))


@bp.post("/preferenze/fonti")
@security.login_required
def add_source():
    """Aggiunge una fonte (RSS o pagina HTML) verificandola, come /addsource nel bot."""
    user = security.current_user()
    url = (request.form.get("url") or "").strip()
    name = (request.form.get("name") or "").strip()[:100]
    if not url or "." not in url:
        flash("Inserisci l'indirizzo di un feed RSS o di una pagina di notizie.", "error")
        return redirect(url_for("prefs.show"))

    existing = get_source_by_url(url)
    if existing and existing["enabled"]:
        set_user_source(user["id"], existing["id"], True)
        flash(f"Fonte già presente: ora la segui ({existing['name']}).", "info")
        return redirect(url_for("prefs.show"))

    try:
        detected = detect_source(url)
    except SourceError as e:
        flash(f"Non riesco a leggere notizie da questo indirizzo: {e}", "error")
        return redirect(url_for("prefs.show"))
    except Exception as e:  # rete, parser...
        log(f"❌ Errore aggiunta fonte dal web ({url}): {e}")
        flash("Errore inatteso durante il controllo della fonte. Riprova più tardi.", "error")
        return redirect(url_for("prefs.show"))

    source, created = add_user_source(name or detected["name"] or url, detected["url"], detected["type"], user["id"])
    fetch_source(source, notify=False)  # prima lettura senza notifiche
    flash(f"Fonte {'aggiunta' if created else 'riattivata'}: {source['name']} ({len(detected['items'])} notizie trovate).", "success")
    return redirect(url_for("prefs.show"))


# --- area: regione e province ("Dove insegni?") ------------------------------

@bp.get("/preferenze/area")
@security.login_required
def area():
    user = security.current_user()
    region, provinces = user_area(user["id"])
    return render_template("area.html", user=user, regions=REGIONS, provinces_by_region=provinces_by_region(get_sources()),
                           region=region, provinces=provinces, welcome=request.args.get("benvenuto") == "1")


@bp.post("/preferenze/area")
@security.login_required
def save_area():
    user = security.current_user()
    region = (request.form.get("region") or "").strip()
    if region not in REGIONS:
        flash("Scegli la tua regione.", "error")
        return redirect(url_for("prefs.area"))
    provinces = [p for p in request.form.getlist("provinces") if p]
    count = follow_area(user["id"], region, provinces)
    where = region + (f" ({', '.join(provinces)})" if provinces else "")
    flash(f"Area impostata: {where}. Ora segui {count} fonti; puoi rifinire la scelta qui sotto.", "success")
    return redirect(url_for("prefs.show") + "#fonti")


# --- Telegram ---------------------------------------------------------------

@bp.post("/preferenze/telegram/codice")
@security.login_required
def telegram_code():
    user = security.current_user()
    code = "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(8))
    create_link_code(user["id"], code)
    return redirect(url_for("prefs.show", codice=code) + "#telegram")


@bp.post("/preferenze/telegram/scollega")
@security.login_required
def telegram_unlink():
    user = security.current_user()
    unlink_telegram(user["id"])
    flash("Telegram scollegato. Continuerai a ricevere le notifiche via email, se attive.", "info")
    return redirect(url_for("prefs.show"))


def bot_username():
    return (current_app.config.get("TELEGRAM_BOT_USERNAME") or "").lstrip("@")
