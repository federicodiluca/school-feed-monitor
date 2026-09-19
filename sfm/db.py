import os
import sqlite3

from sfm.migrations import run_migrations
from sfm.settings import DB_PATH, migrate_legacy_db_file  # SFM_DB_PATH (o CHECKFEED_DB_PATH, deprecata)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# Schema "finale": i DB creati da zero nascono così; quelli vecchi vengono
# portati a questa forma da sfm/migrations.py.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    email TEXT UNIQUE,
    password_hash TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    keywords TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    notify_telegram INTEGER NOT NULL DEFAULT 1,
    notify_email INTEGER NOT NULL DEFAULT 0,
    alert_mode TEXT NOT NULL DEFAULT 'instant',
    digest_time TEXT,
    last_digest_date TEXT,
    consent_version TEXT,
    consent_at DATETIME,
    google_sub TEXT UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,
    source TEXT,
    published_at DATETIME,
    content TEXT,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_id INTEGER
);

-- Fonti: da config.json (origin='config') o aggiunte dagli utenti (origin='user').
-- type: 'rss' (feed) oppure 'html' (pagina scrapata).
-- default_follow: 1 = seguita da tutti salvo esclusione, 0 = opt-in.
-- added_by: users.id di chi l'ha aggiunta (solo origin='user').
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL DEFAULT 'rss',
    origin TEXT NOT NULL DEFAULT 'config',
    added_by INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    default_follow INTEGER NOT NULL DEFAULT 1,
    kind TEXT,          -- 'usr' | 'usp' | 'mim' | 'other'
    region TEXT,        -- es. 'Emilia-Romagna'
    province TEXT,      -- es. 'Bologna' (solo USP)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Override per utente: follow=1 segue, follow=0 esclude. Assente = default della fonte.
CREATE TABLE IF NOT EXISTS user_sources (
    user_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    follow INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, source_id)
);

-- Log invii: una riga per (utente, notizia, canale, tipo). Serve al dedup
-- multi-canale: alert immediati e digest non ripropongono la stessa notizia.
-- kind: 'alert' | 'digest'. channel: 'telegram' | 'email' | ...
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    news_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    kind TEXT NOT NULL,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, news_id, channel, kind)
);
CREATE INDEX IF NOT EXISTS idx_deliveries_news ON deliveries (news_id);

-- Salute delle fonti (aggiornata a ogni lettura) e heartbeat dei job: usati dal watchdog.
CREATE TABLE IF NOT EXISTS source_health (
    source_id INTEGER PRIMARY KEY,
    first_seen_at DATETIME,
    last_success_at DATETIME,
    last_error_at DATETIME,
    last_error TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_items INTEGER,
    last_new_item_at DATETIME
);

CREATE TABLE IF NOT EXISTS job_runs (
    name TEXT PRIMARY KEY,
    started_at DATETIME,
    finished_at DATETIME,
    ok INTEGER,
    error TEXT
);

-- Codici usa-e-getta per collegare un account web a una chat Telegram (/link CODICE).
CREATE TABLE IF NOT EXISTS link_codes (
    code TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at DATETIME NOT NULL
);

-- Token usa-e-getta inviati via email (verifica indirizzo, in futuro reset password).
CREATE TABLE IF NOT EXISTS email_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL
);

-- Incidenti aperti dal watchdog: un avviso all'apertura, uno alla chiusura.
CREATE TABLE IF NOT EXISTS watchdog_incidents (
    key TEXT PRIMARY KEY,
    message TEXT,
    opened_at DATETIME
);
"""


def init_db():
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    migrate_legacy_db_file()  # data/checkfeed.db -> data/sfm.db, una volta sola

    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")  # letture/scritture concorrenti (bot + web)
    conn.executescript(SCHEMA)
    run_migrations(conn)
    conn.commit()
    conn.close()
