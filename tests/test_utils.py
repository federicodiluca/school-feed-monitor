from datetime import datetime, timezone

import pytest

from sfm.utils import (
    cleanHTMLPreview,
    escape_html,
    find_matching_keywords,
    normalize_text,
    parse_keywords,
    parse_rss_datetime,
    strip_html,
)


# --- normalize_text -------------------------------------------------------

def test_normalize_text_replaces_typographic_apostrophes():
    assert normalize_text("l’uso dell‘arte") == "l'uso dell'arte"
    assert normalize_text("“virgolette”") == '"virgolette"'
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


# --- strip_html / cleanHTMLPreview / escape_html --------------------------

def test_strip_html_removes_tags_and_joins_with_spaces():
    assert strip_html("<p>Ciao</p><p>mondo</p>") == "Ciao mondo"
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_clean_html_preview_truncates_and_escapes():
    long_text = "<div>" + "a" * 500 + "</div>"
    preview = cleanHTMLPreview(long_text)
    assert preview == "a" * 400 + "..."

    assert cleanHTMLPreview("<b>Tom &amp; Jerry</b> <i>1 < 2</i>") == "Tom &amp; Jerry 1 &lt; 2"


def test_escape_html_handles_none_and_special_chars():
    assert escape_html(None) == ""
    assert escape_html('a & b < c > "d"') == "a &amp; b &lt; c &gt; &quot;d&quot;"
    assert escape_html(42) == "42"


# --- parse_keywords -------------------------------------------------------

def test_parse_keywords_splits_and_strips():
    assert parse_keywords(" scuola , docenti,GRADUATORIA FINALE ,, ") == ["scuola", "docenti", "GRADUATORIA FINALE"]
    assert parse_keywords("") == []
    assert parse_keywords(None) == []
    assert parse_keywords(" , , ") == []


def test_parse_keywords_normalizes_apostrophes():
    assert parse_keywords("l’aquila") == ["l'aquila"]


# --- find_matching_keywords ----------------------------------------------

@pytest.mark.parametrize("text, keyword, expected", [
    ("Concorso docenti 2025", "docenti", True),
    ("Crowe è arrivato", "Rowe", False),          # non deve matchare dentro un'altra parola
    ("Ademir vince", "Demir", False),
    ("Demir vince", "demir", True),               # case-insensitive
    ("GRADUATORIA FINALE pubblicata", "graduatoria finale", True),  # parola composta
    ("graduatoria  finale", "graduatoria finale", False),           # doppio spazio: non è la stessa frase
    ("Classe di concorso A041.", "A041", True),  # punteggiatura adiacente
    ("Corso di C++ base", "C++", True),           # simboli in coda: \b fallirebbe
    ("Trasferimenti docenti", "trasferiment", False),  # prefisso non basta
    ("L’aquila vola", "l'aquila", True),     # apostrofo tipografico nel testo
])
def test_find_matching_keywords(text, keyword, expected):
    result = find_matching_keywords(text, [keyword])
    assert (result == [keyword]) is expected


def test_find_matching_keywords_returns_original_form_and_skips_blanks():
    assert find_matching_keywords("scuola e docenti", ["Docenti", "", "  ", "scuola", "prova"]) == ["Docenti", "scuola"]
    assert find_matching_keywords("", ["a"]) == []
    assert find_matching_keywords(None, ["a"]) == []


# --- parse_rss_datetime ---------------------------------------------------

def test_parse_rss_datetime_rfc2822_utc():
    assert parse_rss_datetime("Mon, 29 Sep 2025 10:05:28 +0000") == "2025-09-29 10:05:28"


def test_parse_rss_datetime_rfc2822_with_offset_converted_to_utc():
    assert parse_rss_datetime("Mon, 29 Sep 2025 12:05:28 +0200") == "2025-09-29 10:05:28"


def test_parse_rss_datetime_iso_with_z_and_offset():
    assert parse_rss_datetime("2025-10-05T10:00:00Z") == "2025-10-05 10:00:00"
    assert parse_rss_datetime("2025-10-05T12:00:00+02:00") == "2025-10-05 10:00:00"


def test_parse_rss_datetime_naive_is_treated_as_local_time():
    local_tz = datetime.now().astimezone().tzinfo
    expected = datetime(2025, 10, 5, 12, 0, 0, tzinfo=local_tz).astimezone(timezone.utc)
    assert parse_rss_datetime("2025-10-05T12:00:00") == expected.strftime("%Y-%m-%d %H:%M:%S")


def test_parse_rss_datetime_falls_back_to_now_for_empty_or_garbage():
    now = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_rss_datetime("", now=now) == "2025-01-02 03:04:05"
    assert parse_rss_datetime(None, now=now) == "2025-01-02 03:04:05"
    assert parse_rss_datetime("non è una data", now=now) == "2025-01-02 03:04:05"


# --- local_day_bounds_utc / format_local_datetime ------------------------

def test_local_day_bounds_utc_converts_local_day_to_utc_range():
    from datetime import timedelta
    from sfm.utils import local_day_bounds_utc
    now = datetime(2025, 10, 5, 1, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert local_day_bounds_utc(now) == ("2025-10-04 22:00:00", "2025-10-05 22:00:00")
    now = datetime(2025, 10, 5, 23, 30, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert local_day_bounds_utc(now) == ("2025-10-05 05:00:00", "2025-10-06 05:00:00")


def test_local_day_bounds_utc_default_contains_now():
    from sfm.utils import local_day_bounds_utc
    start, end = local_day_bounds_utc()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert start <= now_utc < end


def test_format_local_datetime():
    from sfm.utils import format_local_datetime
    expected = datetime(2025, 10, 5, 10, 0, 0, tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    assert format_local_datetime("2025-10-05 10:00:00") == expected
    assert format_local_datetime("") == ""
    assert format_local_datetime(None) == ""
    assert format_local_datetime("boh") == "boh"
