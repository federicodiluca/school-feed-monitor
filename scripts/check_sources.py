"""Verifica un elenco di URL con il parser reale (detect_source) e stampa cosa trova.

    python scripts/check_sources.py URL [URL ...]
    python scripts/check_sources.py --catalog          # tutte le voci di sfm/catalog/italy.json
    python scripts/check_sources.py --file elenco.txt  # un URL per riga (# = commento)

Per ogni URL: tipo rilevato (rss/html), URL effettiva (feed scoperto), numero di notizie,
titolo suggerito e prima notizia. Serve a costruire e mantenere il catalogo.
"""
import os
import sys

sys.stdout.reconfigure(errors="replace")  # console Windows cp1252
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sfm.source_parser import SourceError, detect_source, read_source  # noqa: E402


def check(url, label=None, source_type=None):
    """source_type: se dato (voci di catalogo) legge come farebbe il bot, altrimenti autodetect."""
    try:
        if source_type:
            items = read_source({"url": url, "type": source_type})
            d = {"type": source_type, "url": url, "name": "", "items": items}
        else:
            d = detect_source(url)
    except SourceError as e:
        print(f"KO   {label or url}\n     {url}\n     {e}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"ERR  {label or url}\n     {url}\n     {type(e).__name__}: {e}")
        return None
    first = d["items"][0]
    print(f"OK   {label or url}\n     {d['type']:4} {len(d['items']):3} items  {d['url']}\n"
          f"     titolo: {d['name']!r}\n     prima: {first['title'][:90]!r} ({first['published'][:19]})")
    return d


def main(argv):
    urls = []
    if "--catalog" in argv:
        from sfm.catalog import load_catalog
        urls = [(e["url"], f"{e['name']} [{e['kind']} {e.get('region') or ''} {e.get('province') or ''}]", e["type"]) for e in load_catalog()]
    elif "--file" in argv:
        path = argv[argv.index("--file") + 1]
        with open(path, encoding="utf-8") as f:
            urls = [(l.strip(), None, None) for l in f if l.strip() and not l.startswith("#")]
    else:
        urls = [(u, None, None) for u in argv[1:]]
    if not urls:
        print(__doc__)
        return 2
    ok = 0
    for url, label, source_type in urls:
        if check(url, label, source_type):
            ok += 1
    print(f"\n{ok}/{len(urls)} fonti leggibili")
    return 0 if ok == len(urls) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
