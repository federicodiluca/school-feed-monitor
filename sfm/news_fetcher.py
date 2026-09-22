from sfm import notifier
from sfm.db_deliveries import record_delivery
from sfm.db_health import record_source_failure, record_source_success
from sfm.db_news import add_news
from sfm.db_sources import get_followers_map, get_sources
from sfm.db_user import get_users
from sfm.logger import log
from sfm.matching import match_users
from sfm.source_parser import SourceError, read_source


def notify_users(users, news):
    """Alert immediato agli utenti le cui parole chiave compaiono nel titolo o nel
    contenuto; ogni invio riuscito è registrato in deliveries (per il badge "già
    segnalata" nel riepilogo). Ritorna il numero di utenti notificati."""
    notified = 0
    for user, matched_keywords in match_users(news, users):
        log(f"📨 Notifica a {notifier.user_label(user)} per keyword: {', '.join(matched_keywords)} | Titolo: {news['title']}")
        channels = notifier.send_alert(user, news, matched_keywords)
        if channels:
            notified += 1
            if user.get("id") and news.get("id"):
                for ch in channels:
                    record_delivery(user["id"], news["id"], ch, "alert")
    return notified


def fetch_source(source, followers=None, notify=True):
    """Legge una fonte, salva le news nuove e (se notify) avvisa i follower.
    Ritorna il numero di news nuove."""
    followers = followers or []
    try:
        items = read_source(source)
    except SourceError as e:
        log(f"⚠️ Fonte non leggibile: {source['name']} ({e})")
        record_source_failure(source["id"], e)
        return 0
    except Exception as e:
        log(f"❌ Errore lettura fonte {source['name']}: {e}")
        record_source_failure(source["id"], e)
        return 0

    new_count = 0
    for item in items:
        news_id = add_news(item["title"], item["link"], source["name"], item["published"], item["content"],
                           source_id=source["id"])
        if not news_id:
            continue  # news già presente → niente notifica
        new_count += 1

        if notify and followers:
            news = {**item, "id": news_id, "source": source["name"], "source_id": source["id"]}
            try:
                notify_users(followers, news)
            except Exception as e:
                log(f"❌ Errore notifica per '{item['title']}': {e}")
    record_source_success(source["id"], len(items), new_count)
    return new_count


def fetch_news():
    """Scarica tutte le fonti attive, salva le news nuove e notifica gli utenti
    che seguono ciascuna fonte. Ritorna il numero di news nuove."""
    sources = get_sources()
    followers_map = get_followers_map(get_users())

    total = 0
    for source in sources:
        total += fetch_source(source, followers=followers_map.get(source["id"], []))

    if total:
        log(f"➕ Aggiunte {total} nuove notizie da {len(sources)} fonti.")
    return total
