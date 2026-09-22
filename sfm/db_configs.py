"""Configurazioni create sul sito e applicate al bot con /start CODICE.

Il sito non conosce chi le crea: salva solo l'elenco di fonti e parole chiave scelte,
con una scadenza breve. Il collegamento a una persona avviene solo su Telegram, quando
il codice viene usato.
"""
import json
import secrets

from sfm.db import get_conn

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza 0/O e 1/I
CODE_LENGTH = 8
TTL_HOURS = 24


def new_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def save_config(source_ids, keywords, code=None):
    """Salva la configurazione e ritorna il codice (valido TTL_HOURS ore)."""
    code = (code or new_code()).upper()
    payload = json.dumps({"sources": sorted(set(int(s) for s in source_ids)),
                          "keywords": [k for k in keywords if k]}, ensure_ascii=False)
    conn = get_conn()
    conn.execute("DELETE FROM configs WHERE datetime(expires_at) < datetime('now')")
    conn.execute("INSERT OR REPLACE INTO configs (code, payload, expires_at) VALUES (?, ?, datetime('now', ?))",
                 (code, payload, f"+{TTL_HOURS} hours"))
    conn.commit()
    conn.close()
    return code


def load_config(code, consume=True):
    """Ritorna {"sources": [...], "keywords": [...]} oppure None se scaduto/inesistente."""
    code = (code or "").strip().upper()
    conn = get_conn()
    row = conn.execute("SELECT payload FROM configs WHERE code=? AND datetime(expires_at) >= datetime('now')",
                       (code,)).fetchone()
    if row and consume:
        conn.execute("DELETE FROM configs WHERE code=?", (code,))
        conn.commit()
    conn.close()
    return json.loads(row["payload"]) if row else None


def cleanup_configs():
    conn = get_conn()
    cur = conn.execute("DELETE FROM configs WHERE datetime(expires_at) < datetime('now')")
    conn.commit()
    conn.close()
    return cur.rowcount
