"""Lettura delle fonti: feed RSS/Atom, autodiscovery del feed da una pagina
e scraping generico delle pagine HTML "lista notizie" (es. siti Liferay del MIM
che non espongono RSS).

Ogni funzione di parsing ritorna una lista di entry normalizzate:
    {"title": str, "link": str, "published": str, "content": str}
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from bot.utils import strip_html

USER_AGENT = "Mozilla/5.0 (compatible; CheckFeed-Bot/1.0)"
FETCH_TIMEOUT = 20
MIN_HTML_ITEMS = 3  # sotto questa soglia una pagina HTML non è considerata una lista di notizie

SOURCE_TYPES = ("rss", "html")

_IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}
_RE_IT_DATE = re.compile(r"\b(\d{1,2})\s+([a-zà]{3,9})\.?\s+(\d{4})\b", re.I)
_RE_NUM_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_RE_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?")


class SourceError(Exception):
    """Fonte non leggibile (rete, formato, nessuna notizia trovata)."""


# --- rete -----------------------------------------------------------------

def fetch_url(url):
    """Scarica una URL. Ritorna (bytes, content_type). Solleva SourceError."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SourceError(f"impossibile scaricare {url}: {e}") from e
    return resp.content, resp.headers.get("content-type", "")


# --- date -----------------------------------------------------------------

def parse_italian_date(text):
    """Cerca una data in italiano ('11 settembre 2026'), numerica ('11/09/2026')
    o ISO nel testo. Ritorna una stringa ISO 'YYYY-MM-DDTHH:MM:SS' oppure None."""
    if not text:
        return None
    m = _RE_ISO_DATE.search(text)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0)).isoformat()
        except ValueError:
            pass
    m = _RE_IT_DATE.search(text)
    if m:
        d, month_name, y = m.groups()
        month = _IT_MONTHS.get(month_name.lower())
        if month:
            try:
                return datetime(int(y), month, int(d)).isoformat()
            except ValueError:
                pass
    m = _RE_NUM_DATE.search(text)
    if m:
        d, mo, y = m.groups()
        try:
            return datetime(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass
    return None


# --- RSS / Atom -----------------------------------------------------------

def feed_entry_to_item(entry):
    """Normalizza una entry feedparser. Ritorna None se manca il link."""
    link = (entry.get("link") or "").strip()
    if not link:
        return None
    title = strip_html(entry.get("title") or "").strip() or "(senza titolo)"
    published = entry.get("published") or entry.get("updated") or datetime.now(timezone.utc).isoformat()

    content_list = entry.get("content") or []
    content_val = content_list[0].get("value", "") if content_list else ""
    text_content = content_val or entry.get("description", "") or entry.get("summary", "") or ""
    return {"title": title, "link": link, "published": published, "content": text_content}


def parse_feed(data):
    """Parsa bytes/str di un feed. Ritorna (items, feed_title). items vuota se non è un feed."""
    parsed = feedparser.parse(data)
    items = []
    for entry in parsed.entries:
        item = feed_entry_to_item(entry)
        if item:
            items.append(item)
    title = (parsed.feed.get("title") or "").strip() if getattr(parsed, "feed", None) else ""
    return items, title


def discover_feed_url(html_data, base_url):
    """Cerca <link rel="alternate" type="application/rss+xml|atom+xml"> nella pagina."""
    soup = BeautifulSoup(html_data, "html.parser")
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        typ = (link.get("type") or "").lower()
        if "alternate" in rel and typ in ("application/rss+xml", "application/atom+xml"):
            title = (link.get("title") or "").lower()
            if "comment" in title or "commenti" in title:
                continue  # feed dei commenti di WordPress: non ci interessa
            return urljoin(base_url, link["href"])
    return None


# --- HTML scraping --------------------------------------------------------

_BLOCK_TAGS = ("article", "li")


def _link_of_heading(h):
    """Link di un titolo: <h3><a>…</a></h3> oppure <a><h3>…</h3></a> (link che avvolge il titolo)."""
    a = h.find("a", href=True)
    if a and a.get_text(strip=True):
        return a
    outer = h.find_parent("a", href=True)
    if outer is not None and h.get_text(strip=True):
        return outer
    return None


def _heading_link(node):
    for h in node.find_all(["h1", "h2", "h3", "h4"]):
        a = _link_of_heading(h)
        if a is not None:
            return a
    return None


def _block_of_heading(h):
    """Contenitore della notizia: il più vicino <article>/<li>, altrimenti il genitore del titolo
    (o del link che lo avvolge)."""
    container = h.find_parent(_BLOCK_TAGS)
    if container is not None:
        return container
    outer = h.find_parent("a", href=True)
    top = outer if outer is not None else h
    return top.parent if top.parent is not None else top


def _candidate_blocks(soup):
    articles = soup.find_all("article")
    if articles:
        return articles
    # fallback: contenitori di un titolo h2/h3 con link (dentro o attorno al titolo)
    blocks, seen = [], set()
    for h in soup.find_all(["h2", "h3"]):
        if _link_of_heading(h) is None:
            continue
        block = _block_of_heading(h)
        if id(block) not in seen:
            seen.add(id(block))
            blocks.append(block)
    return blocks


MIN_TEASER_LEN = 40
_DATE_CLASS_HINTS = ("date", "data", "time", "pubbl", "revision", "revis")
FUTURE_TOLERANCE_DAYS = 1  # le date di pubblicazione non stanno nel futuro (fuso/orologi a parte)


def _not_future(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt > datetime.now() + timedelta(days=FUTURE_TOLERANCE_DAYS):
        return None  # scadenza/evento futuro, non data di pubblicazione
    return iso


def _block_date(block, heading):
    """Data di pubblicazione di un blocco notizia. In ordine: <time>, elementi con classe
    "date/data/...", poi il testo del blocco SENZA il titolo (i titoli contengono spesso
    scadenze o date di eventi). Le date future vengono scartate. None se non trovata."""
    time_tag = block.find("time")
    if time_tag is not None:
        found = _not_future(parse_italian_date(time_tag.get("datetime") or time_tag.get_text(" ", strip=True)))
        if found:
            return found
    for node in block.find_all(True, class_=True):
        classes = " ".join(node.get("class") or []).lower()
        if any(h in classes for h in _DATE_CLASS_HINTS) and node is not heading and heading not in node.parents:
            found = _not_future(parse_italian_date(node.get_text(" ", strip=True)))
            if found:
                return found
    title_text = heading.get_text(" ", strip=True) if heading is not None else ""
    text = block.get_text(" ", strip=True)
    if title_text:
        text = text.replace(title_text, " ")
    return _not_future(parse_italian_date(text))


def _teaser_text(block, title):
    """Senza <p>: il testo più lungo tra i <div>/<span> "foglia" del blocco (teaser, sommario),
    escludendo titolo, date e frammenti brevi (tag, categorie)."""
    best = ""
    for node in block.find_all(["div", "span"]):
        if node.find(["div", "span", "p", "h1", "h2", "h3", "h4"]):
            continue  # non è una foglia
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(text) < MIN_TEASER_LEN or text == title or title in text:
            continue
        if len(text) > len(best):
            best = text
    return best[:600]


def parse_html_articles(html_data, base_url):
    """Estrae le notizie da una pagina HTML "lista": per ogni blocco (article, o
    contenitore di h2/h3) prende titolo+link dal titolo, la data dal testo e i
    paragrafi come contenuto. Ritorna (items, page_title)."""
    soup = BeautifulSoup(html_data, "html.parser")
    page_title = soup.title.get_text(strip=True) if soup.title else ""
    page_host = urlparse(base_url).netloc

    items, seen = [], set()
    for block in _candidate_blocks(soup):
        a = _heading_link(block)
        if a is None:
            continue
        heading = a.find(["h1", "h2", "h3", "h4"]) or a  # titolo = testo del heading, non dell'intero link
        link = urljoin(base_url, a["href"].strip())
        if not link.startswith(("http://", "https://")) or link in seen:
            continue
        if urlparse(link).netloc != page_host:
            continue  # link esterni: menu, social, ecc.
        title = heading.get_text(" ", strip=True)
        if len(title) < 10:
            continue
        seen.add(link)

        published = _block_date(block, heading)

        paragraphs = []
        for p in block.find_all("p"):
            text = p.get_text(" ", strip=True)
            links_text = " ".join(a.get_text(" ", strip=True) for a in p.find_all("a"))
            if not text or text == title or text == links_text:
                continue  # vuoto, titolo ripetuto o paragrafo fatto solo di link (tag/categorie)
            paragraphs.append(text)
        content = " ".join(paragraphs)
        if not content:
            content = _teaser_text(block, title)

        items.append({"title": title, "link": link, "published": published or "", "content": content})
    return items, page_title


# --- rilevamento ----------------------------------------------------------

def _looks_like_html(data, content_type):
    if "html" in (content_type or "").lower():
        return True
    head = data[:2048].lstrip().lower()
    return head.startswith(b"<!doctype html") or b"<html" in head


def detect_source(url):
    """Capisce come leggere una URL. Ritorna un dict:
        {"type": "rss"|"html", "url": <url effettiva da usare>, "name": <nome suggerito>,
         "items": [...]}
    Solleva SourceError se non si riesce a estrarre notizie in nessun modo."""
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    data, content_type = fetch_url(url)

    # 1) È già un feed?
    items, feed_title = parse_feed(data)
    if items:
        return {"type": "rss", "url": url, "name": feed_title or urlparse(url).netloc, "items": items}

    if not _looks_like_html(data, content_type):
        raise SourceError("la URL non è un feed RSS/Atom e non è una pagina HTML")

    # 2) La pagina dichiara un feed?
    feed_url = discover_feed_url(data, url)
    if feed_url and feed_url != url:
        try:
            feed_data, _ = fetch_url(feed_url)
            items, feed_title = parse_feed(feed_data)
            if items:
                return {"type": "rss", "url": feed_url, "name": feed_title or urlparse(url).netloc, "items": items}
        except SourceError:
            pass

    # 3) Scraping della pagina
    items, page_title = parse_html_articles(data, url)
    if len(items) >= MIN_HTML_ITEMS:
        return {"type": "html", "url": url, "name": page_title or urlparse(url).netloc, "items": items}

    raise SourceError(
        "nessun feed RSS trovato e la pagina non sembra una lista di notizie "
        f"(trovati {len(items)} elementi, minimo {MIN_HTML_ITEMS})"
    )


def read_source(source):
    """Legge una fonte già registrata ({'url','type'}). Ritorna la lista di item.
    Solleva SourceError se irraggiungibile o senza contenuti."""
    data, _ = fetch_url(source["url"])
    if source["type"] == "html":
        items, _ = parse_html_articles(data, source["url"])
    else:
        items, _ = parse_feed(data)
    if not items:
        raise SourceError("nessuna notizia trovata")
    return items
