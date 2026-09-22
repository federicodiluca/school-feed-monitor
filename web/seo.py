"""SEO: canonical, robots.txt, sitemap.xml. Le pagine pubbliche sono renderizzate lato server."""
from urllib.parse import urlsplit

from flask import Response, current_app, request, url_for

from sfm.db_news import latest_per_source
from sfm.db_sources import get_sources

# Pagine pubbliche indicizzabili: (endpoint, priorità, changefreq)
PUBLIC_PAGES = [
    ("index", "1.0", "daily"),
    ("news.index", "0.9", "hourly"),
    ("news.sources", "0.8", "weekly"),
    ("config.show", "0.8", "monthly"),
    ("about", "0.6", "monthly"),
    ("privacy", "0.2", "yearly"),
    ("terms", "0.2", "yearly"),
]
PRIVATE_PREFIXES = ("/le-mie-notizie", "/configura/esporta.json")  # dipendono dai cookie del visitatore


def origin(base):
    """Solo schema + host: gli URL di url_for portano già il prefisso (sito statico su Pages)."""
    parts = urlsplit(base)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else base.rstrip("/")


def canonical_url(req=None):
    """URL canonico della pagina corrente (senza query string), basato su APP_BASE_URL se impostato."""
    req = req or request
    base = current_app.config.get("BASE_URL") or req.url_root.rstrip("/")
    return base + req.path


def init_app(app):
    from web.news import source_url  # import locale: web.news importa web.security

    @app.get("/robots.txt")
    def robots():
        base = app.config.get("BASE_URL") or request.url_root.rstrip("/")
        prefix = request.script_root or ""
        lines = (["User-agent: *", "Allow: /"] + [f"Disallow: {prefix}{p}" for p in PRIVATE_PREFIXES]
                 + [f"Sitemap: {base}/sitemap.xml"])
        return Response("\n".join(lines) + "\n", mimetype="text/plain")

    @app.get("/sitemap.xml")
    def sitemap():
        base = app.config.get("BASE_URL") or request.url_root.rstrip("/")
        entries = [(url_for(endpoint), prio, freq) for endpoint, prio, freq in PUBLIC_PAGES]
        entries = [(path, prio, freq, None) for path, prio, freq in entries]
        last = latest_per_source()
        entries += [(source_url(s), "0.7", "daily", (last.get(s["id"]) or "")[:10]) for s in get_sources()]
        host = origin(base)
        urls = "".join(
            f"<url><loc>{host}{path}</loc>"
            + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
            + f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
            for path, prio, freq, lastmod in entries
        )
        body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
        return Response(body, mimetype="application/xml")
