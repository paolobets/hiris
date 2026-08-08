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
    # precedente): approvarlo lo indicizza, cosi' diventa richiamabile invece
    # di restare approvato-e-muto.
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
async def test_manual_add_senza_embedder_scrive_comunque_non_richiamabile(
    aiohttp_client, tmp_path,
):
    """Stessa forma del difetto chiuso in save_knowledge, su un percorso
    solo-API: senza un provider di embedding l'elemento non puo' avere un
    vettore. Rifiutare la richiesta lasciava l'utente bloccato -- l'elemento
    viene scritto e marcato approvato comunque, solo non richiamabile dalla
    ricerca (che filtra su `embedding IS NOT NULL`) finche' un embedding non
    arriva."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_manual_add

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    app = web.Application()
    app["knowledge_store"] = store
    # Nessun embedding_provider configurato.
    app.router.add_post("/api/knowledge", handle_manual_add)
    client = await aiohttp_client(app)

    r = await client.post("/api/knowledge", json={"kind": "note", "content": "x"})

    assert r.status == 200
    data = await r.json()
    assert data["status"] == "approved"
    # La riga esiste davvero, approvata, senza vettore.
    item = store.get_item(data["id"])
    assert item is not None
    assert item["status"] == "approved"
    assert not item["has_embedding"]
    assert not _trovato(store, "x")

    store.close()


@pytest.mark.asyncio
async def test_manual_add_con_embedder_rotto_scrive_comunque_senza_vettore(
    aiohttp_client, tmp_path,
):
    """Un provider configurato che solleva un'eccezione non deve piu' bloccare
    la scrittura: il dettaglio resta nel log del server, la riga viene scritta
    senza vettore, come nel caso di provider assente."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_manual_add

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    app = web.Application()
    app["knowledge_store"] = store
    app["embedding_provider"] = _EmbedderFinto(esplode=True)
    app.router.add_post("/api/knowledge", handle_manual_add)
    client = await aiohttp_client(app)

    r = await client.post("/api/knowledge", json={"kind": "note", "content": "x"})

    assert r.status == 200
    corpo = await r.json()
    assert corpo["status"] == "approved"
    item = store.get_item(corpo["id"])
    assert item["status"] == "approved"
    assert not item["has_embedding"]
    assert not _trovato(store, "x")

    store.close()


@pytest.mark.asyncio
async def test_manual_add_con_embedder_scrive_un_elemento_richiamabile(
    aiohttp_client, tmp_path,
):
    """Il percorso buono, verificato dal comportamento: l'elemento aggiunto a
    mano si trova davvero con la ricerca."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_manual_add, handle_list_pending

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    app = web.Application()
    app["knowledge_store"] = store
    app["embedding_provider"] = _EmbedderFinto()
    app.router.add_post("/api/knowledge", handle_manual_add)
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.post("/api/knowledge", json={"kind": "note", "content": "x"})
    assert r.status == 200
    data = await r.json()
    assert data["status"] == "approved"
    item_id = data["id"]

    # Non finisce in coda: e' gia' approvato.
    r2 = await client.get("/api/knowledge/pending")
    pending_data = await r2.json()
    assert all(i["id"] != item_id for i in pending_data["items"])
    # E l'unico modo di richiamare un'informazione lo vede.
    assert _trovato(store, "x")

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
    "Approva" della coda.

    Nota (Task 2 -- memoria unica): il tool LLM `save_memory` (fusione dei
    vecchi save_memory/save_knowledge) scrive oggi sempre `status='approved'`
    -- non esiste piu' un percorso che passi da questo tool a `pending`. La
    coda di approvazione manuale (`handlers_knowledge.py`, questo file)
    resta invece invariata: qui l'elemento in coda si crea direttamente
    sullo store, come fa il resto del file, per esercitare l'endpoint
    `/approve` a prescindere da come una riga finisce in coda."""
    from unittest.mock import AsyncMock
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    saved_id = store.add_item(
        kind="obligation", content="La caldaia va revisionata a ottobre",
        owner="home", status="pending",
        embedding=await embedder.embed("La caldaia va revisionata a ottobre"),
    )
    saved = {"id": saved_id, "status": "pending"}

    # fetta E2 Task 8 ("escono i trentaquattro"): `handle_recall_memory`
    # (tools/memory_tools.py) e' uscita -- orfana dal Task 7 (il
    # `ToolDispatcher` che la chiamava e' uscito). Il soggetto vero di questo
    # test e' `KnowledgeStore.search`, che chiamava attraverso quel wrapper:
    # lo chiama direttamente.
    async def cerca():
        qv = await embedder.embed("caldaia")
        res = store.search(query_vec=qv, k=5, owner="home")
        return [r["content"] for r in res]

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
# cambiava solo lo stato e le lasciava irraggiungibili per sempre. Rifiutare
# l'approvazione finche' non c'era un vettore chiudeva quel silenzio dietro un
# altro: la coda in chat mostrava all'utente la cosa che HIRIS aveva imparato
# e rispondeva 503 al pulsante «Approva», lasciandolo bloccato. L'approvazione
# calcola l'embedding mancante quando puo'; quando non puo' approva comunque,
# senza vettore -- la riga resta un ricordo dell'utente, recuperabile da
# `recent()` (il percorso di degradazione di `search()`), solo non ancora
# trovabile da una ricerca per significato.


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
async def test_approvare_senza_embedder_riesce_comunque_e_approva(
    aiohttp_client, tmp_path,
):
    """Il caso che oggi lascia l'utente bloccato: una riga senza vettore e
    senza modo di calcolarne uno (nessun provider configurato). Prima di
    questa modifica il pulsante «Approva» rispondeva 503 e la riga restava in
    coda per sempre. Ora l'approvazione riesce davvero: lo stato in database
    cambia, non solo la risposta HTTP."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="senza indice",
                         status="pending", embedding=None)

    client = await aiohttp_client(_app_approve(store, embedder=None))
    r = await client.post(f"/api/knowledge/{pid}/approve")
    assert r.status == 200
    assert (await r.json())["ok"] is True
    # La mutazione e' reale: la riga e' approvata in database, non solo la
    # risposta HTTP lo dice.
    item = store.get_item(pid)
    assert item["status"] == "approved"
    assert not item["has_embedding"]
    # Senza vettore non e' ancora trovabile da una ricerca per significato.
    assert not _trovato(store, "senza indice")

    store.close()


@pytest.mark.asyncio
async def test_approvare_con_embedder_rotto_approva_comunque_senza_esporre_lerrore(
    aiohttp_client, tmp_path,
):
    """Un provider configurato che solleva un'eccezione non deve piu'
    impedire l'approvazione: il dettaglio dell'eccezione resta nel log del
    server, la riga viene comunque approvata, senza vettore."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="indice non calcolabile",
                         status="pending", embedding=None)

    embedder = _EmbedderFinto(esplode=True)
    client = await aiohttp_client(_app_approve(store, embedder))
    r = await client.post(f"/api/knowledge/{pid}/approve")
    assert r.status == 200
    corpo = await r.json()
    assert corpo["ok"] is True
    item = store.get_item(pid)
    assert item["status"] == "approved"
    assert not item["has_embedding"]
    assert not _trovato(store, "indice non calcolabile")

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
