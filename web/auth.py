"""Registrazione, login, logout e area account (consenso, export, cancellazione)."""
import re
import secrets

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from sfm import mailer
from sfm.channels.email_channel import format_verification
from sfm.db_user import (
    consume_email_token,
    create_email_token,
    create_web_user,
    delete_user,
    export_user_data,
    get_password_hash,
    get_user_by_email,
    revoke_consent,
    set_active,
    set_consent,
    set_email_verified,
    set_password_hash,
)
from sfm.logger import log
from web import security

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LEN = 10


def _valid_email(email):
    return bool(email) and len(email) <= 254 and EMAIL_RE.match(email) is not None


def _password_problem(password):
    if not password or len(password) < PASSWORD_MIN_LEN:
        return f"La password deve avere almeno {PASSWORD_MIN_LEN} caratteri."
    if len(password) > 200:
        return "Password troppo lunga."
    return None


def _safe_next(target):
    """Solo percorsi relativi interni: evita open redirect."""
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("auth.account")


# --- verifica email (double opt-in) -------------------------------------------

def send_verification_email(user):
    """Genera un token e invia il link di conferma. Ritorna True se inviata,
    False se troppo presto (anti-spam) o se l'email è disabilitata (link solo nel log)."""
    token = secrets.token_urlsafe(32)
    if not create_email_token(user["id"], token, "verify"):
        return False
    base = current_app.config.get("BASE_URL") or request.url_root.rstrip("/")
    link = f"{base}{url_for('auth.verify_email', token=token)}"
    subject, html, text = format_verification(link)
    try:
        sent = mailer.send_email(user["email"], subject, html, text)
    except mailer.EmailError as e:
        log(f"❌ Email di verifica non inviata a {user['email']}: {e}")
        return False
    if not sent:
        log(f"✉️ [email disabilitata] link di verifica per {user['email']}: {link}")
    return sent


@bp.get("/verifica-email/<token>")
def verify_email(token):
    user_id = consume_email_token(token, "verify")
    if user_id is None:
        flash("Link di conferma non valido o scaduto. Richiedine uno nuovo dalla pagina Account.", "error")
        return redirect(url_for("auth.login"))
    set_email_verified(user_id, True)
    flash("Indirizzo confermato: le notifiche via email sono attive.", "success")
    return redirect(url_for("auth.account") if security.current_user() else url_for("auth.login"))


@bp.post("/account/verifica/reinvia")
@security.login_required
def resend_verification():
    user = security.current_user()
    if user["email_verified"]:
        flash("Il tuo indirizzo è già confermato.", "info")
    elif send_verification_email(user):
        flash(f"Email di conferma inviata a {user['email']}. Controlla anche lo spam.", "success")
    else:
        flash("Email già inviata da poco o servizio email non disponibile: riprova tra un minuto.", "error")
    return redirect(url_for("auth.account"))


# --- registrazione ----------------------------------------------------------

@bp.route("/registrati", methods=["GET", "POST"])
def register():
    if security.current_user():
        return redirect(url_for("auth.account"))
    if request.method == "GET":
        return render_template("registrati.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    consent = request.form.get("consent") == "on"

    errors = []
    if not _valid_email(email):
        errors.append("Inserisci un indirizzo email valido.")
    problem = _password_problem(password)
    if problem:
        errors.append(problem)
    if not consent:
        errors.append("Per registrarti devi accettare l'informativa sulla privacy e i termini del servizio.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("registrati.html", email=email), 400

    user = create_web_user(email, generate_password_hash(password),
                           consent_version=current_app.config["PRIVACY_VERSION"])
    if user is None:
        # Non riveliamo se l'email esiste: stesso messaggio del successo, ma nessun login.
        flash("Se l'indirizzo non era già registrato, l'account è stato creato. Accedi con le tue credenziali.", "info")
        return redirect(url_for("auth.login"))

    security.login_user(user)
    send_verification_email(user)
    flash("Benvenuto! Ti abbiamo inviato un'email: conferma l'indirizzo per attivare le notifiche. "
          "Intanto dicci dove insegni.", "success")
    return redirect(url_for("prefs.area", benvenuto=1))


# --- login / logout ---------------------------------------------------------

@bp.route("/accedi", methods=["GET", "POST"])
def login():
    if security.current_user():
        return redirect(url_for("auth.account"))
    if request.method == "GET":
        return render_template("accedi.html", next=request.args.get("next", ""))

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    if security.login_blocked(email):
        abort(429)

    user = get_user_by_email(email) if _valid_email(email) else None
    pw_hash = get_password_hash(user["id"]) if user else None
    if not user or not pw_hash or not check_password_hash(pw_hash, password):
        security.record_login_failure(email)
        flash("Email o password non corretti.", "error")
        return render_template("accedi.html", email=email, next=request.form.get("next", "")), 401

    security.clear_login_failures(email)
    security.login_user(user)
    return redirect(_safe_next(request.form.get("next")))


@bp.post("/esci")
def logout():
    security.logout_user()
    flash("Sei uscito.", "info")
    return redirect(url_for("index"))


# --- account ------------------------------------------------------------------

@bp.get("/account")
@security.login_required
def account():
    user = security.current_user()
    needs_consent = user["consent_version"] != current_app.config["PRIVACY_VERSION"]
    return render_template("account.html", user=user, needs_consent=needs_consent)


@bp.post("/account/consenso")
@security.login_required
def give_consent():
    user = security.current_user()
    if request.form.get("consent") != "on":
        flash("Devi spuntare la casella per dare il consenso.", "error")
        return redirect(url_for("auth.account"))
    set_consent(user["id"], current_app.config["PRIVACY_VERSION"])
    set_active(user["id"], True)
    flash("Consenso registrato. Le notifiche sono attive.", "success")
    return redirect(url_for("auth.account"))


@bp.post("/account/revoca")
@security.login_required
def revoke():
    user = security.current_user()
    revoke_consent(user["id"])
    flash("Consenso revocato: non riceverai più notifiche. Puoi riattivarle quando vuoi, oppure cancellare l'account.", "info")
    return redirect(url_for("auth.account"))


@bp.post("/account/password")
@security.login_required
def change_password():
    user = security.current_user()
    current, new = request.form.get("current") or "", request.form.get("new") or ""
    pw_hash = get_password_hash(user["id"])
    if not pw_hash or not check_password_hash(pw_hash, current):
        flash("La password attuale non è corretta.", "error")
        return redirect(url_for("auth.account"))
    problem = _password_problem(new)
    if problem:
        flash(problem, "error")
        return redirect(url_for("auth.account"))
    set_password_hash(user["id"], generate_password_hash(new))
    flash("Password aggiornata.", "success")
    return redirect(url_for("auth.account"))


@bp.get("/account/export.json")
@security.login_required
def export_data():
    data = export_user_data(security.current_user()["id"])
    resp = jsonify(data)
    resp.headers["Content-Disposition"] = "attachment; filename=school-feed-monitor-dati.json"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


@bp.post("/account/elimina")
@security.login_required
def delete_account():
    user = security.current_user()
    if request.form.get("confirm") != "ELIMINA":
        flash("Per cancellare l'account scrivi ELIMINA nel campo di conferma.", "error")
        return redirect(url_for("auth.account"))
    delete_user(user["id"])
    security.logout_user()
    flash("Account e dati cancellati definitivamente.", "info")
    return redirect(url_for("index"))
