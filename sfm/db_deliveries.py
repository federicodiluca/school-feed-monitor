"""Log invii (tabella deliveries): dedup multi-canale.
Una notizia va a un utente al più una volta per (canale, tipo)."""
from sfm.db import get_conn

KINDS = ("alert", "digest")


def record_delivery(user_id, news_id, channel, kind):
    """Registra un invio. Ritorna True se è il primo per quella combinazione,
    False se era già stato registrato (→ non reinviare)."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO deliveries (user_id, news_id, channel, kind) VALUES (?, ?, ?, ?)",
        (user_id, news_id, channel, kind),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delivered_news_ids(user_id, channel=None, kind=None, news_ids=None):
    """Insieme dei news_id già inviati all'utente, filtrabile per canale/tipo/lista di id."""
    sql, params = "SELECT news_id FROM deliveries WHERE user_id=?", [user_id]
    if channel is not None:
        sql += " AND channel=?"; params.append(channel)
    if kind is not None:
        sql += " AND kind=?"; params.append(kind)
    if news_ids is not None:
        ids = sorted(set(news_ids))
        if not ids:
            return set()
        sql += f" AND news_id IN ({','.join('?' * len(ids))})"; params += ids
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {r["news_id"] for r in rows}


def cleanup_old_deliveries(days=30):
    """Elimina le righe più vecchie di `days` giorni (le news vengono già pulite prima)."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM deliveries WHERE datetime(sent_at) < datetime('now', ?)", (f"-{int(days)} days",))
    conn.commit()
    conn.close()
    return cur.rowcount
