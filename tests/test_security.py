"""Controlli trasversali su TUTTE le rotte web: CSRF, autenticazione, header, smoke delle pagine.
Se si aggiunge una rotta e ci si dimentica una protezione, questi test lo dicono."""
import pytest

from sfm.db_user import consume_email_token, consume_link_code, create_email_token, create_link_code, get_user_by_email
from tests.test_web import EMAIL, csrf, register
from web import create_app, security

PUBLIC_GET = ["/", "/notizie", "/registrati", "/accedi", "/password-dimenticata", "/privacy", "/termini", "/chi-siamo",
              "/robots.txt", "/sitemap.xml", "/reimposta-password/qualsiasi"]
PRIVATE_GET = ["/account", "/account/export.json", "/preferenze", "/preferenze/area", "/le-mie-notizie"]
PRIVATE_POST = ["/account/consenso", "/account/revoca", "/account/password", "/account/elimina", "/account/verifica/reinvia",
                "/preferenze", "/preferenze/fonti", "/preferenze/area", "/preferenze/telegram/codice", "/preferenze/telegram/scollega"]
PUBLIC_POST = ["/registrati", "/accedi", "/esci", "/password-dimenticata", "/reimposta-password/qualsiasi"]


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "BASE_URL": "https://sfm.example"})
    security.reset_rate_limits()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged(app):
    c = app.test_client()
    register(c)
    return c


def test_every_route_is_covered_by_this_file(app):
    """Ogni rotta dell'app deve comparire in una delle liste sopra (esclusi static e google)."""
    rules = {r.rule for r in app.url_map.iter_rules() if not r.rule.startswith("/static") and "/google" not in r.rule}
    known = set(PUBLIC_GET + PRIVATE_GET + PRIVATE_POST + PUBLIC_POST)
    known = {k.replace("/qualsiasi", "/<token>") for k in known}
    known |= {"/verifica-email/<token>", "/notizie/fonte/<int:source_id>", "/notizie/fonte/<int:source_id>/<slug>"}
    missing = rules - known
    assert not missing, f"rotte non coperte dai test di sicurezza: {sorted(missing)}"


@pytest.mark.parametrize("path", PRIVATE_POST + PUBLIC_POST)
def test_post_without_csrf_is_rejected(logged, path):
    assert logged.post(path, data={"email": EMAIL, "password": "x"}).status_code == 403


@pytest.mark.parametrize("path", PRIVATE_GET)
def test_private_pages_require_login(client, path):
    r = client.get(path)
    assert r.status_code == 302 and "/accedi" in r.headers["Location"]


@pytest.mark.parametrize("path", PRIVATE_POST)
def test_private_posts_require_login_even_with_csrf(client, path):
    tok = csrf(client, "/accedi")
    r = client.post(path, data={"_csrf": tok})
    assert r.status_code == 302 and "/accedi" in r.headers["Location"]


@pytest.mark.parametrize("path", PUBLIC_GET)
def test_public_pages_render(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    if r.mimetype == "text/html":
        html = r.get_data(as_text=True)
        assert '<html lang="it">' in html and '<link rel="canonical"' in html and "<title>" in html


@pytest.mark.parametrize("path", PRIVATE_GET)
def test_private_pages_render_for_logged_user(logged, path):
    r = logged.get(path)
    assert r.status_code == 200, path
    if r.mimetype == "text/html":
        assert 'name="robots" content="noindex' in r.get_data(as_text=True)


@pytest.mark.parametrize("path", PUBLIC_GET + ["/non-esiste"])
def test_security_headers_on_every_response(client, path):
    r = client.get(path)
    for header in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
        assert header in r.headers, (path, header)
    assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"]


def test_public_pages_have_no_third_party_resources(client):
    """Niente CDN, font o script esterni: una promessa dell'informativa (nessun tracker)."""
    for path in ("/", "/notizie", "/registrati", "/accedi", "/privacy", "/chi-siamo"):
        html = client.get(path).get_data(as_text=True)
        for tag in ("<script src=\"http", "<link rel=\"stylesheet\" href=\"http", "<img src=\"http", "fonts.googleapis"):
            assert tag not in html, (path, tag)


def test_session_cookie_flags(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False  # BASE_URL https ma test client http: si attiva da APP_BASE_URL reale
    https_app = create_app({"TESTING": True})
    assert https_app.config["SESSION_COOKIE_SECURE"] == (https_app.config["BASE_URL"].startswith("https://"))


def test_delete_account_removes_tokens_and_link_codes(logged):
    uid = get_user_by_email(EMAIL)["id"]
    create_email_token(uid, "tok-verify", "verify")
    create_link_code(uid, "ABCD2345")
    tok = csrf(logged, "/account")
    logged.post("/account/elimina", data={"_csrf": tok, "confirm": "ELIMINA"})
    assert consume_email_token("tok-verify") is None and consume_link_code("ABCD2345") is None


def test_forgot_password_is_rate_limited(client):
    tok = csrf(client, "/password-dimenticata")
    for _ in range(security.LOGIN_MAX_FAILURES):
        assert client.post("/password-dimenticata", data={"_csrf": tok, "email": "nessuno@x.it"}).status_code == 302
    assert client.post("/password-dimenticata", data={"_csrf": tok, "email": "nessuno@x.it"}).status_code == 429


def test_about_page_has_contact_and_disclaimer(client, app):
    html = client.get("/chi-siamo").get_data(as_text=True)
    assert app.config["CONTACT_EMAIL"] in html and "federicodiluca.github.io" in html and "AGPL" in html
    terms = client.get("/termini").get_data(as_text=True)
    assert 'id="responsabilita"' in terms and "non risponde di alcun" in terms
    home = client.get("/").get_data(as_text=True)
    assert "senza garanzia di completezza" in home and "/termini#responsabilita" in home
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/chi-siamo</loc>" in sitemap


def test_privacy_mentions_all_processors_and_rights(client, app):
    html = client.get("/privacy").get_data(as_text=True)
    for needle in ("Brevo", "Google", "Telegram", "72 ore", "portabilit", "revocare il consenso", "cancellare l", "cookie",
                   app.config["CONTACT_EMAIL"], "double opt-in"):
        assert needle in html, needle
