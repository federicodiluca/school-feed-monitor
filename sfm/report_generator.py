"""Report giornaliero: wrapper di compatibilità sul modulo digest.
`/report` su Telegram e la vecchia API generate_report() passano da qui."""
from sfm.channels.telegram_channel import build_report, no_news_message  # noqa: F401 (compatibilità)
from sfm.db_user import get_user
from sfm.digest import run_digests, send_user_digest
from sfm.logger import log


def generate_report(target_chat_id=None):
    """Report a un singolo utente Telegram (target_chat_id), senza toccare il guard
    giornaliero, oppure a tutti gli attivi (force)."""
    if target_chat_id:
        user = get_user(target_chat_id) or {"id": None, "telegram_id": target_chat_id, "keywords": []}
        count, _ = send_user_digest(user, mark=False)
        log(f"📄 Report inviato manualmente a {target_chat_id} ({count} notizie).")
        return
    run_digests(force=True)
