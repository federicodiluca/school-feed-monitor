# bot/telegram.py
import requests
import time
from sfm.config_loader import get_config
from sfm.db_user import deactivate_user, get_user, get_users
from sfm.logger import log

CONFIG = get_config()
TELEGRAM_TOKEN = CONFIG["telegram_token"]
DISABLE_WEB_PAGE_PREVIEW = CONFIG.get("disable_web_page_preview", True)
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Parametri
MAX_MSG_LEN = 4000         # Telegram ~4096, resto conservativo
SLEEP_BETWEEN_MSGS = 0.35  # evita di colpire rate limits
REQUEST_TIMEOUT = 15


def api_call(method, payload):
    """Chiama un metodo della Bot API. Ritorna {"ok": True, "result": ...} oppure {"ok": False, ...}."""
    try:
        # JSON: i booleani arrivano a Telegram come veri booleani, non come stringhe
        resp = requests.post(f"{API_BASE}/{method}", json=payload, timeout=REQUEST_TIMEOUT)
        try:
            data = resp.json()
        except ValueError:
            data = {"ok": False, "status_code": resp.status_code, "text": resp.text}

        if not resp.ok or not data.get("ok"):
            log(f"❌ Telegram error {resp.status_code} - {method} - chat_id={payload.get('chat_id')} - resp={data}")
            return {"ok": False, "status_code": resp.status_code, "data": data}

        return {"ok": True, "result": data.get("result")}

    except Exception as e:
        log(f"❌ Errore chiamata Telegram {method}: {e}")
        return {"ok": False, "exception": str(e)}


def send_message(text, parse_mode=None, chat_id=None, disable_web_page_preview=None, reply_markup=None):
    """Invia un messaggio Telegram. Con chat_id=None lo invia a tutti gli utenti attivi.
    reply_markup: es. {"inline_keyboard": [[{"text": ..., "callback_data": ...}]]}."""
    if chat_id is None:
        results = []
        for user in get_users():
            uid = user.get("telegram_id")
            if uid:
                results.append(_send_single_message(
                    text, parse_mode=parse_mode, chat_id=uid,
                    disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup,
                ))
        return results

    return _send_single_message(text, parse_mode=parse_mode, chat_id=chat_id,
                                disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)


# Telegram risponde 403 quando dall'altra parte non c'è più nessuno da avvisare
BLOCKED_DESCRIPTIONS = ("bot was blocked", "bot was kicked", "user is deactivated", "chat not found")


def _suspend_if_unreachable(chat_id, result):
    """Se l'utente ha bloccato il bot (o ha chiuso l'account) smette di provarci a ogni
    notizia: sospende le notifiche. Con /start si riattiva da solo."""
    if result.get("ok") or result.get("status_code") != 403 or not chat_id:
        return False
    description = str((result.get("data") or {}).get("description", "")).lower()
    if not any(hint in description for hint in BLOCKED_DESCRIPTIONS):
        return False
    user = get_user(chat_id)
    if not user or not user.get("active"):
        return False
    deactivate_user(chat_id)
    log(f"🚫 {chat_id} non è più raggiungibile ({description}): notifiche sospese, /start per riattivarle")
    return True


def _send_single_message(text, parse_mode=None, chat_id=None, disable_web_page_preview=None, reply_markup=None):
    """Funzione privata: invia un singolo messaggio a Telegram."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": DISABLE_WEB_PAGE_PREVIEW if disable_web_page_preview is None else disable_web_page_preview
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = api_call("sendMessage", payload)
    _suspend_if_unreachable(chat_id, result)
    return result


def edit_message_text(chat_id, message_id, text, parse_mode=None, reply_markup=None):
    """Modifica testo (e tastiera) di un messaggio già inviato dal bot."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "disable_web_page_preview": DISABLE_WEB_PAGE_PREVIEW,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return api_call("editMessageText", payload)


def answer_callback_query(callback_query_id, text=None):
    """Chiude lo "spinner" del pulsante premuto, con eventuale notifica breve."""
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text[:200]
    return api_call("answerCallbackQuery", payload)


def split_long_message(text, max_len=MAX_MSG_LEN):
    """Spezza un testo in parti <= max_len, tagliando preferibilmente su
    doppia newline > newline > spazio."""
    if not text:
        return []

    parts = []
    remaining = text.strip()

    while remaining:
        if len(remaining) <= max_len:
            parts.append(remaining)
            break

        # cerca taglio intelligente: doppia newline > newline > space
        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind(" ", 0, max_len)
        if cut == -1 or cut < int(max_len * 0.6):
            cut = max_len

        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    return [p for p in parts if p]


def send_long_message(text, chat_id, parse_mode="HTML"):
    """
    Spezza e invia un testo lungo in più messaggi rispettando il limite.
    Ritorna lista di esiti.
    """
    parts = split_long_message(text)
    results = []
    for i, p in enumerate(parts):
        res = send_message(p, parse_mode=parse_mode, chat_id=chat_id)
        results.append(res)
        if i < len(parts) - 1:
            time.sleep(SLEEP_BETWEEN_MSGS)
    return results
