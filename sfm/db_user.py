"""Utenti. La chiave interna è users.id; telegram_id ed email sono identità
opzionali (un utente può avere entrambe). Le funzioni con parametro telegram_id
sono l'API usata dai comandi Telegram; quelle con user_id servono al layer web
e al core."""
from datetime import datetime
from sfm.db import get_conn

ALERT_MODES = ("instant", "digest")   # instant = alert a ogni fetch; digest = solo nel report
USER_COLUMNS = ("id, telegram_id, username, email, email_verified, keywords, active, "
                "notify_telegram, notify_email, alert_mode, digest_time, last_digest_date, consent_version, consent_at, google_sub, created_at")


def _split_keywords(raw):
    return [kw.strip() for kw in (raw or "").split(",") if kw.strip()]


def _row_to_user(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "telegram_id": row["telegram_id"],
        "username": row["username"],
        "email": row["email"],
        "email_verified": bool(row["email_verified"]),
        "keywords": _split_keywords(row["keywords"]),
        "active": bool(row["active"]),
        "notify_telegram": bool(row["notify_telegram"]),
        "notify_email": bool(row["notify_email"]),
        "alert_mode": row["alert_mode"] or "instant",
        "digest_time": row["digest_time"],
        "last_digest_date": row["last_digest_date"],
        "consent_version": row["consent_version"],
        "consent_at": row["consent_at"],
        "google_sub": row["google_sub"],
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


def get_user_by_email(email):
    return _fetch_user("email=?", ((email or "").strip().lower(),))


def get_user_by_google_sub(sub):
    return _fetch_user("google_sub=?", (sub,)) if sub else None


def set_google_sub(user_id, sub):
    _exec("UPDATE users SET google_sub=? WHERE id=?", (sub, user_id))


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


# --- registrazione --------------------------------------------------------

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


def create_web_user(email, password_hash, alert_mode="digest", consent_version=None):
    """Registra un utente dal web. Ritorna l'utente creato, o None se l'email è già usata.
    Default: report giornaliero via email, nessun alert immediato.
    consent_version: versione dell'informativa privacy accettata (registrata con timestamp)."""
    email = (email or "").strip().lower()
    if not email or alert_mode not in ALERT_MODES:
        raise ValueError("email o alert_mode non validi")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE email=?", (email,))
    if cur.fetchone():
        conn.close()
        return None
    now = datetime.now().isoformat()
    cur.execute("""
        INSERT INTO users (email, password_hash, keywords, active, notify_telegram, notify_email, alert_mode,
                           consent_version, consent_at, created_at)
        VALUES (?, ?, '', 1, 0, 1, ?, ?, ?, ?)
    """, (email, password_hash, alert_mode, consent_version, now if consent_version else None, now))
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)


def link_telegram(user_id, telegram_id, username=None):
    """Collega un account Telegram a un utente (es. registrato dal web).
    Ritorna False se quel telegram_id appartiene già a un altro utente."""
    other = get_user(telegram_id)
    if other and other["id"] != user_id:
        return False
    _exec("UPDATE users SET telegram_id=?, username=COALESCE(?, username), notify_telegram=1 WHERE id=?",
          (telegram_id, username, user_id))
    return True


def unlink_telegram(user_id):
    _exec("UPDATE users SET telegram_id=NULL, username=NULL, notify_telegram=0 WHERE id=?", (user_id,))


def merge_telegram_user(user_id, telegram_id):
    """Collega a `user_id` una chat Telegram che oggi appartiene a un utente "solo Telegram"
    (senza email): le sue preferenze (keyword, fonti, log invii) confluiscono nell'account web
    e il vecchio utente viene eliminato. Ritorna False se l'altro utente ha un'email (è un
    account distinto: non si fonde in automatico)."""
    other = get_user(telegram_id)
    if not other:
        return link_telegram(user_id, telegram_id)
    if other["id"] == user_id:
        return True
    if other.get("email"):
        return False
    target = get_user_by_id(user_id)
    keywords = list(target["keywords"])
    keywords += [k for k in other["keywords"] if k.lower() not in {x.lower() for x in keywords}]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO user_sources (user_id, source_id, follow) "
                "SELECT ?, source_id, follow FROM user_sources WHERE user_id=?", (user_id, other["id"]))
    cur.execute("DELETE FROM user_sources WHERE user_id=?", (other["id"],))
    cur.execute("UPDATE OR IGNORE deliveries SET user_id=? WHERE user_id=?", (user_id, other["id"]))
    cur.execute("DELETE FROM deliveries WHERE user_id=?", (other["id"],))
    cur.execute("UPDATE sources SET added_by=? WHERE added_by=?", (user_id, other["id"]))
    cur.execute("DELETE FROM users WHERE id=?", (other["id"],))
    cur.execute("UPDATE users SET telegram_id=?, username=?, notify_telegram=1, keywords=? WHERE id=?",
                (telegram_id, other["username"], ",".join(keywords), user_id))
    conn.commit()
    conn.close()
    return True


# --- codici di collegamento Telegram ---------------------------------------

LINK_CODE_TTL_MINUTES = 15


def create_link_code(user_id, code):
    """Registra un codice usa-e-getta (uno solo attivo per utente)."""
    conn = get_conn()
    conn.execute("DELETE FROM link_codes WHERE user_id=? OR datetime(expires_at) < datetime('now')", (user_id,))
    conn.execute("INSERT INTO link_codes (code, user_id, expires_at) VALUES (?, ?, datetime('now', ?))",
                 (code, user_id, f"+{LINK_CODE_TTL_MINUTES} minutes"))
    conn.commit()
    conn.close()


def consume_link_code(code):
    """Ritorna lo user_id del codice (e lo cancella), oppure None se inesistente o scaduto."""
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM link_codes WHERE code=? AND datetime(expires_at) >= datetime('now')",
                       ((code or "").strip().upper(),)).fetchone()
    conn.execute("DELETE FROM link_codes WHERE code=? OR datetime(expires_at) < datetime('now')", ((code or "").strip().upper(),))
    conn.commit()
    conn.close()
    return row["user_id"] if row else None


# --- token email (verifica indirizzo) ---------------------------------------

EMAIL_TOKEN_TTL_HOURS = {"verify": 48, "reset": 1}
EMAIL_TOKEN_RESEND_SECONDS = 60


def create_email_token(user_id, token, purpose="verify"):
    """Registra un token (uno solo attivo per utente e scopo). Ritorna False se ne è stato
    creato uno da meno di EMAIL_TOKEN_RESEND_SECONDS (anti-spam sul reinvio)."""
    conn = get_conn()
    recent = conn.execute(
        "SELECT 1 FROM email_tokens WHERE user_id=? AND purpose=? AND datetime(created_at) > datetime('now', ?)",
        (user_id, purpose, f"-{EMAIL_TOKEN_RESEND_SECONDS} seconds")).fetchone()
    if recent:
        conn.close()
        return False
    conn.execute("DELETE FROM email_tokens WHERE (user_id=? AND purpose=?) OR datetime(expires_at) < datetime('now')",
                 (user_id, purpose))
    conn.execute("INSERT INTO email_tokens (token, user_id, purpose, expires_at) VALUES (?, ?, ?, datetime('now', ?))",
                 (token, user_id, purpose, f"+{EMAIL_TOKEN_TTL_HOURS.get(purpose, 48)} hours"))
    conn.commit()
    conn.close()
    return True


def consume_email_token(token, purpose="verify"):
    """Ritorna lo user_id del token valido (e lo cancella), oppure None."""
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM email_tokens WHERE token=? AND purpose=? AND datetime(expires_at) >= datetime('now')",
                       (token or "", purpose)).fetchone()
    conn.execute("DELETE FROM email_tokens WHERE token=? OR datetime(expires_at) < datetime('now')", (token or "",))
    conn.commit()
    conn.close()
    return row["user_id"] if row else None


# --- stato / preferenze ---------------------------------------------------

def set_active(user_id, active):
    _exec("UPDATE users SET active=? WHERE id=?", (1 if active else 0, user_id))


def activate_user(telegram_id):
    _exec("UPDATE users SET active=1 WHERE telegram_id=?", (telegram_id,))


def deactivate_user(telegram_id):
    _exec("UPDATE users SET active=0 WHERE telegram_id=?", (telegram_id,))


def _clean_keywords(keywords):
    return [kw.strip() for kw in keywords if kw and kw.strip()]


def set_keywords(user_id, keywords):
    _exec("UPDATE users SET keywords=? WHERE id=?", (",".join(_clean_keywords(keywords)), user_id))


def update_keywords(telegram_id, keywords):
    _exec("UPDATE users SET keywords=? WHERE telegram_id=?", (",".join(_clean_keywords(keywords)), telegram_id))


def set_preferences(user_id, notify_telegram=None, notify_email=None, alert_mode=None, digest_time=None):
    """Aggiorna solo i campi passati (non None). digest_time: 'HH:MM' o '' per usare il default globale."""
    fields, params = [], []
    if notify_telegram is not None:
        fields.append("notify_telegram=?"); params.append(1 if notify_telegram else 0)
    if notify_email is not None:
        fields.append("notify_email=?"); params.append(1 if notify_email else 0)
    if alert_mode is not None:
        if alert_mode not in ALERT_MODES:
            raise ValueError(f"alert_mode non valido: {alert_mode}")
        fields.append("alert_mode=?"); params.append(alert_mode)
    if digest_time is not None:
        fields.append("digest_time=?"); params.append(digest_time or None)
    if not fields:
        return
    _exec(f"UPDATE users SET {', '.join(fields)} WHERE id=?", params + [user_id])


def set_last_digest_date(user_id, day):
    """Segna che il digest del giorno `day` ('YYYY-MM-DD') è stato inviato all'utente."""
    _exec("UPDATE users SET last_digest_date=? WHERE id=?", (day, user_id))


def set_password_hash(user_id, password_hash):
    _exec("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))


def get_password_hash(user_id):
    conn = get_conn()
    row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row["password_hash"] if row else None


def set_email_verified(user_id, verified=True):
    _exec("UPDATE users SET email_verified=? WHERE id=?", (1 if verified else 0, user_id))


# --- GDPR: consenso, export, cancellazione ---------------------------------

def set_consent(user_id, version):
    _exec("UPDATE users SET consent_version=?, consent_at=? WHERE id=?", (version, datetime.now().isoformat(), user_id))


def revoke_consent(user_id):
    """Revoca del consenso: niente più invii (active=0) e consenso azzerato. I dati restano
    finché l'utente non cancella l'account (o riacconsente)."""
    _exec("UPDATE users SET consent_version=NULL, consent_at=NULL, active=0 WHERE id=?", (user_id,))


def delete_user(user_id):
    """Cancellazione definitiva (diritto all'oblio): utente, preferenze fonti e log invii.
    Le fonti aggiunte dall'utente restano (sono dati pubblici) ma senza riferimento a lui."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM deliveries WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM email_tokens WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM link_codes WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM user_sources WHERE user_id=?", (user_id,))
    cur.execute("UPDATE sources SET added_by=NULL WHERE added_by=?", (user_id,))
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def export_user_data(user_id):
    """Tutti i dati personali dell'utente in forma leggibile (portabilità)."""
    user = get_user_by_id(user_id)
    if not user:
        return None
    conn = get_conn()
    follows = [dict(r) for r in conn.execute(
        "SELECT s.id AS source_id, s.name, s.url, us.follow FROM user_sources us JOIN sources s ON s.id=us.source_id WHERE us.user_id=?",
        (user_id,))]
    deliveries = [dict(r) for r in conn.execute(
        "SELECT news_id, channel, kind, sent_at FROM deliveries WHERE user_id=? ORDER BY sent_at", (user_id,))]
    conn.close()
    return {"user": user, "source_preferences": follows, "deliveries": deliveries}
