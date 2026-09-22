"""Preferenze dell'utente salvate SOLO nel suo browser (cookie).

Il server non conserva nulla: legge il cookie a ogni richiesta per filtrare le notizie
ed evidenziare le parole chiave. Cookie tecnici, impostati su richiesta esplicita
dell'utente: non serve un banner.
"""
from flask import request

COOKIE_SOURCES = "sfm_fonti"
COOKIE_KEYWORDS = "sfm_parole"
MAX_AGE = 60 * 60 * 24 * 365          # un anno
MAX_KEYWORDS = 30
MAX_KEYWORD_LEN = 60


def selected_source_ids(req=None):
    """Insieme degli id delle fonti scelte (vuoto se il cookie non c'è)."""
    raw = (req or request).cookies.get(COOKIE_SOURCES, "")
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


def selected_keywords(req=None):
    raw = (req or request).cookies.get(COOKIE_KEYWORDS, "")
    return [k.strip() for k in raw.split(",") if k.strip()][:MAX_KEYWORDS]


def has_preferences(req=None):
    return bool(selected_source_ids(req) or selected_keywords(req))


def clean_keywords(keywords):
    out = []
    for k in keywords:
        k = (k or "").strip()[:MAX_KEYWORD_LEN]
        if k and k.lower() not in {x.lower() for x in out}:
            out.append(k)
    return out[:MAX_KEYWORDS]


def store(response, source_ids, keywords):
    """Scrive i cookie sulla risposta. source_ids/keywords vuoti = cookie cancellati."""
    _set(response, COOKIE_SOURCES, ",".join(str(int(s)) for s in sorted(set(source_ids))))
    _set(response, COOKIE_KEYWORDS, ",".join(clean_keywords(keywords)))
    return response


def forget(response):
    return store(response, [], [])


def _set(response, name, value):
    if value:
        response.set_cookie(name, value, max_age=MAX_AGE, samesite="Lax", httponly=False,
                            secure=request.is_secure, path="/")
    else:
        response.delete_cookie(name, path="/")
