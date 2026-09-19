from sfm.db import get_conn


def _row_to_source(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "url": row["url"],
        "type": row["type"],
        "origin": row["origin"],
        "added_by": row["added_by"],
        "enabled": bool(row["enabled"]),
        "default_follow": bool(row["default_follow"]),
        "kind": row["kind"] or "other",
        "region": row["region"],
        "province": row["province"],
    }


def sync_config_sources(sites):
    """Allinea le fonti di config.json con la tabella sources.
    Le fonti di config non più presenti vengono disabilitate (non cancellate,
    così le news collegate restano consistenti).
    Ritorna (numero di fonti da config, lista degli id delle fonti create ora)."""
    conn = get_conn()
    cur = conn.cursor()
    urls = []
    created_ids = []
    for site in sites:
        url = site["url"].strip()
        name = (site.get("name") or url).strip()
        source_type = site.get("type") or "rss"
        default_follow = 1 if site.get("default_follow", True) else 0
        kind = site.get("kind") or "other"
        region, province = site.get("region"), site.get("province")
        urls.append(url)
        cur.execute("SELECT id FROM sources WHERE url=?", (url,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE sources SET name=?, type=?, origin='config', enabled=1, default_follow=?, kind=?, region=?, province=? WHERE id=?",
                (name, source_type, default_follow, kind, region, province, row["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO sources (name, url, type, origin, enabled, default_follow, kind, region, province) "
                "VALUES (?, ?, ?, 'config', 1, ?, ?, ?, ?)",
                (name, url, source_type, default_follow, kind, region, province),
            )
            created_ids.append(cur.lastrowid)
    if urls:
        placeholders = ",".join("?" * len(urls))
        cur.execute(f"UPDATE sources SET enabled=0 WHERE origin='config' AND url NOT IN ({placeholders})", urls)
    else:
        cur.execute("UPDATE sources SET enabled=0 WHERE origin='config'")

    # Migrazione: collega le news vecchie (senza source_id) alla fonte con lo stesso nome
    cur.execute("""
        UPDATE news SET source_id = (SELECT id FROM sources s WHERE s.name = news.source LIMIT 1)
        WHERE source_id IS NULL
    """)
    conn.commit()
    conn.close()
    return len(urls), created_ids


def get_sources(enabled_only=True):
    conn = get_conn()
    cur = conn.cursor()
    if enabled_only:
        cur.execute("SELECT * FROM sources WHERE enabled=1 ORDER BY id")
    else:
        cur.execute("SELECT * FROM sources ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_source(r) for r in rows]


def get_source(source_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources WHERE id=?", (source_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_source(row) if row else None


def get_source_by_url(url):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources WHERE url=?", (url.strip(),))
    row = cur.fetchone()
    conn.close()
    return _row_to_source(row) if row else None


def add_user_source(name, url, source_type, user_id):
    """Aggiunge una fonte custom (opt-in per gli altri, seguita da chi la aggiunge).
    Se l'URL esiste già (anche disabilitata) la riabilita e la fa seguire all'utente.
    Ritorna (source, created)."""
    url = url.strip()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM sources WHERE url=?", (url,))
    row = cur.fetchone()
    if row:
        source_id = row["id"]
        cur.execute("UPDATE sources SET enabled=1 WHERE id=?", (source_id,))
        created = False
    else:
        cur.execute(
            "INSERT INTO sources (name, url, type, origin, added_by, enabled, default_follow) VALUES (?, ?, ?, 'user', ?, 1, 0)",
            (name.strip(), url, source_type, user_id),
        )
        source_id = cur.lastrowid
        created = True
    cur.execute(
        "INSERT OR REPLACE INTO user_sources (user_id, source_id, follow) VALUES (?, ?, 1)",
        (user_id, source_id),
    )
    conn.commit()
    conn.close()
    return get_source(source_id), created


def remove_source(source_id, user_id=None):
    """Disabilita una fonte custom. Se user_id è dato, deve essere chi l'ha aggiunta.
    Ritorna True se rimossa, False altrimenti (fonte di config, inesistente o non propria)."""
    source = get_source(source_id)
    if not source or source["origin"] != "user":
        return False
    if user_id is not None and source["added_by"] != user_id:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sources SET enabled=0 WHERE id=?", (source_id,))
    cur.execute("DELETE FROM user_sources WHERE source_id=?", (source_id,))
    conn.commit()
    conn.close()
    return True


def set_user_source(user_id, source_id, follow):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO user_sources (user_id, source_id, follow) VALUES (?, ?, ?)",
        (user_id, source_id, 1 if follow else 0),
    )
    conn.commit()
    conn.close()


def _overrides():
    """{user_id: {source_id: follow}}"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, source_id, follow FROM user_sources")
    out = {}
    for r in cur.fetchall():
        out.setdefault(r["user_id"], {})[r["source_id"]] = bool(r["follow"])
    conn.close()
    return out


def _effective(source, override):
    if override is not None:
        return override
    return source["default_follow"]


def get_user_sources(user_id, enabled_only=True):
    """Lista delle fonti con il flag 'followed' calcolato per l'utente
    (user_id=None → solo i default delle fonti)."""
    overrides = _overrides().get(user_id, {})
    result = []
    for s in get_sources(enabled_only=enabled_only):
        s = dict(s)
        s["followed"] = _effective(s, overrides.get(s["id"]))
        result.append(s)
    return result


def get_followed_source_ids(user_id):
    return {s["id"] for s in get_user_sources(user_id) if s["followed"]}


def get_followers_map(users):
    """Per una lista di utenti ({id,...}) ritorna {source_id: [user, ...]}
    con soli utenti che seguono la fonte. Una sola query per gli override."""
    overrides = _overrides()
    sources = get_sources()
    out = {s["id"]: [] for s in sources}
    for user in users:
        user_over = overrides.get(user["id"], {})
        for s in sources:
            if _effective(s, user_over.get(s["id"])):
                out[s["id"]].append(user)
    return out


def follow_area(user_id, region, provinces=()):
    """Imposta le fonti seguite dall'utente in base all'area (regione + province):
    segue nazionali + USR + USP dell'area, smette di seguire USR/USP di altre aree,
    non tocca le fonti custom ('other'). Ritorna il numero di fonti seguite."""
    from sfm.catalog import sources_for_area
    sources = get_sources()
    chosen = {s["id"] for s in sources_for_area(sources, region, provinces)}
    conn = get_conn()
    cur = conn.cursor()
    for s in sources:
        if s["kind"] in ("usr", "usp", "mim"):
            cur.execute("INSERT OR REPLACE INTO user_sources (user_id, source_id, follow) VALUES (?, ?, ?)",
                        (user_id, s["id"], 1 if s["id"] in chosen else 0))
    conn.commit()
    conn.close()
    return len(chosen)


def user_area(user_id):
    """(regione, [province]) dedotte dalle fonti USR/USP seguite, oppure (None, [])."""
    from sfm.catalog import provinces_of
    followed = [s for s in get_user_sources(user_id) if s["followed"] and s["kind"] in ("usr", "usp")]
    regions = sorted({s["region"] for s in followed if s.get("region")})
    if not regions:
        return None, []
    region = regions[0]
    provinces = sorted({p for s in followed if s["kind"] == "usp" and s.get("region") == region for p in provinces_of(s)})
    return region, provinces
