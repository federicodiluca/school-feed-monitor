"""Congela il sito in pagine statiche da pubblicare su GitHub Pages.

Le pagine sono le stesse del sito Flask, renderizzate con il client di prova sotto il
prefisso del Pages (es. /school-feed-monitor): il contenuto resta indicizzabile, mentre
filtri, preferenze e configuratore girano nel browser sui dati di `data/*.json`
(vedi web/static/app.js). Il server non viene mai esposto in rete.

    python -m scripts.build_site [--out site] [--base-url https://utente.github.io/repo]
"""
import argparse
import json
import os
import shutil
from urllib.parse import urlsplit

from sfm.db_news import latest_news
from sfm.db_sources import get_sources
from sfm.env import env
from sfm.logger import log
from sfm.utils import slugify, strip_html
from web import create_app
from web.configurator import catalog_positions

DEFAULT_BASE_URL = "https://federicodiluca.github.io/school-feed-monitor"
NEWS_IN_DATASET = 1200         # quante notizie finiscono nel JSON usato dal browser
NEWS_DAYS = 90
PREVIEW_CHARS = 220

# (percorso sull'app, file nella cartella di uscita)
PAGES = [
    ("/", "index.html"),
    ("/notizie", "notizie/index.html"),
    ("/le-mie-notizie", "le-mie-notizie/index.html"),
    ("/configura", "configura/index.html"),
    ("/chi-siamo", "chi-siamo/index.html"),
    ("/privacy", "privacy/index.html"),
    ("/termini", "termini/index.html"),
    ("/robots.txt", "robots.txt"),
    ("/sitemap.xml", "sitemap.xml"),
]


def _preview(text):
    clean = strip_html(text or "").strip()
    if len(clean) <= PREVIEW_CHARS:
        return clean
    return clean[:PREVIEW_CHARS].rsplit(" ", 1)[0] + "…"


def _write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    mode, encoding = ("wb", None) if isinstance(content, bytes) else ("w", "utf-8")
    with open(path, mode, encoding=encoding) as f:
        f.write(content)


def _fetch(client, base_url, path):
    resp = client.get(path, base_url=base_url)
    if resp.status_code != 200:
        raise RuntimeError(f"{path} ha risposto {resp.status_code}: il sito statico sarebbe rotto")
    return resp.data


def news_dataset(sources):
    """Le notizie che il browser filtra: poche chiavi, nomi corti (il file viene scaricato)."""
    names = {s["id"]: s["name"] for s in sources}
    rows = latest_news(limit=NEWS_IN_DATASET, days=NEWS_DAYS)
    items = [{"i": r["id"], "t": r["title"], "l": r["link"], "s": r["source_id"],
              "n": names.get(r["source_id"], r["source"] or ""), "d": r["published_at"],
              "p": _preview(r["content"])}
             for r in rows]
    return {"items": items, "days": NEWS_DAYS}


def sources_dataset(sources):
    positions = catalog_positions()
    items = [{"id": s["id"], "name": s["name"], "kind": s["kind"], "region": s["region"],
              "province": s["province"], "url": s["url"],
              "page": f"/notizie/fonte/{s['id']}/{slugify(s['name'])}",
              "catalog": positions.get(s["url"], -1)}
             for s in sources]
    return {"items": items, "catalog_size": len(positions)}


def build(out_dir="site", base_url=None, bot_username=None):
    base_url = (base_url or env("SITE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    prefix = urlsplit(base_url).path.rstrip("/")
    app = create_app({"STATIC": True, "BASE_URL": base_url,
                      "TELEGRAM_BOT_USERNAME": (bot_username or env("TELEGRAM_BOT_USERNAME") or "").lstrip("@")})
    client = app.test_client()

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    for path, target in PAGES:
        _write(os.path.join(out_dir, target), _fetch(client, base_url, path))

    sources = get_sources()
    for s in sources:
        path = f"/notizie/fonte/{s['id']}/{slugify(s['name'])}"
        _write(os.path.join(out_dir, path.lstrip("/"), "index.html"), _fetch(client, base_url, path))

    # pagina di errore di GitHub Pages
    _write(os.path.join(out_dir, "404.html"), client.get("/pagina-che-non-esiste", base_url=base_url).data)

    shutil.copytree(os.path.join(os.path.dirname(__file__), "..", "web", "static"),
                    os.path.join(out_dir, "static"), dirs_exist_ok=True)
    shutil.copy(os.path.join(out_dir, "static", "sw.js"), os.path.join(out_dir, "sw.js"))

    for name, payload in (("news", news_dataset(sources)), ("sources", sources_dataset(sources))):
        _write(os.path.join(out_dir, "data", f"{name}.json"),
               json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    _write(os.path.join(out_dir, ".nojekyll"), "")       # niente Jekyll: i file passano così come sono
    log(f"[build_site] sito generato in {out_dir} ({len(sources)} fonti, prefisso '{prefix or '/'}')")
    return out_dir


def main():
    parser = argparse.ArgumentParser(description="Genera il sito statico per GitHub Pages")
    parser.add_argument("--out", default="site", help="cartella di uscita (default: site)")
    parser.add_argument("--base-url", default=None, help=f"URL pubblico (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--bot", default=None, help="username del bot Telegram, senza @")
    args = parser.parse_args()
    build(args.out, args.base_url, args.bot)


if __name__ == "__main__":
    main()
