from datetime import datetime, timedelta, timezone

import pytest

import sfm.news_fetcher as news_fetcher
import sfm.telegram_commands as tc
import sfm.watchdog as watchdog
from sfm.db_health import (
    get_job_runs,
    get_open_incidents,
    get_source_health,
    record_job_end,
    record_job_start,
    record_source_failure,
    record_source_success,
)
from sfm.db_user import add_user
from tests.fixtures import rss

UNO = "https://example.org/uno/feed/"
DUE = "https://example.org/due/feed/"
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def admin_env(monkeypatch):
    for k in ("ADMIN_TELEGRAM_ID", "ADMIN_EMAIL", "WATCHDOG_SOURCE_FAILURES", "WATCHDOG_SOURCE_SILENCE_HOURS",
              "WATCHDOG_JOB_STALE_MINUTES", "HEALTHCHECK_PING_URL", "EMAIL_BACKEND", "EMAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "999")
    return monkeypatch


# --- salute delle fonti aggiornata dal fetch ------------------------------------

def test_fetch_records_success_and_failures(fake_sources, sent_messages):
    fake_sources[UNO] = rss([{"title": "a", "link": "https://x/1"}])
    news_fetcher.fetch_news()                       # UNO ok (1 nuova), DUE → SourceError
    h = {x["source_id"]: x for x in get_source_health()}
    assert h[1]["consecutive_failures"] == 0 and h[1]["last_items"] == 1 and h[1]["last_new_item_at"]
    assert h[2]["consecutive_failures"] == 1 and "404" in h[2]["last_error"] and h[2]["last_success_at"] is None

    news_fetcher.fetch_news()                       # UNO ok ma niente di nuovo, DUE fallisce ancora
    h = {x["source_id"]: x for x in get_source_health()}
    assert h[1]["last_new_item_at"] == h[1]["last_new_item_at"] and h[1]["consecutive_failures"] == 0
    assert h[2]["consecutive_failures"] == 2

    fake_sources[DUE] = rss([{"title": "b", "link": "https://x/2"}])
    news_fetcher.fetch_news()
    assert get_source_health(2)["consecutive_failures"] == 0


def test_sources_list_marks_failing_sources(sent_messages):
    add_user(1)
    for _ in range(3):
        record_source_failure(2, "boom")
    tc.handle_update({"update_id": 1, "message": {"text": "/sources", "chat": {"id": 1}}})
    text = sent_messages[-1]["text"]
    assert "Feed Due ⚠️ in errore" in text and "Feed Uno ⚠️" not in text


# --- job heartbeat ----------------------------------------------------------------

def test_tracked_records_runs_and_swallows_exceptions(admin_env):
    calls = []
    ok_job = watchdog.tracked("ok_job", lambda: calls.append("ok") or 7)
    assert ok_job() == 7
    run = get_job_runs()["ok_job"]
    assert run["ok"] == 1 and run["started_at"] and run["finished_at"]

    def boom():
        raise RuntimeError("kaputt")

    assert watchdog.tracked("bad_job", boom)() is None
    run = get_job_runs()["bad_job"]
    assert run["ok"] == 0 and "kaputt" in run["error"]


def test_tracked_fetch_pings_healthcheck(admin_env, monkeypatch):
    admin_env.setenv("HEALTHCHECK_PING_URL", "https://hc.example/ping")
    pinged = []
    monkeypatch.setattr("requests.get", lambda url, timeout=None: pinged.append(url))
    watchdog.tracked(watchdog.JOB_FETCH, lambda: 0)()
    assert pinged == ["https://hc.example/ping"]


# --- rilevamento problemi -----------------------------------------------------------

def test_find_problems_failing_silent_and_stale(admin_env):
    old = NOW - timedelta(hours=80)
    record_source_success(1, 10, 1, now=old)                # muta da 80h
    for _ in range(3):
        record_source_failure(2, "HTTP 500", now=NOW)      # 3 fallimenti
    record_job_start(watchdog.JOB_FETCH, now=NOW - timedelta(minutes=60))
    record_job_end(watchdog.JOB_FETCH, ok=True, now=NOW - timedelta(minutes=60))   # polling 15 → soglia 45

    problems = watchdog.find_problems(NOW)
    assert set(problems) == {"source:1:silent", "source:2:failing", "job:fetch_news:stale"}
    assert "Feed Uno" in problems["source:1:silent"] and "80 ore" in problems["source:1:silent"]
    assert "Feed Due" in problems["source:2:failing"] and "HTTP 500" in problems["source:2:failing"]
    assert "60 minuti" in problems["job:fetch_news:stale"]


def test_find_problems_thresholds_from_env(admin_env):
    admin_env.setenv("WATCHDOG_SOURCE_FAILURES", "5")
    admin_env.setenv("WATCHDOG_SOURCE_SILENCE_HOURS", "200")
    admin_env.setenv("WATCHDOG_JOB_STALE_MINUTES", "120")
    record_source_success(1, 10, 1, now=NOW - timedelta(hours=80))
    for _ in range(3):
        record_source_failure(2, "x", now=NOW)
    record_job_end(watchdog.JOB_FETCH, ok=True, now=NOW - timedelta(minutes=60))
    assert watchdog.find_problems(NOW) == {}


def test_find_problems_reports_job_errors_and_ignores_unknown_sources(admin_env):
    record_job_end(watchdog.JOB_FETCH, ok=False, error="db locked", now=NOW)
    record_job_end(watchdog.JOB_DIGEST, ok=False, error="smtp", now=NOW)
    record_source_failure(999, "fonte inesistente", now=NOW)   # non tra le fonti attive
    problems = watchdog.find_problems(NOW)
    assert set(problems) == {"job:fetch_news:error", "job:run_digests:error"}
    assert "db locked" in problems["job:fetch_news:error"]


# --- avvisi e incidenti -----------------------------------------------------------------

def test_run_watchdog_notifies_once_and_on_recovery(admin_env, sent_messages):
    for _ in range(3):
        record_source_failure(2, "HTTP 500", now=NOW)

    assert watchdog.run_watchdog(NOW) == (1, 0)
    assert set(get_open_incidents()) == {"source:2:failing"}
    assert len(sent_messages) == 1 and sent_messages[0]["chat_id"] == 999
    assert "🚨" in sent_messages[0]["text"] and "Feed Due" in sent_messages[0]["text"]

    assert watchdog.run_watchdog(NOW + timedelta(minutes=30)) == (0, 0)   # stesso problema: silenzio
    assert len(sent_messages) == 1

    record_source_success(2, 5, 0, now=NOW + timedelta(hours=1))
    assert watchdog.run_watchdog(NOW + timedelta(hours=1)) == (0, 1)
    assert get_open_incidents() == {}
    assert "✅" in sent_messages[-1]["text"] and "Feed Due" in sent_messages[-1]["text"]


def test_notify_admin_without_admin_only_logs(admin_env, sent_messages):
    admin_env.delenv("ADMIN_TELEGRAM_ID")
    assert watchdog.notify_admin("test", ["a"]) == []
    assert sent_messages == []
def test_site_of_registrable_domain():
    assert watchdog.site_of("https://bo.istruzioneer.gov.it/feed/") == "istruzioneer.gov.it"
    assert watchdog.site_of("https://www.usr.sicilia.it/x") == "sicilia.it"
    assert watchdog.site_of("https://uspmc.sinp.net/") == "sinp.net"
    assert watchdog.site_of("https://www.mim.gov.it/web/abruzzo") == "mim.gov.it"
    assert watchdog.site_of("nonsense") == ""


def test_source_drift_detects_foreign_links(admin_env):
    from sfm.db_news import add_news
    src = {"id": 1, "url": "https://www.istruzionemolise.it/feed/", "name": "USR Molise"}
    assert watchdog.source_drift(src, news=[]) is False                            # troppo poche
    for i in range(6):
        add_news(f"n{i}", f"https://www.antropologie.it/{i}", "USR Molise", "", source_id=1)
    add_news("ok", "https://www.istruzionemolise.it/vera", "USR Molise", "", source_id=1)
    assert watchdog.source_drift(src) is True
    problems = watchdog.find_problems(NOW)
    assert "source:1:drift" in problems and "altro sito" in problems["source:1:drift"]


def test_source_drift_allows_subdomains_and_minority(admin_env):
    from sfm.db_news import add_news
    src = {"id": 2, "url": "https://www.istruzioneer.gov.it/tutte-le-notizie/feed/", "name": "USR ER"}
    for i in range(4):
        add_news(f"n{i}", f"https://bo.istruzioneer.gov.it/{i}", "x", "", source_id=2)
    add_news("ext", "https://www.mim.gov.it/doc", "x", "", source_id=2)
    assert watchdog.source_drift(src) is False


def test_weekly_summary_reports_counts(admin_env, sent_messages):
    add_user(1)
    record_source_success(1, 10, 1, now=NOW)
    for _ in range(3):
        record_source_failure(2, "HTTP 500", now=NOW)
    lines = watchdog.weekly_summary(NOW)
    assert lines[0].startswith("Fonti attive: 2") and "in errore: 1" in lines[0]
    assert "Utenti iscritti al bot: 1 (1 attivi)" in lines[2]
    assert any("In errore: Feed Due" in l for l in lines)
    assert sent_messages and "Riepilogo settimanale" in sent_messages[-1]["text"]
