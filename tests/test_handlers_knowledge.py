import pytest
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_pending_and_approve(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import (
        handle_list_pending, handle_approve,
    )
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="x", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    # L'elemento e' senza embedding (come quelli scritti dalla versione
    # precedente): approvarlo lo indicizza, e senza un provider fallirebbe
    # dichiaratamente invece di renderlo approvato-e-muto.
    app["embedding_provider"] = _EmbedderFinto()
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending")
    data = await r.json()
    assert [i["id"] for i in data["items"]] == [pid]

    r2 = await client.post(f"/api/knowledge/{pid}/approve")
    assert r2.status == 200
    assert store.get_item(pid)["status"] == "approved"

    store.close()


@pytest.mark.asyncio
async def test_manual_add_no_embedder(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_manual_add, handle_list_pending

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    app = web.Application()
    app["knowledge_store"] = store
    # No embedding_provider — must still work
    app.router.add_post("/api/knowledge", handle_manual_add)
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.post(
        "/api/knowledge",
        json={"kind": "note", "content": "x"},
    )
    assert r.status == 200
    data = await r.json()
    assert data["status"] == "approved"
    item_id = data["id"]

    # Verify item is approved and visible via list_items
    approved = store.list_items(status="approved")
    assert any(i["id"] == item_id for i in approved)

    # Verify item does NOT appear in pending list
    r2 = await client.get("/api/knowledge/pending")
    pending_data = await r2.json()
    assert all(i["id"] != item_id for i in pending_data["items"])

    store.close()


@pytest.mark.asyncio
async def test_reject_deletes_item(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending, handle_reject

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="to reject", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    client = await aiohttp_client(app)

    r = await client.post(f"/api/knowledge/{pid}/reject")
    assert r.status == 200

    assert store.get_item(pid) is None

    store.close()


@pytest.mark.asyncio
async def test_list_pending_scoped_to_owner_and_home(aiohttp_client, tmp_path):
    """IDOR regression (review B/#16): user B must not see user A's private
    pending items, only their own + shared 'home' items."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA",
                           sensitivity="sensitive", status="pending")
    b_id = store.add_item(kind="fact", content="B's own", owner="userB", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending", headers={"X-Remote-User-Id": "userB"})
    assert r.status == 200
    data = await r.json()
    ids = {i["id"] for i in data["items"]}
    assert ids == {b_id, home_id}
    assert a_id not in ids

    store.close()


@pytest.mark.asyncio
async def test_approve_cross_owner_rejected(aiohttp_client, tmp_path):
    """IDOR regression: user B cannot approve user A's pending item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r = await client.post(f"/api/knowledge/{a_id}/approve", headers={"X-Remote-User-Id": "userB"})
    assert r.status in (403, 404)
    assert store.get_item(a_id)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_reject_cross_owner_rejected(aiohttp_client, tmp_path):
    """IDOR regression: user B cannot delete (reject) user A's pending item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_reject

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    client = await aiohttp_client(app)

    r = await client.post(f"/api/knowledge/{a_id}/reject", headers={"X-Remote-User-Id": "userB"})
    assert r.status in (403, 404)
    assert store.get_item(a_id) is not None
    assert store.get_item(a_id)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_approve_own_item_and_home_item_still_works(aiohttp_client, tmp_path):
    """Legitimate flow: a user approves their OWN pending item, and any user
    can approve a shared 'home' item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    own_id = store.add_item(kind="fact", content="mine", owner="userA", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    # Entrambi senza embedding: l'approvazione lo calcola (vedi in fondo al
    # file), quindi il percorso legittimo ha bisogno del provider.
    app["embedding_provider"] = _EmbedderFinto()
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r1 = await client.post(f"/api/knowledge/{own_id}/approve", headers={"X-Remote-User-Id": "userA"})
    assert r1.status == 200
    assert store.get_item(own_id)["status"] == "approved"

    r2 = await client.post(f"/api/knowledge/{home_id}/approve", headers={"X-Remote-User-Id": "userA"})
    assert r2.status == 200
    assert store.get_item(home_id)["status"] == "approved"

    store.close()


@pytest.mark.asyncio
async def test_unknown_identity_fails_closed_to_home_scope(aiohttp_client, tmp_path):
    """No X-Remote-User-Id header (unknown identity) must fail closed: only
    'home' items are visible/actionable, never another user's private item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending, handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    # No identity header at all.
    r = await client.get("/api/knowledge/pending")
    data = await r.json()
    ids = {i["id"] for i in data["items"]}
    assert ids == {home_id}
    assert a_id not in ids

    r2 = await client.post(f"/api/knowledge/{a_id}/approve")
    assert r2.status in (403, 404)
    assert store.get_item(a_id)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_no_store_list_signals_unavailable(aiohttp_client):
    """Uno store assente NON e' una coda vuota: rispondere 200 {"items": []}
    faceva apparire "non ho potuto leggere" come "non c'e' niente da
    approvare", che e' esattamente il modo in cui un ricordo si perde in
    silenzio. Stesso 503 delle rotte di scrittura, cosi' la coda in chat puo'
    distinguere i due casi."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending

    app = web.Application()
    # knowledge_store NOT set
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending")
    assert r.status == 503
    data = await r.json()
    assert data["items"] == []
    assert data["error"]


@pytest.mark.asyncio
async def test_no_store_write_returns_503(aiohttp_client):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import (
        handle_approve, handle_reject, handle_manual_add,
    )

    app = web.Application()
    # knowledge_store NOT set
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    app.router.add_post("/api/knowledge", handle_manual_add)
    client = await aiohttp_client(app)

    r1 = await client.post("/api/knowledge/1/approve")
    assert r1.status == 503

    r2 = await client.post("/api/knowledge/1/reject")
    assert r2.status == 503

    r3 = await client.post("/api/knowledge", json={"kind": "note", "content": "x"})
    assert r3.status == 503


@pytest.mark.asyncio
async def test_approvazione_rende_richiamabile(aiohttp_client, tmp_path):
    """Il ciclo che questo lavoro promette, verificato dal comportamento e non
    dalla colonna: salvato -> coda -> approvato -> richiamabile.

    Gli altri test si fermano a `status == 'approved'`, che e' struttura
    interna: se domani la ricerca aggiungesse un filtro (come gia' fa con
    `embedding IS NOT NULL`) resterebbero verdi mentre il ricordo tornerebbe
    irraggiungibile. Qui l'elemento viene CERCATO davvero, prima e dopo
    l'approvazione, passando dallo stesso endpoint che tocca il bottone
    "Approva" della coda."""
    from unittest.mock import AsyncMock
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve
    from hiris.app.tools.knowledge_tools import (
        handle_save_knowledge, handle_recall_knowledge,
    )

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    saved = await handle_save_knowledge(
        store, embedder,
        {"kind": "obligation", "content": "La caldaia va revisionata a ottobre"},
        owner="home",
    )
    assert saved["status"] == "pending"

    async def cerca():
        res = await handle_recall_knowledge(
            store, embedder, {"query": "caldaia"}, owner="home")
        return [r["content"] for r in res["results"]]

    # Prima dell'approvazione: in coda, quindi NON richiamabile.
    assert "La caldaia va revisionata a ottobre" not in await cerca()

    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)
    r = await client.post(f"/api/knowledge/{saved['id']}/approve")
    assert r.status == 200

    # Dopo l'approvazione: la ricerca lo trova. E' questo che l'utente ha
    # comprato approvando, non il valore della colonna.
    assert "La caldaia va revisionata a ottobre" in await cerca()

    store.close()


# ── Gli elementi gia' in coda, salvati SENZA embedding ───────────────────────
#
# La versione precedente di save_knowledge scriveva l'elemento anche quando
# l'embedding non si poteva calcolare (provider assente o chiamata fallita),
# lasciando la colonna a NULL. La ricerca filtra su
# `status='approved' AND embedding IS NOT NULL`: approvare quelle righe
# cambiava solo lo stato e le lasciava irraggiungibili per sempre -- lo stesso
# silenzio che questo lavoro chiude, riaperto sui dati gia' esistenti, con la
# promessa scritta nelle note di rilascio ("approvato significa richiamabile da
# quel momento in poi"). L'approvazione deve quindi calcolare l'embedding
# mancante, e quando non ci riesce deve fallire dichiaratamente: la coda in
# chat ha gia' il ramo che mostra l'errore (503).


class _EmbedderFinto:
    """Provider di embedding a comportamento dichiarato: conta le chiamate,
    cosi' i test possono verificare anche cio' che NON deve succedere."""

    def __init__(self, vettore=None, esplode=False):
        self._vettore = vettore if vettore is not None else [1.0, 0.0]
        self._esplode = esplode
        self.chiamate = []

    async def embed(self, text):
        self.chiamate.append(text)
        if self._esplode:
            raise RuntimeError("embedder giu' -- dettaglio che non deve uscire")
        return list(self._vettore)


def _app_approve(store, embedder=None):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    app = web.Application()
    app["knowledge_store"] = store
    if embedder is not None:
        app["embedding_provider"] = embedder
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    return app


def _trovato(store, contenuto):
    return contenuto in [
        r["content"] for r in store.search(query_vec=[1.0, 0.0], k=10)
    ]


@pytest.mark.asyncio
async def test_approvare_un_elemento_senza_embedding_lo_rende_richiamabile(
    aiohttp_client, tmp_path,
):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    # Come lo scriveva la vecchia save_knowledge: nessun embedding.
    pid = store.add_item(kind="fact", content="La caldaia e' del 2019",
                         status="pending", embedding=None)
    assert not _trovato(store, "La caldaia e' del 2019")

    embedder = _EmbedderFinto()
    client = await aiohttp_client(_app_approve(store, embedder))
    r = await client.post(f"/api/knowledge/{pid}/approve")
    assert r.status == 200
    # L'embedding e' stato calcolato sul contenuto vero dell'elemento.
    assert embedder.chiamate == ["La caldaia e' del 2019"]
    # E l'unico modo di richiamare un'informazione ora lo vede.
    assert _trovato(store, "La caldaia e' del 2019")

    store.close()


@pytest.mark.asyncio
async def test_approvare_senza_embedder_fallisce_invece_di_dichiarare_successo(
    aiohttp_client, tmp_path,
):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="senza indice",
                         status="pending", embedding=None)

    client = await aiohttp_client(_app_approve(store, embedder=None))
    r = await client.post(f"/api/knowledge/{pid}/approve")
    # 503: lo stesso stato che la coda in chat traduce gia' in "la memoria non
    # e' raggiungibile in questo momento".
    assert r.status == 503
    assert (await r.json())["error"]
    # Nessuna mutazione: l'elemento resta in coda, riapprovabile domani.
    assert store.get_item(pid)["status"] == "pending"
    assert not _trovato(store, "senza indice")

    store.close()


@pytest.mark.asyncio
async def test_approvare_con_embedder_rotto_non_muta_nulla_e_non_espone_lerrore(
    aiohttp_client, tmp_path,
):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="indice non calcolabile",
                         status="pending", embedding=None)

    embedder = _EmbedderFinto(esplode=True)
    client = await aiohttp_client(_app_approve(store, embedder))
    r = await client.post(f"/api/knowledge/{pid}/approve")
    assert r.status == 503
    corpo = await r.json()
    assert corpo["error"]
    # Il dettaglio dell'eccezione resta nel log del server, non nella risposta.
    assert "embedder giu'" not in corpo["error"]
    assert store.get_item(pid)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_approvare_un_elemento_con_embedding_non_lo_ricalcola(
    aiohttp_client, tmp_path,
):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="gia' indicizzato",
                         status="pending", embedding=[1.0, 0.0])

    # Se l'approvazione ricalcolasse a ogni giro, questo embedder farebbe
    # fallire l'approvazione di un elemento che non ne ha bisogno.
    embedder = _EmbedderFinto(esplode=True)
    client = await aiohttp_client(_app_approve(store, embedder))
    r = await client.post(f"/api/knowledge/{pid}/approve")
    assert r.status == 200
    assert embedder.chiamate == []
    assert _trovato(store, "gia' indicizzato")

    store.close()


@pytest.mark.asyncio
async def test_approvare_lelemento_di_un_altro_owner_non_tocca_lembedder(
    aiohttp_client, tmp_path,
):
    """La riservatezza viene prima: un id di un altro owner deve fermarsi al
    404 senza che il contenuto passi dal servizio di embedding."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="segreto di A", owner="userA",
                          status="pending", embedding=None)

    embedder = _EmbedderFinto()
    client = await aiohttp_client(_app_approve(store, embedder))
    r = await client.post(f"/api/knowledge/{a_id}/approve",
                          headers={"X-Remote-User-Id": "userB"})
    assert r.status in (403, 404)
    assert embedder.chiamate == []
    assert store.get_item(a_id)["status"] == "pending"

    store.close()
