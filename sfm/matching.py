"""Matching keyword ↔ notizie: logica pura, senza dipendenze da DB o canali."""
from sfm.utils import find_matching_keywords, strip_html


def news_text(news):
    """Testo su cui cercare le keyword: titolo + contenuto senza HTML."""
    return f"{news.get('title') or ''} {strip_html(news.get('content') or '')}"


def match_users(news, users):
    """Per una notizia e una lista di utenti ({keywords: [...], ...}) ritorna
    [(user, [keyword, ...]), ...] per i soli utenti con almeno una keyword nel testo."""
    text = news_text(news)
    matches = []
    for user in users:
        matched = find_matching_keywords(text, user.get("keywords") or [])
        if matched:
            matches.append((user, matched))
    return matches
