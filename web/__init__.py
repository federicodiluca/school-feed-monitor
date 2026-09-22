"""School Feed Monitor — layer web (Flask, server-side rendering).

Sito pubblico senza account: mostra le notizie raccolte, le filtra con le preferenze
salvate nel browser di chi visita e genera la configurazione per il bot Telegram.
Processo separato dal bot, stesso database SQLite (WAL).

Configurazione via ambiente / .env:
    SECRET_KEY              chiave per firmare il cookie di sessione (solo token CSRF)
    APP_BASE_URL            URL pubblico (canonical, sitemap)
    FLASK_DEBUG             1 per il server di sviluppo
    TELEGRAM_BOT_USERNAME   username del bot (senza @) per i link "apri il bot"
    CONTACT_EMAIL           email pubblica di contatto (pagina Chi siamo, privacy)
"""
import secrets

from flask import Flask, render_template, request

from sfm.config_loader import get_config
from sfm.db import init_db
from sfm.db_news import search_news
from sfm.db_sources import sync_config_sources
from sfm.env import env, env_bool
from sfm.utils import format_local_datetime, strip_html
from web import prefs, seo, security
from web.configurator import bp as config_bp, telegram_link
from web.news import bp as news_bp, source_url

APP_NAME = "School Feed Monitor"
PRIVACY_VERSION = "2026-09-22"

_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre"]


def giorno_it(d):
    """date -> 'Sabato 13 settembre 2026' (senza dipendere dal locale del server)."""
    return f"{_GIORNI[d.weekday()].capitalize()} {d.day} {_MESI[d.month - 1]} {d.year}"


def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    secret = env("SECRET_KEY")
    debug = env_bool("FLASK_DEBUG", False)
    if not secret:
        if not debug and not test_config:
            raise RuntimeError("SECRET_KEY mancante: impostala in .env "
                               "(es. `python -c \"import secrets; print(secrets.token_hex(32))\"`)")
        secret = secrets.token_hex(32)  # solo sviluppo/test

    app.config.update(
        SECRET_KEY=secret,
        APP_NAME=APP_NAME,
        PRIVACY_VERSION=PRIVACY_VERSION,
        BASE_URL=(env("APP_BASE_URL") or "").rstrip("/"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(env("APP_BASE_URL") or "").startswith("https://"),
        MAX_CONTENT_LENGTH=64 * 1024,
        TELEGRAM_BOT_USERNAME=(env("TELEGRAM_BOT_USERNAME") or "").lstrip("@"),
        CONTACT_EMAIL=env("CONTACT_EMAIL") or "schoolfeedmonitor@gmail.com",
    )
    if test_config:
        app.config.update(test_config)

    init_db()
    # Le fonti di config.json + catalogo vivono nel DB: le allinea anche il web, così il
    # sito funziona anche se il bot non è ancora partito (idempotente, come in main.py).
    sync_config_sources(get_config()["sites"])
    security.init_app(app)
    seo.init_app(app)
    app.register_blueprint(news_bp)
    app.register_blueprint(config_bp)
    app.jinja_env.filters["local_datetime"] = lambda v: format_local_datetime(v, "%d/%m/%Y %H:%M")
    app.jinja_env.filters["preview"] = lambda v, n=220: (lambda t: t[:n].rsplit(" ", 1)[0] + "…" if len(t) > n else t)(strip_html(v or ""))
    app.jinja_env.filters["giorno_it"] = giorno_it
    app.jinja_env.globals["source_url"] = source_url

    @app.get("/")
    def index():
        latest, _ = search_news(days=7, page=1, per_page=5)
        return render_template("index.html", latest=latest)

    @app.get("/sw.js")
    def service_worker():
        resp = app.send_static_file("sw.js")
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.get("/termini")
    def terms():
        return render_template("termini.html")

    @app.get("/chi-siamo")
    def about():
        return render_template("chi_siamo.html")

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errore.html", code=404, message="Pagina non trovata."), 404

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errore.html", code=403, message="Richiesta non valida o scaduta: ricarica la pagina e riprova."), 403

    @app.context_processor
    def inject_globals():
        return {"app_name": APP_NAME, "canonical": seo.canonical_url(request),
                "bot_username": app.config.get("TELEGRAM_BOT_USERNAME", ""),
                "contact_email": app.config.get("CONTACT_EMAIL", ""),
                "telegram_link": telegram_link,
                "has_prefs": prefs.has_preferences(),
                "n_prefs_sources": len(prefs.selected_source_ids())}

    return app
