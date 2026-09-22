"""Migrazioni dello schema SQLite, versionate con PRAGMA user_version.

Ogni migrazione riceve la connessione e deve essere idempotente rispetto allo
stato che trova (i DB creati da zero nascono già nella forma finale, quindi le
migrazioni controllano le colonne prima di agire).
"""


def column_exists(conn, table, column):
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def table_exists(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _v1_multi_channel(conn):
    """Da 'utente = telegram_id' a 'utente = users.id' con canali/frequenza.
    - users: telegram_id nullable, nuove colonne email/password/notifiche
    - user_sources: telegram_id -> user_id
    - sources.added_by: telegram_id -> user_id
    - news.source_id (DB molto vecchi)
    """
    if not column_exists(conn, "news", "source_id"):
        conn.execute("ALTER TABLE news ADD COLUMN source_id INTEGER")

    legacy_users = not column_exists(conn, "users", "email")
    if legacy_users:
        conn.executescript("""
            CREATE TABLE users_v1 (
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users_v1 (id, telegram_id, username, keywords, active, created_at)
                SELECT id, telegram_id, username, keywords, COALESCE(active, 1), created_at FROM users;
            DROP TABLE users;
            ALTER TABLE users_v1 RENAME TO users;
        """)

    if table_exists(conn, "user_sources") and column_exists(conn, "user_sources", "telegram_id"):
        conn.executescript("""
            CREATE TABLE user_sources_v1 (
                user_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                follow INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, source_id)
            );
            INSERT OR IGNORE INTO user_sources_v1 (user_id, source_id, follow)
                SELECT u.id, us.source_id, us.follow
                FROM user_sources us JOIN users u ON u.telegram_id = us.telegram_id;
            DROP TABLE user_sources;
            ALTER TABLE user_sources_v1 RENAME TO user_sources;
        """)

    if legacy_users:
        # added_by conteneva il telegram_id: lo rimappiamo su users.id
        conn.execute("""
            UPDATE sources SET added_by = (SELECT id FROM users u WHERE u.telegram_id = sources.added_by)
            WHERE added_by IS NOT NULL
        """)


def _v2_digest_guard(conn):
    """users.last_digest_date (YYYY-MM-DD locale): evita doppi invii del digest nello stesso giorno."""
    if not column_exists(conn, "users", "last_digest_date"):
        conn.execute("ALTER TABLE users ADD COLUMN last_digest_date TEXT")


def _v3_consent(conn):
    """Consenso privacy (versione dell'informativa accettata e quando): registrazione web."""
    for col in ("consent_version TEXT", "consent_at DATETIME"):
        if not column_exists(conn, "users", col.split()[0]):
            conn.execute(f"ALTER TABLE users ADD COLUMN {col}")


def _v4_google(conn):
    """users.google_sub: identificativo stabile dell'account Google (login OAuth)."""
    if not column_exists(conn, "users", "google_sub"):
        conn.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users (google_sub)")


def _v5_source_geo(conn):
    """sources.kind/region/province: catalogo USR/USP per regione e provincia."""
    for col in ("kind TEXT", "region TEXT", "province TEXT"):
        if not column_exists(conn, "sources", col.split()[0]):
            conn.execute(f"ALTER TABLE sources ADD COLUMN {col}")


def _v6_fix_future_dates(conn):
    """Correzione dati: notizie salvate con published_at nel futuro (il parser HTML prendeva
    scadenze/date di eventi dal titolo). Le riportiamo alla data di fetch."""
    conn.execute("UPDATE news SET published_at = fetched_at "
                 "WHERE datetime(published_at) > datetime('now', '+1 day')")


def _v7_drop_web_accounts(conn):
    """Torniamo alla versione "utility": nessun account web, nessuna email.
    Restano gli utenti Telegram; le colonne e le tabelle dell'era account spariscono."""
    conn.executescript("""
        DROP TABLE IF EXISTS email_tokens;
        DROP TABLE IF EXISTS link_codes;
    """)
    if column_exists(conn, "users", "email"):
        conn.executescript("""
            DELETE FROM user_sources WHERE user_id IN (SELECT id FROM users WHERE telegram_id IS NULL);
            DELETE FROM deliveries   WHERE user_id IN (SELECT id FROM users WHERE telegram_id IS NULL);
            UPDATE sources SET added_by = NULL
             WHERE added_by IN (SELECT id FROM users WHERE telegram_id IS NULL);
            DELETE FROM users WHERE telegram_id IS NULL;   -- account creati solo sul sito

            CREATE TABLE users_v7 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                keywords TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                digest_time TEXT,
                last_digest_date TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users_v7 (id, telegram_id, username, keywords, active, digest_time, last_digest_date, created_at)
                SELECT id, telegram_id, username, keywords, active, digest_time, last_digest_date, created_at FROM users;
            DROP TABLE users;
            ALTER TABLE users_v7 RENAME TO users;
        """)


MIGRATIONS = [
    (1, _v1_multi_channel),
    (2, _v2_digest_guard),
    (3, _v3_consent),
    (4, _v4_google),
    (5, _v5_source_geo),
    (6, _v6_fix_future_dates),
    (7, _v7_drop_web_accounts),
]


def get_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def run_migrations(conn):
    """Applica in ordine le migrazioni mancanti. Ritorna la lista delle versioni applicate."""
    current = get_version(conn)
    applied = []
    for version, migrate in MIGRATIONS:
        if current >= version:
            continue
        migrate(conn)
        conn.execute(f"PRAGMA user_version = {int(version)}")
        conn.commit()
        applied.append(version)
        current = version
    return applied
