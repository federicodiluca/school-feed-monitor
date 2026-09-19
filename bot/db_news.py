from bot.db import get_conn
from bot.logger import log
from bot.utils import local_day_bounds_utc, parse_rss_datetime

MAX_CONTENT_LEN = 20000
FUTURE_TOLERANCE_HOURS = 24


def clamp_future(published_utc, now=None):
    """Una data di pubblicazione nel futuro (scadenze scambiate per date, orologi sballati)
    viene riportata a 'adesso': altrimenti resterebbe in cima all'elenco per giorni."""
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.strptime(published_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return published_utc
    if dt > now + timedelta(hours=FUTURE_TOLERANCE_HOURS):
        return now.strftime("%Y-%m-%d %H:%M:%S")
    return published_utc


def _source_filter(source_ids):
    """Ritorna (clausola SQL, parametri) per filtrare su un insieme di fonti.
    None = nessun filtro; insieme vuoto = nessun risultato."""
    if source_ids is None:
        return "", []
    ids = sorted(set(source_ids))
    if not ids:
        return " AND 0", []
    return f" AND source_id IN ({','.join('?' * len(ids))})", ids


def add_news(title, link, source, published_at, content="", source_id=None):
    """Inserisce una news. Ritorna l'id se è nuova, None se già presente o in errore."""
    content = content or ""
    if len(content) > MAX_CONTENT_LEN:
        content = content[:MAX_CONTENT_LEN]

    conn = get_conn()
    cur = conn.cursor()
    try:
        published_at = clamp_future(parse_rss_datetime(published_at))  # formato SQLite UTC standard
        cur.execute("""
        INSERT OR IGNORE INTO news (title, link, source, published_at, content, source_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (title, link, source, published_at, content, source_id))
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None  # None se ignorata (già presente)
    except Exception as e:
        log(f"❌ Errore inserimento news: {e}")
        return None
    finally:
        conn.close()


def get_recent_news(limit=10, source_ids=None):
    """Ultime news. source_ids=None → tutte; altrimenti solo quelle fonti."""
    where, params = _source_filter(source_ids)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, title, link, source, source_id, published_at, content
        FROM news
        WHERE 1=1{where}
        ORDER BY datetime(published_at) DESC, id DESC
        LIMIT ?
    """, params + [int(limit)])
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_news(now=None, source_ids=None):
    """Restituisce le news pubblicate nel giorno locale corrente
    (published_at è in UTC: i confini del giorno vengono convertiti).
    source_ids=None → tutte le fonti; altrimenti solo quelle indicate."""
    start_utc, end_utc = local_day_bounds_utc(now)
    where, params = _source_filter(source_ids)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, title, link, source, source_id, published_at, content
        FROM news
        WHERE datetime(published_at) >= datetime(?) AND datetime(published_at) < datetime(?){where}
        ORDER BY datetime(published_at) DESC, id DESC
    """, [start_utc, end_utc] + params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_news(source_ids=None, query=None, days=None, page=1, per_page=20):
    """Ricerca paginata: filtro per fonti (None = tutte), testo (titolo/contenuto, case-insensitive)
    e finestra temporale in giorni (su published_at). Ritorna (righe, totale)."""
    where, params = _source_filter(source_ids)
    if query:
        like = f"%{query.strip()}%"
        where += " AND (title LIKE ? OR content LIKE ?)"
        params += [like, like]
    if days:
        where += " AND datetime(published_at) >= datetime('now', ?)"
        params.append(f"-{int(days)} days")
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM news WHERE 1=1{where}", params).fetchone()[0]
    rows = conn.execute(f"""
        SELECT id, title, link, source, source_id, published_at, content
        FROM news
        WHERE 1=1{where}
        ORDER BY datetime(published_at) DESC, id DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page]).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def cleanup_old_news(days=7):
    """Elimina le news con fetched_at più vecchio di `days` giorni. Ritorna il numero di righe eliminate."""
    conn = get_conn()
    cur = conn.cursor()
    # fetched_at è in UTC (CURRENT_TIMESTAMP): confrontiamo con datetime('now'), anch'esso UTC
    cur.execute(
        "DELETE FROM news WHERE datetime(fetched_at) < datetime('now', ?)",
        (f"-{int(days)} days",),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    log(f"🧽 Pulite {deleted} notizie più vecchie di {days} giorni.")
    return deleted
