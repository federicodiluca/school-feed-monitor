"""Utenti del bot Telegram.

Il sito non ha account: gli unici "utenti" sono le chat Telegram che hanno avviato
il bot (identificativo, eventuale username, parole chiave, fonti seguite).
"""
from datetime import datetime

from sfm.db import get_conn

USER_COLUMNS = "id, telegram_id, username, keywords, excluded_keywords, active, digest_time, last_digest_date, created_at"


def _split_keywords(raw):
    return [kw.strip() for kw in (raw or "").split(",") if kw.strip()]


def _row_to_user(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "telegram_id": row["telegram_id"],
        "username": row["username"],
        "keywords": _split_keywords(row["keywords"]),
        "excluded": _split_keywords(row["excluded_keywords"]),
        "active": bool(row["active"]),
        "digest_time": row["digest_time"],
        "last_digest_date": row["last_digest_date"],
        "created_at": row["created_at"],
    }


def _fetch_user(where, params):
    conn = get_conn()
    row = conn.execute(f"SELECT {USER_COLUMNS} FROM users WHERE {where}", params).fetchone()
    conn.close()
    return _row_to_user(row)


def _exec(sql, params):
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    conn.close()
    return cur.rowcount


# --- lettura --------------------------------------------------------------

def get_user(telegram_id):
    """Utente per telegram_id, oppure None se non registrato."""
    return _fetch_user("telegram_id=?", (telegram_id,))


def get_user_by_id(user_id):
    return _fetch_user("id=?", (user_id,))


def get_users(active_only=True):
    conn = get_conn()
    sql = f"SELECT {USER_COLUMNS} FROM users"
    if active_only:
        sql += " WHERE active=1"
    rows = conn.execute(sql + " ORDER BY id").fetchall()
    conn.close()
    return [_row_to_user(r) for r in rows]


def user_id_for_telegram(telegram_id):
    """users.id per un telegram_id, oppure None."""
    user = get_user(telegram_id)
    return user["id"] if user else None


# --- registrazione e stato -------------------------------------------------

def add_user(telegram_id, username=None):
    """Registra un utente Telegram. Ritorna True se creato, False se già esistente
    (in tal caso aggiorna lo username)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if cur.fetchone():
        if username:
            cur.execute("UPDATE users SET username=? WHERE telegram_id=?", (username, telegram_id))
            conn.commit()
        conn.close()
        return False

    cur.execute("""
        INSERT INTO users (telegram_id, username, keywords, active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (telegram_id, username, "", datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True


def activate_user(telegram_id):
    _exec("UPDATE users SET active=1 WHERE telegram_id=?", (telegram_id,))


def deactivate_user(telegram_id):
    _exec("UPDATE users SET active=0 WHERE telegram_id=?", (telegram_id,))


def delete_user(user_id):
    """Cancellazione definitiva: utente, preferenze fonti e log invii."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM deliveries WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM user_sources WHERE user_id=?", (user_id,))
    cur.execute("UPDATE sources SET added_by=NULL WHERE added_by=?", (user_id,))
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def export_user_data(user_id):
    """Tutti i dati dell'utente in forma leggibile (per il comando /dati del bot)."""
    user = get_user_by_id(user_id)
    if not user:
        return None
    conn = get_conn()
    follows = [dict(r) for r in conn.execute(
        "SELECT s.id AS source_id, s.name, s.url, us.follow FROM user_sources us JOIN sources s ON s.id=us.source_id WHERE us.user_id=?",
        (user_id,))]
    conn.close()
    return {"user": user, "source_preferences": follows}


# --- parole chiave e orario del riepilogo ----------------------------------

def _clean_keywords(keywords):
    return [kw.strip() for kw in keywords if kw and kw.strip()]


def set_keywords(user_id, keywords):
    _exec("UPDATE users SET keywords=? WHERE id=?", (",".join(_clean_keywords(keywords)), user_id))


def set_excluded(user_id, words):
    _exec("UPDATE users SET excluded_keywords=? WHERE id=?", (",".join(_clean_keywords(words)), user_id))


def update_keywords(telegram_id, keywords):
    _exec("UPDATE users SET keywords=? WHERE telegram_id=?", (",".join(_clean_keywords(keywords)), telegram_id))


def set_digest_time(user_id, digest_time):
    """'HH:MM' oppure '' / None per usare l'orario globale."""
    _exec("UPDATE users SET digest_time=? WHERE id=?", (digest_time or None, user_id))


def set_last_digest_date(user_id, day):
    """Segna che il riepilogo del giorno `day` ('YYYY-MM-DD') è stato inviato."""
    _exec("UPDATE users SET last_digest_date=? WHERE id=?", (day, user_id))
