"""Sessione, CSRF, rate limit e protezione delle pagine riservate."""
import secrets
import time
from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from sfm.db_user import get_user_by_id

CSRF_KEY = "_csrf"
LOGIN_MAX_FAILURES = 5          # tentativi falliti per IP+email...
LOGIN_WINDOW_SECONDS = 15 * 60  # ...in questa finestra → 429

_failures = {}  # {(ip, email): [timestamp, ...]}  (in memoria: basta per un singolo processo)


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get(CSRF_KEY) or request.headers.get("X-CSRF-Token")
            expected = session.get(CSRF_KEY)
            if not expected or not sent or not secrets.compare_digest(sent, expected):
                abort(403)

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; form-action 'self'")
        return resp


# --- CSRF -----------------------------------------------------------------

def csrf_token():
    if CSRF_KEY not in session:
        session[CSRF_KEY] = secrets.token_urlsafe(32)
    return session[CSRF_KEY]


# --- sessione utente ------------------------------------------------------

def login_user(user, remember=True):
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = remember
    csrf_token()


def logout_user():
    session.clear()


def current_user():
    """Utente loggato (dict) o None; cache per richiesta in g."""
    if "user" not in g:
        uid = session.get("user_id")
        g.user = get_user_by_id(uid) if uid else None
        if uid and g.user is None:
            session.clear()  # utente cancellato: sessione orfana
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# --- rate limit login -------------------------------------------------------

def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() if fwd else request.remote_addr) or "?"


def _prune(key, now):
    stamps = [t for t in _failures.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
    if stamps:
        _failures[key] = stamps
    else:
        _failures.pop(key, None)
    return stamps


def login_blocked(email):
    key = (_client_ip(), (email or "").lower())
    return len(_prune(key, time.time())) >= LOGIN_MAX_FAILURES


def record_login_failure(email):
    key = (_client_ip(), (email or "").lower())
    now = time.time()
    _failures[key] = _prune(key, now) + [now]


def clear_login_failures(email):
    _failures.pop((_client_ip(), (email or "").lower()), None)


def reset_rate_limits():
    _failures.clear()
