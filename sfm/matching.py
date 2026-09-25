"""Matching keyword ↔ notizie: logica pura, senza dipendenze da DB o canali."""
from sfm.utils import find_matching_keywords, strip_html


def news_text(news):
    """Testo su cui cercare le keyword: titolo + contenuto senza HTML."""
    return f"{news.get('title') or ''} {strip_html(news.get('content') or '')}"


def is_excluded(news, user, text=None):
    """True se la notizia contiene una delle parole da escludere dell'utente: in quel caso
    non gli arriva, né come avviso né nel riepilogo, anche se ha una sua parola chiave."""
    words = user.get("excluded") or []
    return bool(words) and bool(find_matching_keywords(text if text is not None else news_text(news), words))


def match_users(news, users):
    """Per una notizia e una lista di utenti ({keywords: [...], excluded: [...]}) ritorna
    [(user, [keyword, ...]), ...] per i soli utenti con almeno una keyword nel testo
    e nessuna parola da escludere."""
    text = news_text(news)
    matches = []
    for user in users:
        if is_excluded(news, user, text):
            continue
        matched = find_matching_keywords(text, user.get("keywords") or [])
        if matched:
            matches.append((user, matched))
    return matches
