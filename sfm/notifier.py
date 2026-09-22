"""Dispatcher delle notifiche: decide su quali canali raggiungere un utente e
delega l'invio al modulo del canale. Il core (fetch/match/report) parla solo
con questo modulo, mai direttamente con Telegram o altri canali."""
from sfm.channels import telegram_channel
from sfm.logger import log

# Registro dei canali disponibili: nome -> modulo con send_alert / send_digest.
CHANNELS = {telegram_channel.NAME: telegram_channel}


def user_label(user):
    return user.get("telegram_id") or user.get("id") or "?"


def channels_for(user):
    """Canali su cui l'utente vuole essere raggiunto: solo Telegram, per ora."""
    return [telegram_channel.NAME] if user.get("telegram_id") else []


def _dispatch(kind, user, *args):
    """Invia su ogni canale dell'utente. Ritorna la lista dei canali su cui l'invio è riuscito
    (un canale che fallisce non blocca gli altri)."""
    sent = []
    for name in channels_for(user):
        try:
            getattr(CHANNELS[name], kind)(user, *args)
            sent.append(name)
        except Exception as e:
            log(f"❌ Errore {kind} via {name} a {user_label(user)}: {e}")
    return sent


def send_alert(user, news, matched_keywords):
    """Notifica immediata a un utente. Ritorna i canali su cui è riuscita."""
    return _dispatch("send_alert", user, news, matched_keywords)


def send_digest(user, news_list):
    """Report/riepilogo a un utente. Le news possono avere 'matched_keywords' (evidenziate
    dai canali). Ritorna i canali su cui è riuscito."""
    return _dispatch("send_digest", user, news_list)
