import sqlite3
from datetime import datetime, timedelta, timezone
from hiris.app.brain.knowledge_store import KnowledgeStore

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def test_init_creates_tables(tmp_path):
    """Un database nuovo non deve MAI far nascere `knowledge_links`: e' stata
    tolta dallo schema (Task 8, fetta 2a) insieme al tool `link_knowledge`
    che era il suo unico scrittore -- una tabella che nessuno interrogava."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    conn = sqlite3.connect(str(tmp_path / "brain.db"))
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "knowledge_items" in names
    assert "knowledge_links" not in names
    store.close()


def test_db_nuovo_parte_gia_alla_versione_corrente_senza_migrazioni(tmp_path):
    """Caso 1 (brief Task 8): un database nuovo non ha tabelle prima
    dell'init, quindi `init_schema` deve stampare direttamente la versione
    piu' recente (6, Task 6 memoria non evapora ha aggiunto `_migrate_v6`)
    senza far girare `_migrate_v4` -- non c'e' nulla da droppare perche'
    `knowledge_links` non e' mai nata."""
    db_path = tmp_path / "fresh.db"
    store = KnowledgeStore(str(db_path))
    conn = sqlite3.connect(str(db_path))
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 6
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "knowledge_links" not in names
    store.close()


def test_db_esistente_alla_v3_perde_knowledge_links_alla_riapertura(tmp_path):
    """Caso 2 (brief Task 8): un database che era gia' alla versione 3 (con
    `knowledge_links` popolata da un `link_knowledge` chiamato prima di
    questa fetta) deve, alla prossima apertura, far girare la migrazione
    v3->v4 e perdere la tabella -- non e' una perdita, perche' nulla la
    leggeva (`neighbors` era l'unico lettore ed e' gia' stato tolto)."""
    db_path = tmp_path / "old.db"

    # Simula un database alla v3, con knowledge_links presente e popolata,
    # cosi' come l'avrebbe lasciato una KnowledgeStore di prima di questa
    # fetta -- senza passare da KnowledgeStore (che oggi non crea piu' la
    # tabella), per riprodurre fedelmente lo stato di un'installazione reale.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE knowledge_items ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,"
        " owner TEXT NOT NULL DEFAULT 'home', title TEXT NOT NULL DEFAULT '',"
        " content TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',"
        " amount REAL, due_date TEXT, category TEXT, embedding BLOB,"
        " sensitivity TEXT NOT NULL DEFAULT 'normal',"
        " source TEXT NOT NULL DEFAULT 'manual', source_ref TEXT,"
        " confidence REAL NOT NULL DEFAULT 1.0,"
        " status TEXT NOT NULL DEFAULT 'approved',"
        " valid_from TEXT, valid_until TEXT,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        " chatbot_id TEXT)"
    )
    conn.execute(
        "CREATE TABLE knowledge_links ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, src_id INTEGER NOT NULL,"
        " dst_id INTEGER NOT NULL, relation TEXT NOT NULL,"
        " weight REAL NOT NULL DEFAULT 1.0,"
        " source TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL,"
        " UNIQUE(src_id, dst_id, relation))"
    )
    conn.execute(
        "INSERT INTO knowledge_links"
        "(src_id, dst_id, relation, weight, source, created_at)"
        " VALUES(1, 2, 'riguarda', 1.0, 'inferred', '2026-01-01T00:00:00Z')"
    )
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    # Riapertura tramite la classe reale: e' qui che devono girare le
    # migrazioni v3->v4->v5->v6 in sequenza.
    store = KnowledgeStore(str(db_path))
    conn = sqlite3.connect(str(db_path))
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 6
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "knowledge_links" not in names
    store.close()


def test_migrate_v6_azzera_valid_until_dei_ricordi_scaduti_e_orfani(tmp_path):
    """Task 6 (memoria non evapora): un database gia' alla v5 puo' avere
    righe kind='memory' con `valid_until` scritto dal vecchio calcolo di
    retention (handle_save_memory, rimosso in questa fetta). Due varianti,
    entrambe reali in produzione:

    - una riga ANCORA legata a un chatbot, con `valid_until` gia' passato
      (scaduta "normale" sotto il vecchio schema);
    - una riga GIA' distaccata dal suo chatbot (`chatbot_id` azzerato da
      `detach_chatbot_id`/`_migrate_v5`) ma con `valid_until` ancora
      impostato e gia' passato -- la riga "immortale e invisibile" del
      brief: `_clausole_di_scope` la nasconde su ogni lettura, e
      `purge_expired_chatbot` (che cercava per chatbot) non la trovava mai,
      quindi restava per sempre nel database, illeggibile.

    Alla riapertura (v5 -> v6) entrambe devono tornare leggibili: la
    migrazione azzera `valid_until` su ogni riga kind='memory', a
    prescindere da chatbot_id."""
    db_path = tmp_path / "prod_shaped.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE knowledge_items ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,"
        " owner TEXT NOT NULL DEFAULT 'home', title TEXT NOT NULL DEFAULT '',"
        " content TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',"
        " amount REAL, due_date TEXT, category TEXT, embedding BLOB,"
        " sensitivity TEXT NOT NULL DEFAULT 'normal',"
        " source TEXT NOT NULL DEFAULT 'manual', source_ref TEXT,"
        " confidence REAL NOT NULL DEFAULT 1.0,"
        " status TEXT NOT NULL DEFAULT 'approved',"
        " valid_from TEXT, valid_until TEXT,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        " chatbot_id TEXT)"
    )
    past = (datetime.now(timezone.utc) - timedelta(days=400)).strftime(_TS_FMT)
    now = datetime.now(timezone.utc).strftime(_TS_FMT)
    conn.execute(
        "INSERT INTO knowledge_items"
        " (kind, owner, content, status, valid_until, chatbot_id, created_at, updated_at)"
        " VALUES ('memory','home','ancora agganciata, scaduta','approved',?,'hiris-default',?,?)",
        (past, now, now),
    )
    conn.execute(
        "INSERT INTO knowledge_items"
        " (kind, owner, content, status, valid_until, chatbot_id, created_at, updated_at)"
        " VALUES ('memory','home','immortale e invisibile','approved',?,NULL,?,?)",
        (past, now, now),
    )
    # Un fatto (non memory) con una vera validita' non deve essere toccato.
    conn.execute(
        "INSERT INTO knowledge_items"
        " (kind, owner, content, status, valid_until, chatbot_id, created_at, updated_at)"
        " VALUES ('fact','home','scadenza reale del fatto','approved',?,NULL,?,?)",
        (past, now, now),
    )
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    store = KnowledgeStore(str(db_path))
    agganciata = [i for i in store.list_items(kind="memory", limit=200)
                  if i["content"] == "ancora agganciata, scaduta"][0]
    orfana = [i for i in store.list_items(kind="memory", limit=200)
              if i["content"] == "immortale e invisibile"][0]
    fatto = [i for i in store.list_items(kind="fact", limit=200)][0]
    assert agganciata["valid_until"] is None
    assert orfana["valid_until"] is None
    assert fatto["valid_until"] == past, (
        "la migrazione tocca solo kind='memory': la validita' di un fatto "
        "vero non e' retention e va lasciata in pace"
    )

    # Ed entrambe tornano visibili sui percorsi di lettura scopati (non solo
    # list_items, che non filtra su valid_until).
    visibili = {r["content"] for r in store.recent(owner="home", k=10)}
    assert "ancora agganciata, scaduta" in visibili
    assert "immortale e invisibile" in visibili
    store.close()


def test_add_and_get_item(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    item_id = store.add_item(
        kind="preference", owner="home",
        title="Intolleranza lattosio",
        content="Paolo è intollerante al lattosio",
        embedding=[0.1, 0.2, 0.3],
        sensitivity="normal", source="manual", status="approved",
    )
    got = store.get_item(item_id)
    assert got["kind"] == "preference"
    assert got["content"] == "Paolo è intollerante al lattosio"
    assert got["status"] == "approved"
    store.close()


def test_list_approve_delete(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="proposto", status="pending")
    assert [i["id"] for i in store.list_items(status="pending")] == [pid]
    store.approve(pid)
    assert store.get_item(pid)["status"] == "approved"
    assert store.list_items(status="pending") == []
    store.delete_item(pid)
    assert store.get_item(pid) is None
    store.close()


def test_list_items_owner_scoping_includes_home(tmp_path):
    """owner filter on list_items must mean 'this owner OR home', mirroring
    search()'s unified scoping (review B/#16 IDOR fix)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A", owner="userA", status="pending")
    b_id = store.add_item(kind="fact", content="B", owner="userB", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")

    ids_for_a = {i["id"] for i in store.list_items(status="pending", owner="userA")}
    assert ids_for_a == {a_id, home_id}
    assert b_id not in ids_for_a

    store.close()


def test_approve_rejects_cross_owner_and_leaves_item_unchanged(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A", owner="userA", status="pending")

    ok = store.approve(a_id, owner="userB")
    assert ok is False
    assert store.get_item(a_id)["status"] == "pending"

    ok2 = store.approve(a_id, owner="userA")
    assert ok2 is True
    assert store.get_item(a_id)["status"] == "approved"

    store.close()


def test_approve_allows_home_item_for_any_owner(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    ok = store.approve(home_id, owner="anyUser")
    assert ok is True
    assert store.get_item(home_id)["status"] == "approved"
    store.close()


def test_delete_item_rejects_cross_owner_and_leaves_item_unchanged(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A", owner="userA", status="pending")

    ok = store.delete_item(a_id, owner="userB")
    assert ok is False
    assert store.get_item(a_id) is not None

    ok2 = store.delete_item(a_id, owner="userA")
    assert ok2 is True
    assert store.get_item(a_id) is None

    store.close()


def test_delete_item_purges_document_chunks(tmp_path):
    """Backlog #5: delete_item must also drop the item's document_chunks, so a
    deleted document leaves no orphan chunks (the Mayan ingest rollback relies
    on this)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    item_id = store.add_item(kind="document", content="Doc", owner="home",
                             source="mayan", source_ref="900", status="approved")
    store.add_document_chunk(item_id=item_id, mayan_doc_id="900",
                             chunk_index=0, content="pezzo", embedding=[0.1, 0.2])
    assert store._conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE item_id=?", (item_id,)
    ).fetchone()[0] == 1

    assert store.delete_item(item_id) is True
    assert store._conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE item_id=?", (item_id,)
    ).fetchone()[0] == 0
    store.close()


def test_approve_delete_owner_none_preserves_unscoped_behavior(tmp_path):
    """Internal callers (brain_trace, history_digest) call approve/delete_item
    without an owner arg -- must keep acting unconditionally (backward compat)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="x", owner="userA", status="pending")
    ok = store.approve(pid)
    assert ok is True
    assert store.get_item(pid)["status"] == "approved"
    ok2 = store.delete_item(pid)
    assert ok2 is True
    assert store.get_item(pid) is None
    store.close()


def test_search_ranks_by_cosine_and_excludes_sensitive(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="fact", content="vicino", embedding=[1.0, 0.0])
    store.add_item(kind="fact", content="lontano", embedding=[0.0, 1.0])
    store.add_item(kind="fact", content="segreto", embedding=[1.0, 0.0],
                   sensitivity="sensitive")
    res = store.search(query_vec=[1.0, 0.0], k=5, allow_sensitive=False)
    contents = [r["content"] for r in res]
    assert contents[0] == "vicino"          # cosine = 1.0
    assert "segreto" not in contents        # sensitive escluso
    store.close()


def test_structured_queries(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-01")
    store.add_item(kind="obligation", content="Bollo", due_date="2026-12-31")

    due = store.upcoming_obligations(before="2026-08-01")
    assert [d["content"] for d in due] == ["TARI"]
    store.close()


def test_upcoming_obligations_returns_parsed_data(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(
        kind="obligation", content="IMU",
        due_date="2026-06-30", data={"note": "prima rata"},
    )
    store.add_item(
        kind="obligation", content="Bolletta gas",
        due_date="2026-07-15", data={"note": "bolletta estiva"},
    )
    due = store.upcoming_obligations(before="2026-07-01")
    assert len(due) == 1
    item = due[0]
    assert "data" in item, "upcoming_obligations deve restituire il campo 'data'"
    assert isinstance(item["data"], dict), "'data' deve essere un dict"
    assert item["data"] == {"note": "prima rata"}
    store.close()


def test_document_chunks_add_search_exists(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    doc = store.add_item(kind="document", content="Estratto conto giugno",
                         source="mayan", source_ref="42", sensitivity="sensitive")
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=0,
                             content="bonifico 50 euro", embedding=[1.0, 0.0])
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=1,
                             content="prelievo bancomat", embedding=[0.0, 1.0])
    assert store.document_exists("42") is True
    assert store.document_exists("99") is False
    hits = store.search_chunks(query_vec=[1.0, 0.0], k=1, allow_sensitive=True)
    assert hits[0]["content"] == "bonifico 50 euro"
    assert hits[0]["sensitivity"] == "sensitive"
    store.close()
