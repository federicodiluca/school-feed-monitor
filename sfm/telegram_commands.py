from threading import Thread
from sfm.telegram import TELEGRAM_TOKEN, answer_callback_query, edit_message_text, send_long_message, send_message
from sfm.db_user import (
    activate_user,
    add_user,
    deactivate_user,
    delete_user,
    export_user_data,
    get_user,
    set_keywords,
    update_keywords,
    user_id_for_telegram,
)
from sfm import config_link
from sfm.db_configs import load_config
from sfm.db_health import get_failing_source_ids
from sfm.db_news import get_recent_news
from sfm.db_sources import (
    add_user_source,
    get_followed_source_ids,
    get_source,
    get_source_by_url,
    get_sources,
    get_user_sources,
    remove_source,
    set_user_source,
)
from sfm.news_fetcher import fetch_news, fetch_source
from sfm.source_parser import SourceError, detect_source
from sfm.report_generator import generate_report
from sfm.logger import log
from sfm.config_loader import get_config
from sfm.env import site_url
from sfm.utils import cleanHTMLPreview, escape_html, format_local_datetime, parse_keywords
import requests
import time

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

POLL_TIMEOUT = 10                 # long polling lato Telegram (secondi)
REQUEST_TIMEOUT = POLL_TIMEOUT + 10  # timeout HTTP: deve superare il long polling
LATEST_DEFAULT = 5
LATEST_MAX = 50

USAGE_SETKEYWORDS = "❗ Usa: /setkeywords parola1, parola2, PAROLA COMPOSTA, ..."
USAGE_REMOVEKEYWORDS = "❗ Usa: /removekeywords parola1, parola2, PAROLA COMPOSTA, ..."
USAGE_FOLLOW = "❗ Usa: /follow 1, 3 (numeri da /sources) oppure /follow all"
USAGE_UNFOLLOW = "❗ Usa: /unfollow 2 (numeri da /sources) oppure /unfollow all"
USAGE_ADDSOURCE = "❗ Usa: /addsource https://sito.it/notizie/ [Nome fonte]"
USAGE_REMOVESOURCE = "❗ Usa: /removesource N (numero da /sources; solo fonti aggiunte da te)"


def build_help_message(telegram_id=None):
    cfg = get_config()
    polling = cfg.get("polling_minutes", 10)
    report_time = cfg.get("daily_report_time", "18:00")
    retention = cfg.get("data_retention_days", 7)
    if telegram_id is not None:
        sources = get_user_sources(user_id_for_telegram(telegram_id))
        feed_list = "\n".join(f"• {'✅' if s['followed'] else '❌'} {escape_html(s['name'])}" for s in sources)
    else:
        feed_list = "\n".join(f"• {escape_html(s['name'])}" for s in get_sources())
    feed_list = feed_list or "⚠️ Nessuna fonte configurata."
    site = site_url()
    return f"""
🤖 <b>School Feed Monitor</b> — servizio attivo.

<b>Comandi disponibili:</b>
/start — registra l'utente e mostra questo messaggio
/stop — sospende le notifiche per questo utente
/setkeywords parola1, parola2, PAROLA COMPOSTA — aggiunge parole chiave (separate da virgole)
/removekeywords parola1, parola2, PAROLA COMPOSTA — rimuove keyword specifiche
/keywords — mostra le tue keyword attive
/fetch — aggiorna manualmente le notizie
/report — genera e invia il report giornaliero
/latest [n] — mostra le ultime n notizie (default {LATEST_DEFAULT}, max {LATEST_MAX})
/sources — elenco fonti con pulsanti per attivarle/disattivarle
/follow n, m — segui le fonti indicate (o "all")
/unfollow n, m — smetti di seguire le fonti indicate (o "all")
/addsource URL [nome] — aggiungi una fonte (RSS o pagina notizie)
/removesource n — rimuovi una fonte aggiunta da te
/start CODICE — applica la configurazione creata sul sito
/dati — cosa conservo su di te · /cancellami — cancella tutto
/commands — elenco rapido comandi

🌐 <b>Sito</b>: {site} — tutte le notizie, ricerca e configuratore delle fonti

<b>Scheduler:</b>
• Fetch ogni {polling} minuti
• Report giornaliero alle {report_time}
• Retention notizie e log: {retention} giorni

<b>Fonti monitorate</b> (✅ seguita, ❌ non seguita — gestisci con /sources):
{feed_list}
""".strip()


COMMANDS_MESSAGE = f"""
📋 <b>Elenco comandi disponibili:</b>

/start — registra e mostra informazioni complete
/stop — sospende le notifiche
/setkeywords parola1, parola2, PAROLA COMPOSTA — aggiunge keyword (separate da virgole)
/removekeywords parola1, parola2, PAROLA COMPOSTA — rimuove keyword specifiche
/keywords — mostra le tue keyword attive
/fetch — aggiorna notizie manualmente
/report — genera report giornaliero
/latest [n] — mostra ultime n notizie (default {LATEST_DEFAULT}, max {LATEST_MAX})
/sources — elenco fonti con pulsanti on/off
/follow n, m — segui fonti (o "all")
/unfollow n, m — non seguire fonti (o "all")
/addsource URL [nome] — aggiungi una fonte
/removesource n — rimuovi una fonte aggiunta da te
/start CODICE — applica la configurazione creata sul sito
/dati — cosa conservo su di te
/cancellami — cancella tutto quello che ho su di te
/commands — mostra questo elenco

💡 <i>Usa /start per informazioni complete su feed e scheduler.</i>
""".strip()


def parse_command(text):
    """Estrae (comando, argomenti) da un messaggio.
    '/SetKeywords@MyBot a, b' -> ('setkeywords', 'a, b'). Ritorna (None, '') se non è un comando."""
    if not text:
        return None, ""
    text = text.strip()
    if not text.startswith("/"):
        return None, ""
    head, _, args = text.partition(" ")
    command = head[1:].split("@", 1)[0].lower()
    if not command:
        return None, ""
    return command, args.strip()


# === Handler dei singoli comandi ===

def cmd_start(telegram_id, args, username=None):
    """/start, eventualmente seguito dal codice di configurazione creato sul sito
    (il link "Apri il bot e configura" apre proprio /start CODICE)."""
    added = add_user(telegram_id, username)
    if added:
        send_message("👋 Benvenuto!", chat_id=telegram_id)
    else:
        activate_user(telegram_id)
        send_message("👋 Bentornato! Le notifiche sono attive.", chat_id=telegram_id)

    code = (args or "").strip()
    if code:
        apply_config_code(telegram_id, code)
    elif added:
        send_message(f"Scegli le fonti sul sito — è più comodo: {site_url()}/configura\n"
                     "In fondo alla pagina premi «Salva e porta su Telegram» e torni qui con tutto pronto.\n"
                     "Oppure fai da qui con /sources e /setkeywords parola1, parola2.", chat_id=telegram_id)
    send_message(build_help_message(telegram_id), parse_mode="HTML", chat_id=telegram_id)


def resolve_config(code):
    """Configurazione dietro l'argomento di /start: o un payload che se la porta dietro
    (sito statico), o un codice usa-e-getta salvato dal sito. None se non è leggibile."""
    if config_link.looks_like_payload(code):
        link = config_link.decode(code)
        if link is None:
            return None
        ids = [s["id"] for url in link["urls"] if (s := get_source_by_url(url))]
        return {"sources": ids, "keywords": link["keywords"]} if ids else None
    return load_config(code.strip().upper())


def apply_config_code(telegram_id, code):
    """Applica una configurazione creata sul sito: fonti seguite + parole chiave.
    Ritorna True se il codice era valido."""
    config = resolve_config(code)
    if config is None:
        send_message("❌ Codice non valido o scaduto (vale 24 ore e si usa una volta sola). "
                     "Generane uno nuovo dal sito.", chat_id=telegram_id)
        return False
    user_id = user_id_for_telegram(telegram_id)
    chosen = {int(s) for s in config.get("sources", [])}
    sources = get_sources()
    for source in sources:
        set_user_source(user_id, source["id"], source["id"] in chosen)
    keywords = config.get("keywords") or []
    if keywords:
        set_keywords(user_id, keywords)
    n = sum(1 for s in sources if s["id"] in chosen)
    message = f"✅ Configurazione applicata: <b>{n} fonti</b>"
    if keywords:
        message += f" e parole chiave <b>{escape_html(', '.join(keywords))}</b>"
    message += ".\nTi avviso quando esce una notizia con le tue parole, più un riepilogo giornaliero."
    send_message(message, parse_mode="HTML", chat_id=telegram_id)
    return True


def cmd_stop(telegram_id, args):
    deactivate_user(telegram_id)
    send_message("✅ Hai disattivato le notifiche. Usa /start per riattivarle.", chat_id=telegram_id)


def cmd_setkeywords(telegram_id, args):
    new_keywords = parse_keywords(args)
    if not new_keywords:
        send_message(USAGE_SETKEYWORDS, chat_id=telegram_id)
        return

    user = get_user(telegram_id)
    if user is None:
        # utente che scrive senza /start: lo registriamo al volo
        add_user(telegram_id)
        user = get_user(telegram_id)
    existing_keywords = user["keywords"]

    # Mappa case-insensitive per evitare duplicati
    keyword_map = {kw.lower(): kw for kw in existing_keywords}
    added_keywords, skipped_keywords = [], []
    for new_kw in new_keywords:
        if new_kw.lower() not in keyword_map:
            keyword_map[new_kw.lower()] = new_kw
            added_keywords.append(new_kw)
        else:
            skipped_keywords.append(new_kw)

    if not added_keywords:
        send_message(f"❌ Tutte le keyword specificate sono già presenti.\n📝 Keyword attuali: {', '.join(existing_keywords)}", chat_id=telegram_id)
        return

    final_keywords = existing_keywords + added_keywords
    update_keywords(telegram_id, final_keywords)

    message = f"✅ Keyword aggiunte: {', '.join(added_keywords)}"
    if skipped_keywords:
        message += f"\n⚠️ Già presenti: {', '.join(skipped_keywords)}"
    message += f"\n📝 Totale keyword: {len(final_keywords)}"
    send_message(message, chat_id=telegram_id)


def cmd_removekeywords(telegram_id, args):
    keywords_to_remove = [kw.lower() for kw in parse_keywords(args)]
    if not keywords_to_remove:
        send_message(USAGE_REMOVEKEYWORDS, chat_id=telegram_id)
        return

    user = get_user(telegram_id)
    if not user or not user["keywords"]:
        send_message("❌ Non hai keyword impostate. Usa /setkeywords per aggiungerne.", chat_id=telegram_id)
        return

    original_keywords = user["keywords"]
    keyword_map = {kw.lower(): kw for kw in original_keywords}

    removed, not_found = [], []
    for remove_kw in keywords_to_remove:
        if remove_kw in keyword_map:
            removed.append(keyword_map[remove_kw])
        else:
            not_found.append(remove_kw)

    if not removed:
        send_message(f"❌ Nessuna delle keyword specificate è stata trovata.\n📝 Keyword attuali: {', '.join(original_keywords)}", chat_id=telegram_id)
        return

    final_keywords = [kw for kw in original_keywords if kw not in removed]
    update_keywords(telegram_id, final_keywords)

    message = f"✅ Keyword rimosse: {', '.join(removed)}"
    if not_found:
        message += f"\n⚠️ Non trovate: {', '.join(not_found)}"
    if final_keywords:
        message += f"\n📝 Keyword rimanenti: {', '.join(final_keywords)}"
    else:
        message += "\n📝 Non hai più keyword impostate."
    send_message(message, chat_id=telegram_id)


def cmd_keywords(telegram_id, args):
    user = get_user(telegram_id)
    if not user or not user["keywords"]:
        send_message("❌ Non hai keyword impostate.\n💡 Usa /setkeywords per aggiungerne alcune!", chat_id=telegram_id)
        return
    keywords_list = user["keywords"]
    keywords_text = "\n".join([f"• {escape_html(kw)}" for kw in keywords_list])
    message = f"📝 <b>Le tue keyword attive ({len(keywords_list)}):</b>\n\n{keywords_text}\n\n💡 Usa /setkeywords per modificare o /removekeywords per rimuovere."
    send_message(message, parse_mode="HTML", chat_id=telegram_id)


def cmd_commands(telegram_id, args):
    send_message(COMMANDS_MESSAGE, parse_mode="HTML", chat_id=telegram_id)


def cmd_fetch(telegram_id, args):
    new_count = fetch_news()
    send_message(f"✅ Notizie aggiornate manualmente ({new_count} nuove).", chat_id=telegram_id)


def cmd_report(telegram_id, args):
    generate_report(target_chat_id=telegram_id)


def cmd_latest(telegram_id, args):
    n = LATEST_DEFAULT
    first = args.split()[0] if args else ""
    if first.isdigit():
        n = max(1, min(int(first), LATEST_MAX))

    rows = get_recent_news(limit=n, source_ids=get_followed_source_ids(user_id_for_telegram(telegram_id)))
    if not rows:
        send_message("⚠️ Nessuna notizia disponibile dalle fonti che segui. Controlla /sources.", chat_id=telegram_id)
        return

    lines = [f"📰 <b>Ultime {len(rows)} notizie</b>:\n"]
    for r in rows:
        title = escape_html(r.get("title") or "Titolo non disponibile")
        source = escape_html(r.get("source") or "Sorgente")
        link = escape_html(r.get("link") or "")
        published = format_local_datetime(r.get("published_at"))
        preview = cleanHTMLPreview(r.get("content") or "")
        lines.append(f"<a href=\"{link}\">{source}</a> – {published}\n<b>{title}</b>\n<i>{preview}</i>\n")

    send_long_message("\n".join(lines), chat_id=telegram_id, parse_mode="HTML")


# === Fonti ===

ALL_TOKENS = ("all", "tutte", "tutti", "*")
SOURCE_WARN_FAILURES = 3  # letture fallite consecutive prima di mostrare il simbolo di errore in /sources


def _ensure_user_id(telegram_id):
    """users.id per il telegram_id, registrando l'utente se non esiste ancora."""
    if get_user(telegram_id) is None:
        add_user(telegram_id)
    return user_id_for_telegram(telegram_id)


def format_sources_list(telegram_id):
    user_id = user_id_for_telegram(telegram_id)
    sources = get_user_sources(user_id)
    if not sources:
        return "⚠️ Nessuna fonte configurata. Aggiungine una con /addsource URL [nome]."
    followed = sum(1 for s in sources if s["followed"])
    lines = [f"📡 <b>Fonti disponibili ({followed}/{len(sources)} seguite)</b>\n"]
    failing = get_failing_source_ids(SOURCE_WARN_FAILURES)
    for s in sources:
        mark = "✅" if s["followed"] else "❌"
        extra = " · HTML" if s["type"] == "html" else ""
        if s["id"] in failing:
            extra += " ⚠️ in errore"
        if s["origin"] == "user":
            extra += " · custom" + (" (tua)" if s["added_by"] == user_id else "")
        lines.append(f"{mark} <b>{s['id']}</b>. {escape_html(s['name'])}{extra}")
    lines.append("\n👇 Tocca una fonte per attivarla/disattivarla. In alternativa: /follow n, m · /unfollow n, m · /addsource URL [nome]")
    return "\n".join(lines)


CB_PREFIX = "src"  # callback_data: "src:t:<id>" toggle, "src:all:1|0" tutte/nessuna


def build_sources_keyboard(telegram_id):
    """Tastiera inline con un pulsante per fonte (✅/❌) più "Tutte" e "Nessuna"."""
    sources = get_user_sources(user_id_for_telegram(telegram_id))
    if not sources:
        return None
    rows = []
    for s in sources:
        mark = "✅" if s["followed"] else "❌"
        rows.append([{"text": f"{mark} {s['name']}"[:64], "callback_data": f"{CB_PREFIX}:t:{s['id']}"}])
    rows.append([
        {"text": "✅ Tutte", "callback_data": f"{CB_PREFIX}:all:1"},
        {"text": "❌ Nessuna", "callback_data": f"{CB_PREFIX}:all:0"},
    ])
    return {"inline_keyboard": rows}


def cmd_sources(telegram_id, args):
    send_message(format_sources_list(telegram_id), chat_id=telegram_id, parse_mode="HTML",
                 reply_markup=build_sources_keyboard(telegram_id))


def handle_sources_callback(telegram_id, chat_id, message_id, data):
    """Gestisce il tap su un pulsante di /sources. Ritorna il testo per il popup di conferma."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != CB_PREFIX:
        return None
    action, value = parts[1], parts[2]

    user_id = _ensure_user_id(telegram_id)
    before = get_followed_source_ids(user_id)

    if action == "t" and value.isdigit():
        source = get_source(int(value))
        if not source or not source["enabled"]:
            return "Fonte non più disponibile"
        currently = source["id"] in before
        set_user_source(user_id, source["id"], not currently)
        feedback = f"{'❌ Non segui più' if currently else '✅ Ora segui'}: {source['name']}"
    elif action == "all" and value in ("0", "1"):
        follow = value == "1"
        for s in get_sources():
            set_user_source(user_id, s["id"], follow)
        feedback = "✅ Segui tutte le fonti" if follow else "❌ Non segui nessuna fonte"
    else:
        return None

    if get_followed_source_ids(user_id) != before:
        # Telegram rifiuta un edit senza modifiche ("message is not modified"): lo evitiamo
        edit_message_text(chat_id, message_id, format_sources_list(telegram_id), parse_mode="HTML",
                          reply_markup=build_sources_keyboard(telegram_id))
    return feedback


def handle_callback_query(cq):
    """Update di tipo callback_query (pressione di un pulsante inline)."""
    telegram_id = (cq.get("from") or {}).get("id")
    message = cq.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    data = cq.get("data") or ""
    feedback = None
    if telegram_id is not None and chat_id is not None and message_id is not None:
        try:
            feedback = handle_sources_callback(telegram_id, chat_id, message_id, data)
        except Exception as e:
            log(f"❌ Errore callback '{data}': {e}")
            feedback = "Errore, riprova"
    if cq.get("id"):
        answer_callback_query(cq["id"], text=feedback)
    return "callback"


def _parse_source_ids(args, telegram_id):
    """Ritorna (ids, invalid). ids=None se non ci sono argomenti.
    'all' → tutte le fonti attive; altrimenti numeri separati da virgola/spazio."""
    tokens = [t for t in args.replace(",", " ").split() if t]
    if not tokens:
        return None, []
    valid = {s["id"] for s in get_user_sources(user_id_for_telegram(telegram_id))}
    if len(tokens) == 1 and tokens[0].lower() in ALL_TOKENS:
        return sorted(valid), []
    ids, invalid = [], []
    for t in tokens:
        if t.isdigit() and int(t) in valid:
            if int(t) not in ids:
                ids.append(int(t))
        else:
            invalid.append(t)
    return ids, invalid


def _set_follow(telegram_id, args, follow, usage):
    ids, invalid = _parse_source_ids(args, telegram_id)
    if ids is None:
        send_message(usage, chat_id=telegram_id)
        return
    if not ids:
        send_message(f"❌ Nessuna fonte valida tra: {', '.join(invalid)}.\n{usage}", chat_id=telegram_id)
        return
    user_id = _ensure_user_id(telegram_id)
    for sid in ids:
        set_user_source(user_id, sid, follow)
    names = [escape_html(get_source(sid)["name"]) for sid in ids]
    verb = "Ora segui" if follow else "Non segui più"
    message = f"✅ {verb}: {', '.join(names)}"
    if invalid:
        message += f"\n⚠️ Ignorate (non valide): {', '.join(escape_html(i) for i in invalid)}"
    message += "\n\n" + format_sources_list(telegram_id)
    send_long_message(message, chat_id=telegram_id, parse_mode="HTML")


def cmd_follow(telegram_id, args):
    _set_follow(telegram_id, args, True, USAGE_FOLLOW)


def cmd_unfollow(telegram_id, args):
    _set_follow(telegram_id, args, False, USAGE_UNFOLLOW)


def cmd_addsource(telegram_id, args):
    parts = args.split(maxsplit=1)
    if not parts:
        send_message(USAGE_ADDSOURCE, chat_id=telegram_id)
        return
    url = parts[0].strip()
    custom_name = parts[1].strip() if len(parts) > 1 else ""
    if "." not in url:
        send_message(USAGE_ADDSOURCE, chat_id=telegram_id)
        return

    user_id = _ensure_user_id(telegram_id)

    existing = get_source_by_url(url)
    if existing and existing["enabled"]:
        set_user_source(user_id, existing["id"], True)
        send_message(f"ℹ️ Fonte già presente: {escape_html(existing['name'])} (n. {existing['id']}). Ora la segui.",
                     parse_mode="HTML", chat_id=telegram_id)
        return

    send_message("🔎 Controllo la fonte, un attimo...", chat_id=telegram_id)
    try:
        detected = detect_source(url)
    except SourceError as e:
        send_message(f"❌ Non riesco a leggere notizie da questa URL: {escape_html(e)}\n"
                     "Prova a incollare direttamente il link del feed RSS, se il sito ne ha uno.",
                     parse_mode="HTML", chat_id=telegram_id)
        return
    except Exception as e:
        log(f"❌ Errore addsource {url}: {e}")
        send_message("❌ Errore inatteso durante il controllo della fonte. Riprova più tardi.", chat_id=telegram_id)
        return

    name = custom_name or detected["name"] or url
    source, created = add_user_source(name, detected["url"], detected["type"], user_id)

    # Prima lettura senza notifiche: evita una raffica di alert sulle notizie già pubblicate
    seeded = fetch_source(source, notify=False)

    kind = "feed RSS" if detected["type"] == "rss" else "pagina HTML (scraping)"
    sample = detected["items"][0]["title"] if detected["items"] else ""
    message = (
        f"✅ Fonte {'aggiunta' if created else 'riattivata'}: <b>{escape_html(source['name'])}</b> (n. {source['id']})\n"
        f"📎 Tipo: {kind}\n"
        f"🔗 {escape_html(source['url'])}\n"
        f"📰 Notizie trovate: {len(detected['items'])} (salvate {seeded} nuove, senza notifica)\n"
    )
    if sample:
        message += f"🧪 Esempio: <i>{escape_html(sample)}</i>\n"
    message += "\nLa segui già; gli altri utenti possono attivarla con /follow."
    send_message(message, parse_mode="HTML", chat_id=telegram_id)


def cmd_removesource(telegram_id, args):
    token = args.split()[0] if args else ""
    if not token.isdigit():
        send_message(USAGE_REMOVESOURCE, chat_id=telegram_id)
        return
    source = get_source(int(token))
    if not source or not source["enabled"]:
        send_message("❌ Fonte non trovata. Controlla i numeri con /sources.", chat_id=telegram_id)
        return
    if source["origin"] != "user":
        send_message("❌ Questa fonte è definita nella configurazione del bot e non può essere rimossa da qui. "
                     "Puoi smettere di seguirla con /unfollow.", chat_id=telegram_id)
        return
    if not remove_source(source["id"], user_id_for_telegram(telegram_id)):
        send_message("❌ Puoi rimuovere solo le fonti che hai aggiunto tu. Per non seguirla usa /unfollow.", chat_id=telegram_id)
        return
    send_message(f"🗑️ Fonte rimossa: {escape_html(source['name'])}", parse_mode="HTML", chat_id=telegram_id)


def cmd_dati(telegram_id, args):
    """Mostra cosa il bot conserva su questa chat (GDPR: diritto di accesso)."""
    user = get_user(telegram_id)
    if not user:
        send_message("Non ho nulla su questa chat. Usa /start per iniziare.", chat_id=telegram_id)
        return
    data = export_user_data(user["id"])
    followed = [f["name"] for f in data["source_preferences"] if f["follow"]]
    lines = [
        "🔎 <b>Quello che conservo su questa chat</b>",
        f"• Identificativo Telegram: <code>{user['telegram_id']}</code>" + (f" (@{escape_html(user['username'])})" if user["username"] else ""),
        f"• Parole chiave: {escape_html(', '.join(user['keywords'])) if user['keywords'] else '—'}",
        f"• Notifiche: {'attive' if user['active'] else 'sospese'}",
        f"• Riepilogo: {user['digest_time'] or 'orario predefinito'}",
        f"• Fonti seguite ({len(followed)}): {escape_html(', '.join(followed[:20])) if followed else '—'}" + (" …" if len(followed) > 20 else ""),
        f"• Iscritto dal: {str(user['created_at'])[:10]}",
        "",
        "Inoltre tengo l'elenco delle notizie già inviate, per non ripetertele (massimo 30 giorni).",
        "Con /cancellami elimino tutto subito.",
    ]
    send_long_message("\n".join(lines), chat_id=telegram_id, parse_mode="HTML")


def cmd_cancellami(telegram_id, args):
    """Cancella definitivamente i dati di questa chat (GDPR: diritto all'oblio)."""
    user = get_user(telegram_id)
    if not user:
        send_message("Non ho nulla da cancellare per questa chat.", chat_id=telegram_id)
        return
    if (args or "").strip().upper() != "CONFERMO":
        send_message("⚠️ Questo cancella <b>tutto</b> (parole chiave, fonti, storico invii) e non è reversibile.\n"
                     "Se sei sicuro scrivi: <code>/cancellami CONFERMO</code>", parse_mode="HTML", chat_id=telegram_id)
        return
    delete_user(user["id"])
    send_message("🗑️ Fatto: non conservo più niente su questa chat. Con /start puoi ricominciare quando vuoi.",
                 chat_id=telegram_id)


def cmd_unknown(telegram_id, args, command=None):
    send_message(f"❓ Comando /{command} non riconosciuto. Usa /commands per l'elenco.", chat_id=telegram_id)


HANDLERS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "setkeywords": cmd_setkeywords,
    "removekeywords": cmd_removekeywords,
    "keywords": cmd_keywords,
    "commands": cmd_commands,
    "help": cmd_commands,
    "fetch": cmd_fetch,
    "report": cmd_report,
    "latest": cmd_latest,
    "sources": cmd_sources,
    "follow": cmd_follow,
    "unfollow": cmd_unfollow,
    "addsource": cmd_addsource,
    "removesource": cmd_removesource,
    "dati": cmd_dati,
    "cancellami": cmd_cancellami,
}


def handle_update(update):
    """Gestisce un singolo update di Telegram. Ritorna il comando eseguito (o None)."""
    if update.get("callback_query"):
        return handle_callback_query(update["callback_query"])

    message = update.get("message") or {}
    text = message.get("text", "")
    chat = message.get("chat") or {}
    telegram_id = chat.get("id")
    if not text or telegram_id is None:
        return None

    command, args = parse_command(text)
    if command is None:
        return None

    username = chat.get("username") or message.get("from", {}).get("username")
    if command == "start":
        cmd_start(telegram_id, args, username=username)
    elif command in HANDLERS:
        HANDLERS[command](telegram_id, args)
    else:
        cmd_unknown(telegram_id, args, command=command)
    return command


POLL_BACKOFF_START = 5
POLL_BACKOFF_MAX = 60
POLL_LOG_EVERY = 10       # dopo il primo errore, una riga ogni N tentativi falliti


def _poll_failure(problem, failures):
    """Tempo di attesa dopo un getUpdates fallito, con log parsimonioso: un errore che dura
    (tipico il 409 di due bot accesi insieme) non deve riempire il file di log."""
    if failures == 1 or failures % POLL_LOG_EVERY == 0:
        hint = ""
        if "409" in str(problem) or "Conflict" in str(problem):
            hint = (" — un'altra istanza del bot sta leggendo gli update: controlla di non "
                    "averlo acceso su due macchine (o in due container)")
        suffix = f" [{failures}° tentativo di fila]" if failures > 1 else ""
        log(f"❌ getUpdates fallito{suffix}: {problem}{hint}")
    return min(POLL_BACKOFF_START * 2 ** (failures - 1), POLL_BACKOFF_MAX)


def handle_commands():
    offset = None
    failures = 0
    while True:
        try:
            resp = requests.get(
                f"{API_URL}/getUpdates",
                params={"timeout": POLL_TIMEOUT, "offset": offset},
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()
            if not data.get("ok"):
                failures += 1
                time.sleep(_poll_failure(data, failures))
                continue
            if failures:
                log(f"✅ getUpdates di nuovo funzionante dopo {failures} tentativi falliti")
                failures = 0

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    handle_update(update)
                except Exception as e:
                    log(f"❌ Errore gestione update {update.get('update_id')}: {e}")

        except Exception as e:
            failures += 1
            time.sleep(_poll_failure(e, failures))


def start_telegram_listener():
    thread = Thread(target=handle_commands, daemon=True)
    thread.start()
    return thread
