"""Configurazione "dentro il link": fonti e parole chiave dentro il payload di /start.

Serve quando il sito è statico (GitHub Pages) e non c'è un server che possa salvare
un codice: la pagina costruisce da sola il payload e il bot lo rilegge. Nessun dato
personale, niente da conservare da nessuna parte.

Formato: "C1" + base64url( <1 byte: quante fonti ha il catalogo>
                            <bitmap delle fonti scelte, 1 bit per voce del catalogo>
                            <parole chiave separate da virgola, UTF-8> )

Il bit i-esimo corrisponde alla i-esima voce del catalogo: le voci si aggiungono
*in fondo*, mai in mezzo, altrimenti i link già generati punterebbero ad altre fonti
(vale comunque solo per i link ancora aperti in un browser, non c'è nulla di salvato).

Le parole da escludere viaggiano nella stessa lista con un "-" davanti ("A041,-infanzia"):
vedi words() e il campo "excluded" di decode().

Telegram accetta payload di /start fino a 64 caratteri di [A-Za-z0-9_-]: se le parole
chiave non ci stanno, encode() ritorna None e il sito propone il comando /setkeywords.
"""
import base64

from sfm.catalog import load_catalog

MAGIC = "C1"
MAX_PAYLOAD = 64


def _b64encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_indexes(indexes, catalog_size, keywords=()):
    """Payload per le posizioni di catalogo indicate. None se supera i 64 caratteri."""
    indexes = sorted({int(i) for i in indexes if 0 <= int(i) < catalog_size})
    if not indexes or not 0 < catalog_size <= 255:
        return None
    bitmap = bytearray((catalog_size + 7) // 8)
    for i in indexes:
        bitmap[i // 8] |= 1 << (7 - i % 8)
    text = ",".join(k.strip() for k in keywords if k and k.strip())
    payload = MAGIC + _b64encode(bytes([catalog_size]) + bytes(bitmap) + text.encode("utf-8"))
    return payload if len(payload) <= MAX_PAYLOAD else None


def words(keywords=(), excluded=()):
    """Parole chiave + parole da escludere (con "-" davanti) in un'unica lista da codificare."""
    clean = lambda w: w.strip().lstrip("-").strip()    # noqa: E731
    return [clean(k) for k in keywords if k and clean(k)] + ["-" + clean(w) for w in excluded if w and clean(w)]


def encode(source_urls, keywords=(), catalog=None):
    """Payload per un elenco di URL di fonti del catalogo (None se non ci sta)."""
    catalog = catalog if catalog is not None else load_catalog()
    positions = {entry["url"]: i for i, entry in enumerate(catalog)}
    indexes = [positions[u] for u in source_urls if u in positions]
    return encode_indexes(indexes, len(catalog), keywords)


def looks_like_payload(value):
    return bool(value) and value.startswith(MAGIC)


def decode(payload, catalog=None):
    """{"urls": [...], "keywords": [...]} oppure None se il payload non è leggibile."""
    if not looks_like_payload(payload):
        return None
    try:
        raw = _b64decode(payload[len(MAGIC):])
    except Exception:
        return None
    if len(raw) < 2:
        return None
    catalog_size = raw[0]
    n_bytes = (catalog_size + 7) // 8
    if catalog_size == 0 or len(raw) < 1 + n_bytes:
        return None
    bitmap, text = raw[1:1 + n_bytes], raw[1 + n_bytes:]
    catalog = catalog if catalog is not None else load_catalog()
    urls = [entry["url"] for i, entry in enumerate(catalog)
            if i < catalog_size and bitmap[i // 8] & (1 << (7 - i % 8))]
    try:
        items = [k.strip() for k in text.decode("utf-8").split(",") if k.strip()]
    except UnicodeDecodeError:
        return None
    if not urls:
        return None
    keywords = [k for k in items if not k.startswith("-")]
    excluded = [k[1:].strip() for k in items if k.startswith("-") and k[1:].strip()]
    return {"urls": urls, "keywords": keywords, "excluded": excluded}
