"""Anteprima presa dalla pagina della notizia, quando la pagina-elenco dà solo il titolo."""
import sfm.news_fetcher as news_fetcher
from sfm.db_news import get_recent_news
from sfm.db_sources import add_user_source
from sfm.db_user import add_user, update_keywords
from sfm.source_parser import article_preview
from tests.fixtures import html_list_page

TITLE = "Interpello DSGA a.s. 2026/27"
GOOD = ("Si pubblica il secondo interpello per il conferimento degli incarichi di Direttore dei servizi "
        "generali e amministrativi nelle scuole della provincia, con scadenza il 30 settembre.")


def page(body, head=""):
    return f"<html><head>{head}</head><body><nav><p>{'Voce Menu ' * 12}</p></nav>{body}" \
           f"<footer><p>Indirizzo PEC usp@postacert.istruzione.it — tutti i diritti riservati</p></footer></body></html>"


def test_takes_the_first_real_paragraph_of_the_article():
    assert article_preview(page(f"<article><h1>{TITLE}</h1><p>{GOOD}</p></article>"), TITLE) == GOOD


def test_prefers_a_meaningful_meta_description():
    head = f'<meta property="og:description" content="{GOOD}">'
    assert article_preview(page("<article><p>Altro testo qualunque</p></article>", head), TITLE) == GOOD


def test_ignores_a_description_that_just_repeats_the_title():
    head = f'<meta name="description" content="{TITLE}">'
    assert article_preview(page(f"<main><p>{GOOD}</p></main>", head), TITLE) == GOOD


def test_rejects_attachments_protocol_numbers_menus_and_contacts():
    noise = [
        "m_pi.AOOUSPCA.REGISTRO DECRETI(R).0000803.18-09-2026-suppl.pdf allegato al presente avviso di pubblicazione",
        "Il documento è acquisito al N. di protocollo AOO USPSO R.D. 231 del 16/09/2026 e pubblicato in data odierna",
        "AT Comunica Cessazioni Diritto Allo Studio Mobilità Organici Reclutamento Sostegno Utilizzazioni Albo Graduatorie",
        "Per informazioni scrivere a usp.ta@istruzione.it oppure telefonare all'ufficio negli orari di apertura al pubblico",
    ]
    for text in noise:
        assert article_preview(page(f"<article><p>{text}</p></article>"), TITLE) == "", text


def test_long_text_is_clipped_on_a_word():
    text = article_preview(page(f"<article><p>{GOOD} {GOOD} {GOOD} {GOOD}</p></article>"), TITLE)
    assert len(text) <= 401 and text.endswith("…")


def _html_source(fake_sources, abstract=""):
    add_user(1)                                            # la fonte la aggiunge (e la segue) l'utente 1
    source, _ = add_user_source("USP Prova", "https://usp.example/news", "html", user_id=1)
    fake_sources["https://usp.example/news"] = html_list_page(
        [{"title": TITLE, "link": "/n/1", "abstract": abstract},
         {"title": "Nomine in ruolo", "link": "/n/2", "abstract": abstract}],
        base="https://usp.example")
    return source


def test_new_html_news_get_the_preview_before_the_alert(fake_sources, sent_messages):
    _html_source(fake_sources)
    update_keywords(1, ["scadenza"])                        # c'è solo nel testo della pagina, non nel titolo
    fake_sources["https://usp.example/n/1"] = page(f"<article><p>{GOOD}</p></article>")
    news_fetcher.fetch_news()
    stored = {n["link"]: n["content"] for n in get_recent_news()}
    assert stored["https://usp.example/n/1"] == GOOD
    assert stored["https://usp.example/n/2"] == ""          # pagina irraggiungibile: niente anteprima, nessun errore
    assert any(TITLE in m["text"] for m in sent_messages)   # l'avviso è partito grazie all'anteprima


def test_text_repeated_on_every_page_is_site_boilerplate(fake_sources, sent_messages):
    _html_source(fake_sources)
    about = ("L'Ufficio IV Ambito Territoriale realizza la presenza dell'Amministrazione a livello provinciale "
             "e facilita i rapporti con le istituzioni scolastiche del territorio.")
    fake_sources["https://usp.example/n/1"] = page(f"<main><p>{about}</p></main>")
    fake_sources["https://usp.example/n/2"] = page(f"<main><p>{about}</p></main>")
    news_fetcher.fetch_news()
    assert all(n["content"] == "" for n in get_recent_news())


def test_news_with_an_abstract_are_not_opened(fake_sources, sent_messages):
    _html_source(fake_sources, abstract=GOOD)
    news_fetcher.fetch_news()
    assert not any("/n/" in url for url in fake_sources["__calls__"])
