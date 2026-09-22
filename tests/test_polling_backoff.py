"""Un conflitto che dura (409: due bot accesi) non deve riempire i log né martellare l'API."""
import sfm.telegram_commands as tc

CONFLICT = {"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates request"}


def test_backoff_grows_and_stops_at_the_ceiling():
    waits = [tc._poll_failure(CONFLICT, n) for n in range(1, 8)]
    assert waits[0] == tc.POLL_BACKOFF_START
    assert waits == sorted(waits) and max(waits) == tc.POLL_BACKOFF_MAX


def test_only_the_first_failure_and_then_one_every_ten_are_logged(monkeypatch):
    lines = []
    monkeypatch.setattr(tc, "log", lines.append)
    for n in range(1, 31):
        tc._poll_failure(CONFLICT, n)
    assert len(lines) == 4                       # tentativi 1, 10, 20, 30
    assert "due macchine" in lines[0]            # spiega la causa più probabile
    assert "10° tentativo" in lines[1]


def test_a_generic_error_does_not_get_the_conflict_hint(monkeypatch):
    lines = []
    monkeypatch.setattr(tc, "log", lines.append)
    tc._poll_failure(ConnectionError("rete assente"), 1)
    assert "due macchine" not in lines[0] and "rete assente" in lines[0]
