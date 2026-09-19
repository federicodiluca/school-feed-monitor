"""Invia una email di prova con la configurazione di .env, per verificare il backend.

    python scripts/send_test_email.py destinatario@esempio.it [alert|digest]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # eseguibile da ovunque

from sfm.channels.email_channel import format_alert, format_digest
from sfm.env import env
from sfm.mailer import EmailError, is_enabled, send_email

SAMPLE = {
    "title": "Email di prova da School Feed Monitor",
    "link": "https://example.org/prova",
    "source": "Fonte di prova",
    "content": "<p>Se leggi questo messaggio il backend email funziona.</p>",
    "published_at": "2026-09-12 08:00:00",
}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    to, kind = argv[1], (argv[2] if len(argv) > 2 else "alert")
    print(f"Backend: {env('EMAIL_BACKEND') or 'none'} | From: {env('EMAIL_FROM') or '(mancante)'} | Abilitato: {is_enabled()}")
    subject, html, text = format_alert(SAMPLE, ["prova"]) if kind == "alert" else format_digest([SAMPLE])
    try:
        ok = send_email(to, subject, html, text)
    except EmailError as e:
        print(f"ERRORE: {e}")
        return 1
    print("Inviata." if ok else "Backend disabilitato (EMAIL_BACKEND=none): nessun invio.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
