"""Stato di salute delle fonti e heartbeat dei job schedulati (per il watchdog)."""
from datetime import datetime, timezone

from sfm.db import get_conn


def utcnow_str(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.astimezone()
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --- fonti ----------------------------------------------------------------

def record_source_success(source_id, items, new_items, now=None):
    """Lettura riuscita: azzera i fallimenti; se ci sono notizie nuove aggiorna last_new_item_at."""
    ts = utcnow_str(now)
    conn = get_conn()
    conn.execute("""
        INSERT INTO source_health (source_id, first_seen_at, last_success_at, last_items, consecutive_failures, last_new_item_at)
        VALUES (?, ?, ?, ?, 0, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            last_success_at = excluded.last_success_at,
            last_items = excluded.last_items,
            consecutive_failures = 0,
            last_new_item_at = COALESCE(excluded.last_new_item_at, source_health.last_new_item_at)
    """, (source_id, ts, ts, int(items), ts if new_items else None))
    conn.commit()
    conn.close()


def record_source_failure(source_id, error, now=None):
    ts = utcnow_str(now)
    conn = get_conn()
    conn.execute("""
        INSERT INTO source_health (source_id, first_seen_at, last_error_at, last_error, consecutive_failures)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(source_id) DO UPDATE SET
            last_error_at = excluded.last_error_at,
            last_error = excluded.last_error,
            consecutive_failures = source_health.consecutive_failures + 1
    """, (source_id, ts, ts, str(error)[:500]))
    conn.commit()
    conn.close()


def get_source_health(source_id=None):
    """Un dict per fonte (o la lista di tutti se source_id è None)."""
    conn = get_conn()
    if source_id is None:
        rows = conn.execute("SELECT * FROM source_health").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    row = conn.execute("SELECT * FROM source_health WHERE source_id=?", (source_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_failing_source_ids(min_failures):
    conn = get_conn()
    rows = conn.execute("SELECT source_id FROM source_health WHERE consecutive_failures >= ?", (int(min_failures),)).fetchall()
    conn.close()
    return {r["source_id"] for r in rows}


# --- job ------------------------------------------------------------------

def record_job_start(name, now=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO job_runs (name, started_at) VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET started_at = excluded.started_at
    """, (name, utcnow_str(now)))
    conn.commit()
    conn.close()


def record_job_end(name, ok=True, error=None, now=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO job_runs (name, finished_at, ok, error) VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET finished_at = excluded.finished_at, ok = excluded.ok, error = excluded.error
    """, (name, utcnow_str(now), 1 if ok else 0, (str(error)[:500] if error else None)))
    conn.commit()
    conn.close()


def get_job_runs():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM job_runs").fetchall()
    conn.close()
    return {r["name"]: dict(r) for r in rows}


# --- incidenti aperti (per non ripetere gli avvisi) ------------------------

def get_open_incidents():
    conn = get_conn()
    rows = conn.execute("SELECT key, message, opened_at FROM watchdog_incidents").fetchall()
    conn.close()
    return {r["key"]: dict(r) for r in rows}


def open_incident(key, message, now=None):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO watchdog_incidents (key, message, opened_at) VALUES (?, ?, ?)",
                 (key, message, utcnow_str(now)))
    conn.commit()
    conn.close()


def close_incident(key):
    conn = get_conn()
    conn.execute("DELETE FROM watchdog_incidents WHERE key=?", (key,))
    conn.commit()
    conn.close()
