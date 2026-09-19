import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

PREVIEW_MAX_LEN = 400

# Apostrofi/virgolette "tipografici" che vanno ricondotti a quelli ASCII,
# così le keyword inserite dall'utente corrispondono al testo dei feed.
_APOSTROPHES = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'", "`": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
}


def normalize_text(text):
    """Normalizza apostrofi e virgolette tipografiche in caratteri ASCII."""
    if not text:
        return ""
    for src, dst in _APOSTROPHES.items():
        text = text.replace(src, dst)
    return text


def strip_html(raw_content):
    """Rimuove i tag HTML e restituisce il testo puro."""
    if not raw_content:
        return ""
    soup = BeautifulSoup(raw_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def escape_html(text):
    """Escape per l'HTML di Telegram (&, <, >, ")."""
    return html.escape(str(text) if text is not None else "", quote=True)


def cleanHTMLPreview(raw_content, max_len=PREVIEW_MAX_LEN):
    """Rimuove i tag HTML, limita la lunghezza del testo e lo rende sicuro per Telegram."""
    content_text = strip_html(raw_content)
    preview = content_text[:max_len] + "..." if len(content_text) > max_len else content_text
    return escape_html(preview)


def parse_keywords(text):
    """Divide una lista di keyword separate da virgola, scartando le vuote."""
    if not text:
        return []
    return [normalize_text(kw).strip() for kw in text.split(",") if kw.strip()]


def keyword_pattern(keyword):
    """Regex per la ricerca esatta di una keyword (anche composta o con simboli)."""
    kw = re.escape(normalize_text(keyword).strip().lower())
    # (?<!\w) / (?!\w) funzionano anche se la keyword inizia/finisce con un simbolo
    # (es. "C++"), a differenza di \b.
    return re.compile(r"(?<!\w)" + kw + r"(?!\w)", re.IGNORECASE)


def find_matching_keywords(text, keywords):
    """Restituisce le keyword (nella forma originale) presenti in `text` come parole intere."""
    if not text:
        return []
    haystack = normalize_text(text).lower()
    matched = []
    for kw in keywords:
        if not kw or not kw.strip():
            continue
        if keyword_pattern(kw).search(haystack):
            matched.append(kw)
    return matched


def parse_rss_datetime(pub_str, now=None):
    """
    Converte una data RSS (RFC 2822) o ISO 8601 in formato SQLite UTC:
    'YYYY-MM-DD HH:MM:SS'. Se la stringa è vuota o non interpretabile usa `now`.
    """
    dt = None
    if pub_str:
        # 1) RFC 2822 (RSS standard)
        try:
            dt = parsedate_to_datetime(pub_str)
        except Exception:
            dt = None
        # 2) ISO 8601
        if dt is None:
            try:
                dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except Exception:
                dt = None

    if dt is None:
        dt = now or datetime.now(timezone.utc)

    # 3) Senza timezone assumiamo l'ora locale e convertiamo in UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    dt = dt.astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%d %H:%M:%S")


def local_day_bounds_utc(now=None):
    """Ritorna (inizio, fine) del giorno locale corrente espressi come stringhe
    SQLite UTC 'YYYY-MM-DD HH:MM:SS' (fine esclusa)."""
    now = now or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    fmt = "%Y-%m-%d %H:%M:%S"
    return (
        start_local.astimezone(timezone.utc).strftime(fmt),
        end_local.astimezone(timezone.utc).strftime(fmt),
    )


def format_local_datetime(utc_str, fmt="%d/%m/%Y %H:%M"):
    """Converte una data SQLite UTC ('YYYY-MM-DD HH:MM:SS') in ora locale formattata.
    Se la stringa non è interpretabile la restituisce com'è (troncata a 16 char)."""
    if not utc_str:
        return ""
    try:
        dt = datetime.strptime(utc_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return utc_str[:16]
    return dt.astimezone().strftime(fmt)


def slugify(text, max_len=60):
    """'USR Emilia-Romagna – Ufficio VII' -> 'usr-emilia-romagna-ufficio-vii' (per URL leggibili)."""
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "fonte"
