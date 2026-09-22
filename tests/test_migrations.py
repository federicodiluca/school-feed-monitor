"""Migrazione dei DB creati dalle versioni precedenti (utente = telegram_id)."""
import sqlite3

import sfm.db as db
from sfm.db_deliveries import cleanup_old_deliveries, delivered_news_ids, record_delivery
from sfm.db_sources import get_followed_source_ids, get_followers_map, get_source
from sfm.db_user import get_user, get_user_by_id, get_users, set_digest_time, set_keywords
from sfm.migrations import MIGRATIONS, column_exists, get_version

LATEST = MIGRATIONS[-1][0]

LEGACY_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    keywords TEXT,
    active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,
    source TEXT,
    published_at DATETIME,
    content TEXT,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL DEFAULT 'rss',
    origin TEXT NOT NULL DEFAULT 'config',
    added_by INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    default_follow INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE user_sources (
    telegram_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    follow INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (telegram_id, source_id)
);
"""


def _legacy_db():
    """Ricrea il DB nella forma pre-migrazione con qualche dato."""
    import os
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db.DB_PATH + suffix):
            os.remove(db.DB_PATH + suffix)
    conn = sqlite3.connect(db.DB_PATH)
    conn.executescript(LEGACY_SCHEMA)
    conn.executescript("""
        INSERT INTO users (id, telegram_id, username, keywords, active) VALUES
            (1, 1001, 'alice', 'docenti,ata', 1),
            (2, 2002, 'bob', '', 0);
        INSERT INTO sources (id, name, url, origin, added_by, default_follow) VALUES
            (1, 'Feed Uno', 'https://example.org/uno/feed/', 'config', NULL, 1),
            (2, 'Custom di Bob', 'https://custom.org/', 'user', 2002, 0);
        INSERT INTO user_sources (telegram_id, source_id, follow) VALUES
            (1001, 1, 0), (2002, 2, 1), (9999, 1, 1);
        INSERT INTO news (title, link, source, published_at) VALUES ('old', 'https://x/old', 'Feed Uno', datetime('now'));
    """)
    conn.commit()
    conn.close()


def test_legacy_db_is_migrated_preserving_users_and_follows():
    _legacy_db()
    db.init_db()

    conn = db.get_conn()
    assert get_version(conn) == LATEST
    assert not column_exists(conn, "users", "email")      # v7: via gli account web
    assert column_exists(conn, "users", "last_digest_date")
    assert column_exists(conn, "user_sources", "user_id") and not column_exists(conn, "user_sources", "telegram_id")
    assert column_exists(conn, "news", "source_id")
    assert conn.execute("SELECT COUNT(*) FROM user_sources").fetchone()[0] == 2  # orfano 9999 scartato
    conn.close()

    alice, bob = get_user(1001), get_user(2002)
    assert alice["id"] == 1 and alice["username"] == "alice" and alice["keywords"] == ["docenti", "ata"]
    assert alice["active"] is True and bob["active"] is False
    assert get_followed_source_ids(1) == set()       # alice ha escluso Feed Uno
    assert get_followed_source_ids(2) == {1, 2}      # bob: default + la sua custom
    assert get_source(2)["added_by"] == 2            # added_by rimappato da telegram_id a users.id


def test_init_db_is_idempotent_on_migrated_db():
    _legacy_db()
    db.init_db()
    db.init_db()
    assert get_user(1001)["id"] == 1
    conn = db.get_conn()
    assert get_version(conn) == LATEST
    conn.close()


def test_fresh_db_has_version_and_deliveries_table():
    conn = db.get_conn()
    assert get_version(conn) == LATEST
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='deliveries'").fetchone()
    conn.close()


# --- deliveries -------------------------------------------------------------

def test_record_delivery_dedupes_per_user_news_channel_kind():
    assert record_delivery(1, 10, "telegram", "alert") is True
    assert record_delivery(1, 10, "telegram", "alert") is False
    assert record_delivery(1, 10, "email", "alert") is True
    assert record_delivery(1, 10, "telegram", "digest") is True
    assert record_delivery(2, 10, "telegram", "alert") is True
    assert delivered_news_ids(1) == {10}
    assert delivered_news_ids(1, channel="email", kind="digest") == set()
    assert delivered_news_ids(1, kind="alert", news_ids=[10, 11]) == {10}
    assert delivered_news_ids(1, news_ids=[]) == set()


def test_cleanup_old_deliveries():
    conn = db.get_conn()
    conn.execute("INSERT INTO deliveries (user_id, news_id, channel, kind, sent_at) VALUES (1, 1, 'telegram', 'alert', datetime('now', '-40 days'))")
    conn.execute("INSERT INTO deliveries (user_id, news_id, channel, kind) VALUES (1, 2, 'telegram', 'alert')")
    conn.commit()
    conn.close()
    assert cleanup_old_deliveries(30) == 1
    assert delivered_news_ids(1) == {2}


# --- utenti web -------------------------------------------------------------

def test_env_setting_prefers_new_name_and_falls_back_to_legacy(monkeypatch, capsys):
    from sfm.settings import env_setting
    monkeypatch.delenv("SFM_FOO", raising=False); monkeypatch.delenv("CHECKFEED_FOO", raising=False)
    assert env_setting("FOO", "dflt") == "dflt"
    monkeypatch.setenv("CHECKFEED_FOO", "old")
    assert env_setting("FOO", "dflt") == "old" and "deprecata" in capsys.readouterr().err
    monkeypatch.setenv("SFM_FOO", "new")
    assert env_setting("FOO", "dflt") == "new"


def test_legacy_db_file_is_moved_to_new_default(tmp_path, monkeypatch):
    import sfm.settings as settings
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "checkfeed.db").write_bytes(b"x")
    (tmp_path / "data" / "checkfeed.db-wal").write_bytes(b"y")
    monkeypatch.setattr(settings, "DB_PATH", settings.DEFAULT_DB_PATH)
    assert settings.migrate_legacy_db_file() is True
    assert (tmp_path / "data" / "sfm.db").read_bytes() == b"x" and (tmp_path / "data" / "sfm.db-wal").exists()
    assert not (tmp_path / "data" / "checkfeed.db").exists()
    assert settings.migrate_legacy_db_file() is False   # niente da fare la seconda volta


def test_v7_removes_web_accounts_but_keeps_telegram_users():
    """Un DB della versione "piattaforma" (account web + email) va ripulito senza perdere il bot."""
    import sqlite3
    _legacy_db()
    conn = sqlite3.connect(db.DB_PATH)
    # nella versione "piattaforma" telegram_id era nullable: rifacciamo la tabella com'era allora
    conn.executescript("""
        CREATE TABLE users_web (
            id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE, username TEXT,
            email TEXT, keywords TEXT, active INTEGER DEFAULT 1,
            digest_time TEXT, last_digest_date TEXT, created_at DATETIME
        );
        INSERT INTO users_web (id, telegram_id, username, keywords, active)
            SELECT id, telegram_id, username, keywords, active FROM users;
        DROP TABLE users;
        ALTER TABLE users_web RENAME TO users;
        INSERT INTO users (id, telegram_id, username, keywords, active, email) VALUES (3, NULL, NULL, 'x', 1, 'web@x.it');
        INSERT INTO user_sources (telegram_id, source_id, follow) VALUES (3, 1, 1);
        CREATE TABLE email_tokens (token TEXT PRIMARY KEY, user_id INTEGER, purpose TEXT, expires_at DATETIME);
        CREATE TABLE link_codes (code TEXT PRIMARY KEY, user_id INTEGER, expires_at DATETIME);
    """)
    conn.commit(); conn.close()

    db.init_db()

    conn = db.get_conn()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "email_tokens" not in tables and "link_codes" not in tables and "configs" in tables
    assert not column_exists(conn, "users", "email")
    conn.close()
    assert [u["telegram_id"] for u in get_users(active_only=False)] == [1001, 2002]   # l'utente web sparisce
    assert get_user(1001)["keywords"] == ["docenti", "ata"]
