"""Ponte europeo per le fonti che non rispondono agli indirizzi IP esteri.

Alcuni siti istituzionali (al 22 settembre 2026: istruzione.calabria.it e uspmc.sinp.net)
lasciano cadere le connessioni che arrivano da fuori Italia. Il bot gira su una VM
americana, quindi per quelle fonti passa da qui: un servizio minuscolo su Cloud Run in
Europa che scarica la pagina e la restituisce così com'è.

Non è un proxy aperto: risponde solo per i domini in ALLOWED_HOSTS e solo a chi manda la
chiave condivisa (header X-Sfm-Key). Non registra nulla se non gli errori.

Variabili d'ambiente:
    ALLOWED_HOSTS   domini ammessi, separati da virgola (obbligatoria)
    PROXY_KEY       chiave condivisa; se assente il servizio rifiuta tutto
    MAX_BYTES       dimensione massima della risposta (default 5 MB)
    FETCH_TIMEOUT   timeout verso il sito di origine (default 25 s)
"""
import os
from urllib.parse import urlparse

import requests
from flask import Flask, Response, request

app = Flask(__name__)

USER_AGENT = ("Mozilla/5.0 (compatible; SchoolFeedMonitor/1.0; "
              "+https://github.com/federicodiluca/school-feed-monitor)")
ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()}
PROXY_KEY = os.environ.get("PROXY_KEY", "")
MAX_BYTES = int(os.environ.get("MAX_BYTES", 5 * 1024 * 1024))
FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", 25))


def allowed(url):
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


@app.get("/health")
def health():
    return {"ok": True, "hosts": sorted(ALLOWED_HOSTS)}


@app.get("/fetch")
def fetch():
    if not PROXY_KEY or request.headers.get("X-Sfm-Key") != PROXY_KEY:
        return Response("chiave mancante o errata", status=403, mimetype="text/plain")
    url = request.args.get("url", "")
    if not allowed(url):
        return Response("dominio non ammesso", status=403, mimetype="text/plain")
    try:
        upstream = requests.get(url, headers={"User-Agent": USER_AGENT},
                                timeout=FETCH_TIMEOUT, stream=True)
    except requests.RequestException as e:
        return Response(f"origine non raggiungibile: {e}", status=502, mimetype="text/plain")
    body = upstream.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(body) > MAX_BYTES:
        return Response("risposta troppo grande", status=502, mimetype="text/plain")
    return Response(body, status=upstream.status_code,
                    mimetype=upstream.headers.get("content-type", "application/octet-stream"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
