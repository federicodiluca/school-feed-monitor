"""Scarica tutte le fonti (config + catalogo) e salva le notizie nel DB, SENZA inviare
notifiche e senza avviare il bot Telegram. Utile in sviluppo per riempire il sito.

    python scripts/fetch_now.py            # tutte le fonti attive
    python scripts/fetch_now.py --limit 10 # solo le prime N (per una prova veloce)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(errors="replace")

from sfm.config_loader import get_config  # noqa: E402
from sfm.db import init_db  # noqa: E402
from sfm.db_sources import get_sources, sync_config_sources  # noqa: E402
from sfm.news_fetcher import fetch_source  # noqa: E402


def main(argv):
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    init_db()
    n, created = sync_config_sources(get_config()["sites"])
    print(f"Fonti configurate: {n} ({len(created)} nuove nel DB)")
    sources = get_sources()[:limit]
    total, failed, start = 0, 0, time.time()
    for i, source in enumerate(sources, 1):
        t = time.time()
        new = fetch_source(source, notify=False)
        total += new
        print(f"[{i:3}/{len(sources)}] {source['name'][:40]:40} +{new:3}  ({time.time() - t:.1f}s)")
    print(f"\nFinito: {total} notizie nuove da {len(sources)} fonti in {time.time() - start:.0f}s. "
          "Nessuna notifica inviata.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
