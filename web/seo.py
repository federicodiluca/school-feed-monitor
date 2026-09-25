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


def page_path(url):
    """Sul sito statico ogni pagina è una cartella con index.html, e GitHub Pages porta
    /notizie su /notizie/ con un 301: canonical, sitemap e link interni devono usare già
    l'indirizzo con la barra, o Google trova un canonical che punta a un redirect.
    I file veri (style.css, sitemap.xml, esporta.json...) restano come sono."""
    path, sep, rest = url.partition("?") if "?" in url else url.partition("#")
    last = path.rsplit("/", 1)[-1]
    if path.endswith("/") or "." in last:
        return url
    return path + "/" + sep + rest


def absolute_url(path):
    """URL assoluto per un percorso di url_for, che porta già il prefisso di Pages:
    non va attaccato a BASE_URL, che lo contiene anche lui (prefisso doppio)."""
    return origin(current_app.config.get("BASE_URL") or request.url_root) + path


def canonical_url(req=None):
    """URL canonico della pagina corrente (senza query string), basato su APP_BASE_URL se impostato."""
    req = req or request
    if current_app.config.get("STATIC"):
        # BASE_URL porta già il prefisso di Pages, che è anche in script_root
        return origin(current_app.config["BASE_URL"]) + page_path(req.script_root + req.path)
    base = current_app.config.get("BASE_URL") or req.url_root.rstrip("/")
    return base + req.path


def init_app(app):
    from web.news import region_sources, region_url, regions_with_sources, source_url  # import locale: web.news importa web.security

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
        last = latest_per_source()
        newest = max((d or "" for d in last.values()), default="")[:10] or None
        # home e /notizie cambiano con l'ultima notizia arrivata, da qualunque fonte
        entries = [(url_for(endpoint), prio, freq, newest if endpoint in ("index", "news.index") else None)
                   for endpoint, prio, freq in PUBLIC_PAGES]
        sources = get_sources()
        for region in regions_with_sources(sources):
            dates = [last.get(s["id"]) or "" for s in region_sources(region, sources)]
            entries.append((region_url(region), "0.8", "daily", max(dates)[:10] or None))
        entries += [(source_url(s), "0.7", "daily", (last.get(s["id"]) or "")[:10]) for s in sources]
        host = origin(base)
        urls = "".join(
            f"<url><loc>{host}{path}</loc>"
            + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
            + f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
            for path, prio, freq, lastmod in entries
        )
        body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
        return Response(body, mimetype="application/xml")
