"""Accesso con Google (OpenID Connect via authlib).

Configurazione: GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nell'ambiente; se mancano il
pulsante non compare. Redirect URI da registrare nella Google Cloud Console:
    <APP_BASE_URL>/accedi/google/callback

Flusso: Google restituisce email verificata + `sub` (id stabile). Se esiste un utente con
quel sub o con quella email → login. Se è nuovo, prima di creare l'account chiediamo il
consenso privacy (pagina "completa registrazione"): nessun dato viene salvato prima.
"""
import secrets

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from sfm.db_user import create_web_user, get_user_by_email, get_user_by_google_sub, set_email_verified, set_google_sub
from web import security

bp = Blueprint("google", __name__)
oauth = OAuth()
PENDING_KEY = "google_pending"  # {"email":..., "sub":...} in sessione, in attesa del consenso


def init_app(app):
    app.config["GOOGLE_ENABLED"] = bool(app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"))
    if not app.config["GOOGLE_ENABLED"]:
        return
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email"},
    )


def _enabled():
    return current_app.config.get("GOOGLE_ENABLED", False)


@bp.get("/accedi/google")
def start():
    if not _enabled():
        return redirect(url_for("auth.login"))
    redirect_uri = (current_app.config.get("BASE_URL") or request.url_root.rstrip("/")) + url_for("google.callback")
    return oauth.google.authorize_redirect(redirect_uri)


def fetch_google_identity():
    """Completa lo scambio del codice e ritorna {"email", "sub"} (email verificata) o None."""
    token = oauth.google.authorize_access_token()
    info = token.get("userinfo") or oauth.google.parse_id_token(token, nonce=session.get("nonce"))
    if not info or not info.get("email") or not info.get("email_verified") or not info.get("sub"):
        return None
    return {"email": info["email"].strip().lower(), "sub": info["sub"]}


@bp.get("/accedi/google/callback")
def callback():
    if not _enabled():
        return redirect(url_for("auth.login"))
    try:
        identity = fetch_google_identity()
    except Exception as e:  # stato non valido, token rifiutato, rete
        current_app.logger.warning("Google login fallito: %s", e)
        identity = None
    if not identity:
        flash("Accesso con Google non riuscito. Riprova o usa email e password.", "error")
        return redirect(url_for("auth.login"))
    identity = {"email": identity["email"].strip().lower(), "sub": str(identity["sub"])}

    user = get_user_by_google_sub(identity["sub"]) or get_user_by_email(identity["email"])
    if user:
        if not user.get("google_sub"):
            set_google_sub(user["id"], identity["sub"])
        if not user.get("email_verified") and user.get("email") == identity["email"]:
            set_email_verified(user["id"], True)
        security.login_user(user)
        return redirect(url_for("auth.account"))

    session[PENDING_KEY] = identity
    return redirect(url_for("google.complete"))


@bp.route("/accedi/google/completa", methods=["GET", "POST"])
def complete():
    """Nuovo utente da Google: chiede il consenso privacy, poi crea l'account."""
    pending = session.get(PENDING_KEY)
    if not pending:
        return redirect(url_for("auth.login"))
    if request.method == "GET":
        return render_template("google_completa.html", email=pending["email"])
    if request.form.get("consent") != "on":
        flash("Per completare la registrazione devi accettare l'informativa sulla privacy e i termini.", "error")
        return render_template("google_completa.html", email=pending["email"]), 400

    # Nessuna password: l'accesso avviene solo tramite Google (hash casuale, non indovinabile).
    user = create_web_user(pending["email"], f"google:{secrets.token_hex(32)}",
                           consent_version=current_app.config["PRIVACY_VERSION"])
    if user is None:  # creato nel frattempo con la stessa email
        user = get_user_by_email(pending["email"])
    set_google_sub(user["id"], pending["sub"])
    set_email_verified(user["id"], True)  # Google la garantisce verificata
    session.pop(PENDING_KEY, None)
    security.login_user(user)
    flash("Benvenuto! Il tuo account è pronto: dicci dove insegni per scegliere le fonti giuste.", "success")
    return redirect(url_for("prefs.area", benvenuto=1))
