import sfm.db as db
from sfm.db_news import add_news, get_recent_news
from sfm.db_sources import (
    add_user_source,
    get_followed_source_ids,
    get_followers_map,
    get_source,
    get_source_by_url,
    get_sources,
    get_user_sources,
    remove_source,
    set_user_source,
    sync_config_sources,
)
from sfm.db_user import add_user, get_users

# conftest sincronizza già le due fonti di TEST_CONFIG (id 1 e 2)


def test_sync_creates_config_sources_with_default_follow():
    sources = get_sources()
    assert [(s["id"], s["name"], s["url"], s["type"], s["origin"], s["default_follow"]) for s in sources] == [
        (1, "Feed Uno", "https://example.org/uno/feed/", "rss", "config", True),
        (2, "Feed Due", "https://example.org/due/feed/", "rss", "config", True),
    ]


def test_sync_returns_count_and_newly_created_ids():
    count, created = sync_config_sources([
        {"name": "Feed Uno", "url": "https://example.org/uno/feed/"},
        {"name": "Nuova", "url": "https://example.org/nuova/feed/"},
    ])
    assert count == 2 and created == [3]
    assert sync_config_sources([{"name": "Nuova", "url": "https://example.org/nuova/feed/"}]) == (1, [])


def test_sync_is_idempotent_updates_names_and_disables_removed():
    sync_config_sources([{"name": "Uno rinominato", "url": "https://example.org/uno/feed/"}])
    enabled = get_sources()
    assert [(s["id"], s["name"]) for s in enabled] == [(1, "Uno rinominato")]
    assert get_source(2)["enabled"] is False
    # ricompare in config → riabilitata, stesso id
    sync_config_sources([{"name": "Uno", "url": "https://example.org/uno/feed/"}, {"name": "Due", "url": "https://example.org/due/feed/"}])
    assert [s["id"] for s in get_sources()] == [1, 2]


def test_sync_does_not_touch_user_sources():
    add_user_source("Custom", "https://custom.org/feed/", "rss", user_id=1)
    sync_config_sources([{"name": "Feed Uno", "url": "https://example.org/uno/feed/"}])
    assert get_source_by_url("https://custom.org/feed/")["enabled"] is True


def test_sync_links_legacy_news_by_source_name():
    conn = db.get_conn()
    conn.execute("INSERT INTO news (title, link, source, published_at) VALUES ('old', 'https://x/old', 'Feed Due', datetime('now'))")
    conn.commit()
    conn.close()
    sync_config_sources([{"name": "Feed Uno", "url": "https://example.org/uno/feed/"}, {"name": "Feed Due", "url": "https://example.org/due/feed/"}])
    assert get_recent_news()[0]["source_id"] == 2


def test_add_user_source_is_opt_in_for_others_and_followed_by_creator():
    add_user(1)
    add_user(2)
    source, created = add_user_source("Marche", "https://mim.example/marche", "html", user_id=1)
    assert created is True
    assert source["origin"] == "user" and source["added_by"] == 1 and source["default_follow"] is False
    assert get_followed_source_ids(1) == {1, 2, source["id"]}
    assert get_followed_source_ids(2) == {1, 2}

    # stessa url di nuovo: non crea, fa seguire
    same, created = add_user_source("altro nome", "https://mim.example/marche", "html", user_id=2)
    assert created is False and same["id"] == source["id"] and same["name"] == "Marche"
    assert get_followed_source_ids(2) == {1, 2, source["id"]}


def test_follow_unfollow_overrides_and_list():
    add_user(1)
    set_user_source(1, 2, False)
    assert get_followed_source_ids(1) == {1}
    assert [(s["id"], s["followed"]) for s in get_user_sources(1)] == [(1, True), (2, False)]
    set_user_source(1, 2, True)
    assert get_followed_source_ids(1) == {1, 2}


def test_remove_source_rules():
    add_user(1)
    add_user(2)
    source, _ = add_user_source("Custom", "https://custom.org/", "html", user_id=1)
    set_user_source(2, source["id"], True)

    assert remove_source(1) is False                      # fonte di config
    assert remove_source(source["id"], user_id=2) is False  # non è chi l'ha aggiunta
    assert remove_source(999) is False
    assert remove_source(source["id"], user_id=1) is True
    assert get_source(source["id"])["enabled"] is False
    assert get_followed_source_ids(2) == {1, 2}
    # riaggiunta: stesso id, riabilitata
    again, created = add_user_source("Custom", "https://custom.org/", "html", user_id=2)
    assert created is False and again["id"] == source["id"] and again["enabled"] is True


def test_followers_map():
    add_user(10)   # id 1
    add_user(20)   # id 2
    add_user(30)   # id 3
    custom, _ = add_user_source("Custom", "https://custom.org/", "rss", user_id=3)
    set_user_source(2, 1, False)
    users = get_users()
    fmap = get_followers_map(users)
    ids = lambda sid: sorted(u["telegram_id"] for u in fmap[sid])
    assert ids(1) == [10, 30]
    assert ids(2) == [10, 20, 30]
    assert ids(custom["id"]) == [30]


def test_news_filter_by_source_ids():
    add_news("a", "https://x/a", "Feed Uno", "", source_id=1)
    add_news("b", "https://x/b", "Feed Due", "", source_id=2)
    add_news("c", "https://x/c", "Legacy", "", source_id=None)
    assert {r["title"] for r in get_recent_news()} == {"a", "b", "c"}
    assert {r["title"] for r in get_recent_news(source_ids={1})} == {"a"}
    assert {r["title"] for r in get_recent_news(source_ids={1, 2})} == {"a", "b"}
    assert get_recent_news(source_ids=set()) == []


def test_sync_applies_type_and_default_follow_from_config():
    sync_config_sources([
        {"name": "Feed Uno", "url": "https://example.org/uno/feed/"},
        {"name": "Marche", "url": "https://mim.example/novita", "type": "html", "default_follow": False},
    ])
    marche = get_source_by_url("https://mim.example/novita")
    assert marche["type"] == "html" and marche["origin"] == "config" and marche["default_follow"] is False
    add_user(1)
    assert get_followed_source_ids(1) == {1}          # opt-in: non seguita di default
    set_user_source(1, marche["id"], True)
    assert marche["id"] in get_followed_source_ids(1)
    # cambio in config → aggiornato al sync successivo
    sync_config_sources([{"name": "Marche", "url": "https://mim.example/novita", "type": "html", "default_follow": True}])
    assert get_source_by_url("https://mim.example/novita")["default_follow"] is True
