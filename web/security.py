"""Protezioni del sito: CSRF sui POST e header di sicurezza.

Non ci sono account: nessuna sessione utente, nessuna password. La sessione Flask
serve solo a tenere il token CSRF.
"""
import secrets

from flask import abort, request, session

CSRF_KEY = "_csrf"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


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
        resp.headers.setdefault("Content-Security-Policy", CSP)
        return resp


def csrf_token():
    if CSRF_KEY not in session:
        session[CSRF_KEY] = secrets.token_urlsafe(32)
    return session[CSRF_KEY]
