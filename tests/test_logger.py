import os
from datetime import datetime, timedelta

import sfm.logger as logger


def test_log_writes_daily_file(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "LOG_DIR", str(tmp_path / "logs"))
    logger.log("ciao 🚀")
    expected = tmp_path / "logs" / f"{datetime.now().date()}.log"
    assert expected.exists()
    assert "ciao 🚀" in expected.read_text(encoding="utf-8")


def test_cleanup_logs_removes_only_old_dated_logs(tmp_path, monkeypatch):
    """Regressione: la vecchia parse_date (oscurata da una seconda definizione)
    lanciava sempre e la pulizia dei log non cancellava mai nulla."""
    monkeypatch.setattr(logger, "LOG_DIR", str(tmp_path))
    today = datetime.now().date()
    old = (today - timedelta(days=10)).isoformat()
    recent = (today - timedelta(days=1)).isoformat()
    for name in (f"{old}.log", f"{recent}.log", "note.txt", "random.log"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    removed = logger.cleanup_logs(retention_days=7)

    assert removed == 1
    assert not (tmp_path / f"{old}.log").exists()
    assert (tmp_path / f"{recent}.log").exists()
    assert (tmp_path / "note.txt").exists()
    assert (tmp_path / "random.log").exists()  # nome non datato: ignorato


def test_cleanup_logs_missing_dir_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "LOG_DIR", str(tmp_path / "missing"))
    assert logger.cleanup_logs(7) == 0
    assert not os.path.exists(tmp_path / "missing")


def test_log_survives_console_without_utf8(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(logger, "LOG_DIR", str(tmp_path))
    real_print = print

    def cp1252_print(msg, *a, **k):
        msg.encode("cp1252")  # solleva UnicodeEncodeError con le emoji
        real_print(msg, *a, **k)

    monkeypatch.setattr("builtins.print", cp1252_print)
    logger.log("🚀 avvio")
    assert "avvio" in capsys.readouterr().out
    assert "🚀 avvio" in (tmp_path / f"{datetime.now().date()}.log").read_text(encoding="utf-8")
