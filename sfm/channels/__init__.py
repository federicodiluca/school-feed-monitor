"""Canali di notifica. Ogni canale è un modulo che espone:
    NAME                                      -> identificativo del canale
    send_alert(user, news, matched_keywords)  -> notifica immediata su una notizia
    send_digest(user, news_list)              -> report/riepilogo (lista anche vuota)
"""
