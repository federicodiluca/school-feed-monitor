import re

import pytest

from sfm.db_user import get_user_by_email, get_user_by_id, get_users
from web import create_app
from web import security

EMAIL, PASSWORD = "prof@scuola.it", "password-lunga-123"


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})
    security.reset_rate_limits()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path="/registrati"):
    """Apre una pagina con form e ne estrae il token CSRF (lo mette in sessione)."""
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert m, "token CSRF non trovato"
    return m.group(1)


def register(client, email=EMAIL, password=PASSWORD, consent=True, follow=True):
    data = {"_csrf": csrf(client), "email": email, "password": password}
    if consent:
        data["consent"] = "on"
    return client.post("/registrati", data=data, follow_redirects=follow)


def login(client, email=EMAIL, password=PASSWORD, follow=False):
    return client.post("/accedi", data={"_csrf": csrf(client, "/accedi"), "email": email, "password": password},
                       follow_redirects=follow)


# --- pagine pubbliche e SEO -----------------------------------------------------

def test_public_pages_render_with_seo_tags(client):
    html = client.get("/").get_data(as_text=True)
    assert "<title>School Feed Monitor" in html
    assert '<link rel="canonical" href="https://sfm.example/">' in html
    assert 'name="description"' in html and 'property="og:title"' in html and '<html lang="it">' in html
    assert "<h1>" in html and "Registrati gratis" in html
    for path in ("/privacy", "/termini", "/registrati", "/accedi"):
        r = client.get(path)
        assert r.status_code == 200 and "<h1>" in r.get_data(as_text=True)


def test_robots_and_sitemap(client):
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Sitemap: https://sfm.example/sitemap.xml" in robots and "Disallow: /account" in robots
    sitemap = client.get("/sitemap.xml")
    assert sitemap.mimetype == "application/xml"
    body = sitemap.get_data(as_text=True)
    assert "<loc>https://sfm.example/</loc>" in body and "<loc>https://sfm.example/privacy</loc>" in body
    assert "/account" not in body


def test_security_headers_and_404(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]
    r = client.get("/non-esiste")
    assert r.status_code == 404 and "Pagina non trovata" in r.get_data(as_text=True)


# --- registrazione ------------------------------------------------------------------

def test_register_creates_user_with_consent_and_logs_in(client, app):
    r = register(client)
    assert r.status_code == 200 and "Benvenuto" in r.get_data(as_text=True)
    user = get_user_by_email(EMAIL)
    assert user and user["consent_version"] == app.config["PRIVACY_VERSION"] and user["consent_at"]
    assert user["alert_mode"] == "digest" and user["notify_email"] and user["active"]
    assert client.get("/account").status_code == 200


def test_register_validation(client):
    r = register(client, email="nonvalida", password="corta", consent=False, follow=False)
    assert r.status_code == 400
    html = r.get_data(as_text=True)
    assert "email valido" in html and "almeno 10 caratteri" in html and "informativa" in html
    assert get_users(active_only=False) == []


def test_register_duplicate_email_does_not_leak(client):
    register(client)
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    r = register(client, password="altra-password-456", follow=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/accedi")
    assert len(get_users(active_only=False)) == 1
    assert client.get("/account").status_code == 302   # non loggato


def test_csrf_required_on_post(client):
    r = client.post("/registrati", data={"email": EMAIL, "password": PASSWORD, "consent": "on"})
    assert r.status_code == 403
    assert get_users(active_only=False) == []


# --- login / logout ---------------------------------------------------------------------

def test_login_logout_flow(client):
    register(client)
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    assert client.get("/account").status_code == 302

    r = login(client, password="sbagliata")
    assert r.status_code == 401 and "non corretti" in r.get_data(as_text=True)

    r = login(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/account")
    assert "prof@scuola.it" in client.get("/account").get_data(as_text=True)


def test_login_next_only_internal(client):
    register(client)
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    r = client.post("/accedi", data={"_csrf": csrf(client, "/accedi"), "email": EMAIL, "password": PASSWORD,
                                     "next": "https://evil.example/"})
    assert r.headers["Location"].endswith("/account")
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    r = client.post("/accedi", data={"_csrf": csrf(client, "/accedi"), "email": EMAIL, "password": PASSWORD, "next": "/privacy"})
    assert r.headers["Location"].endswith("/privacy")


def test_login_rate_limit(client):
    register(client)
    client.post("/esci", data={"_csrf": csrf(client, "/")})
    for _ in range(security.LOGIN_MAX_FAILURES):
        assert login(client, password="no").status_code == 401
    assert login(client).status_code == 429          # anche con la password giusta
    security.reset_rate_limits()
    assert login(client).status_code == 302


# --- account: password, consenso, export, cancellazione -----------------------------------

def test_change_password(client):
    register(client)
    tok = csrf(client, "/account")
    r = client.post("/account/password", data={"_csrf": tok, "current": "sbagliata", "new": "nuova-password-789"}, follow_redirects=True)
    assert "non è corretta" in r.get_data(as_text=True)
    r = client.post("/account/password", data={"_csrf": tok, "current": PASSWORD, "new": "nuova-password-789"}, follow_redirects=True)
    assert "aggiornata" in r.get_data(as_text=True)
    client.post("/esci", data={"_csrf": tok})
    assert login(client, password="nuova-password-789").status_code == 302


def test_revoke_and_regive_consent(client, app):
    register(client)
    tok = csrf(client, "/account")
    r = client.post("/account/revoca", data={"_csrf": tok}, follow_redirects=True)
    html = r.get_data(as_text=True)
    user = get_user_by_email(EMAIL)
    assert user["active"] is False and user["consent_at"] is None
    assert "Consenso richiesto" in html and "sospese" in html

    r = client.post("/account/consenso", data={"_csrf": tok}, follow_redirects=True)
    assert "spuntare" in r.get_data(as_text=True)
    r = client.post("/account/consenso", data={"_csrf": tok, "consent": "on"}, follow_redirects=True)
    user = get_user_by_email(EMAIL)
    assert user["active"] is True and user["consent_version"] == app.config["PRIVACY_VERSION"]
    assert "Consenso registrato" in r.get_data(as_text=True)


def test_privacy_version_change_requires_new_consent(client, app):
    register(client)
    app.config["PRIVACY_VERSION"] = "2099-01-01"
    html = client.get("/account").get_data(as_text=True)
    assert "Consenso richiesto" in html and "è cambiata" in html


def test_export_data_json(client):
    register(client)
    r = client.get("/account/export.json")
    assert r.status_code == 200 and r.mimetype == "application/json"
    data = r.get_json()
    assert data["user"]["email"] == EMAIL and "password_hash" not in data["user"]
    assert data["source_preferences"] == [] and data["deliveries"] == []
    assert "attachment" in r.headers["Content-Disposition"]


def test_delete_account_requires_confirmation_and_removes_everything(client):
    register(client)
    uid = get_user_by_email(EMAIL)["id"]
    from sfm.db_deliveries import record_delivery
    from sfm.db_sources import set_user_source
    set_user_source(uid, 1, False)
    record_delivery(uid, 1, "email", "digest")
    tok = csrf(client, "/account")

    r = client.post("/account/elimina", data={"_csrf": tok, "confirm": "no"}, follow_redirects=True)
    assert "ELIMINA" in r.get_data(as_text=True) and get_user_by_id(uid)

    r = client.post("/account/elimina", data={"_csrf": tok, "confirm": "ELIMINA"}, follow_redirects=True)
    assert "cancellati" in r.get_data(as_text=True)
    assert get_user_by_id(uid) is None
    from sfm.db import get_conn
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) FROM user_sources WHERE user_id=?", (uid,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM deliveries WHERE user_id=?", (uid,)).fetchone()[0] == 0
    conn.close()
    assert client.get("/account").status_code == 302


def test_account_page_is_noindex(client):
    register(client)
    assert 'content="noindex, nofollow"' in client.get("/account").get_data(as_text=True)


def test_missing_secret_key_fails_outside_debug(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    with pytest.raises(RuntimeError):
        create_app()
