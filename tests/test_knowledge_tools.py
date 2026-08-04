import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.tools.knowledge_tools import (
    SAVE_KNOWLEDGE_TOOL_DEF,
    RECALL_KNOWLEDGE_TOOL_DEF,
    LINK_KNOWLEDGE_TOOL_DEF,
)
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_recall_pseudonymizes_sensitive_for_cloud(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    txt = res["results"][0]["content"]
    assert "IT60X0542811101000000123456" not in txt
    assert "[IBAN_1]" in txt
    store.close()


@pytest.mark.asyncio
async def test_recall_sensitive_raw_for_local(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b2.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v2.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=False)
    txt = res["results"][0]["content"]
    # Local model: content is returned raw (not pseudonymized)
    assert "IT60X0542811101000000123456" in txt
    store.close()


@pytest.mark.asyncio
async def test_recall_pseudonymizes_non_normal_non_sensitive_literal_sensitivity(tmp_path):
    """Review C/#5: the cloud-egress gate must treat ANY non-'normal'
    sensitivity value as sensitive (mirroring knowledge_store.search's own
    `sensitivity='normal'` gate), not only the exact literal string
    "sensitive". A third value (e.g. a future/typo'd category) must still be
    pseudonymized before reaching the cloud LLM."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b5.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="confidential")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v5.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    txt = res["results"][0]["content"]
    assert "IT60X0542811101000000123456" not in txt
    assert "[IBAN_1]" in txt
    store.close()


def test_tool_defs_have_names():
    assert SAVE_KNOWLEDGE_TOOL_DEF["name"] == "save_knowledge"
    assert RECALL_KNOWLEDGE_TOOL_DEF["name"] == "recall_knowledge"
    assert LINK_KNOWLEDGE_TOOL_DEF["name"] == "link_knowledge"


@pytest.mark.asyncio
async def test_save_knowledge_creates_pending(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])
    res = await handle_save_knowledge(
        store,
        embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home",
    )
    assert res["status"] == "pending"
    pending = store.list_items(status="pending")
    assert pending[0]["content"] == "Paolo ama la pizza"
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_embedder_che_solleva_salva_comunque_senza_vettore(tmp_path):
    """Un elemento senza embedding resta comunque ritrovabile: dopo la fetta 2a
    `KnowledgeStore.search` degrada a `recent()` (stessi filtri di
    riservatezza) quando non c'e' un vettore di query. Rifiutare qui non
    protegge piu' nulla -- sposta solo il difetto vero, che e' a monte (il
    default di fabbrica NullEmbedder non calcola mai un vettore). Un embedder
    che solleva non deve impedire di ricordare: il salvataggio deve riuscire,
    senza propagare l'eccezione, e senza vettore."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "no_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("provider giu'"))

    res = await handle_save_knowledge(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home",
    )

    assert "error" not in res, "l'embedder rotto non deve impedire di salvare"
    assert res["status"] == "pending"
    # La riga e' davvero nel db: recuperabile dal percorso canonico di lettura
    # per gli elementi in coda (save_knowledge scrive sempre status='pending',
    # quindi store.recent() -- che filtra su status='approved' -- non la
    # vedrebbe; list_items(status='pending') e' l'equivalente corretto).
    pending = store.list_items(status="pending")
    assert [p["content"] for p in pending] == ["Paolo ama la pizza"]
    assert pending[0]["id"] == res["id"]
    # Nessun vettore salvato: has_embedding lo dice senza esporre il blob.
    item = store.get_item(res["id"])
    assert item["has_embedding"] is False
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_embedding_vuoto_salva_comunque_senza_vettore(tmp_path):
    """Stesso esito quando il provider risponde ma senza vettore (lista vuota):
    e' il caso del provider non configurato (NullEmbedder), che non solleva."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "empty_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_save_knowledge(
        store, embedder,
        {"kind": "fact", "content": "La caldaia va revisionata a ottobre"},
        owner="home",
    )

    assert "error" not in res
    assert res["status"] == "pending"
    pending = store.list_items(status="pending")
    assert [p["content"] for p in pending] == ["La caldaia va revisionata a ottobre"]
    item = store.get_item(res["id"])
    assert item["has_embedding"] is False
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_con_embedder_funzionante_salva_ancora_il_vettore(tmp_path):
    """Nessuna regressione: se l'embedder c'e' e funziona, il vettore si
    calcola e si salva esattamente come prima -- pinnato via has_embedding,
    non per assunzione."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "with_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    res = await handle_save_knowledge(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home",
    )

    assert "error" not in res
    assert res["status"] == "pending"
    embedder.embed.assert_awaited_once_with("Paolo ama la pizza")
    item = store.get_item(res["id"])
    assert item["has_embedding"] is True
    store.close()


@pytest.mark.asyncio
async def test_dispatcher_save_knowledge_senza_embedder_fallisce(tmp_path):
    """Il dispatcher instradava `save_knowledge` guardando solo la presenza
    dello store, mentre i runner tolgono dai tool recall_memory/save_memory
    quando manca l'embedder. Senza embedder configurato l'elemento non potra'
    mai essere richiamato: qui il salvataggio deve fallire, come gia' fa
    save_memory, invece di riuscire a vuoto."""
    from hiris.app.tools.dispatcher import ToolDispatcher

    store = KnowledgeStore(str(tmp_path / "dispatch_no_emb.db"))
    dispatcher = ToolDispatcher(
        ha_client=MagicMock(),
        notify_config={},
        knowledge_store=store,
        embedder=None,
    )

    res = await dispatcher.dispatch(
        "save_knowledge",
        {"kind": "preference", "content": "Paolo ama la pizza"},
    )

    assert isinstance(res, dict) and res.get("error")
    assert res.get("status") != "pending"
    assert store.list_items() == []
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_con_embedder_rotto_degrada_ai_piu_recenti(tmp_path):
    """Task 6: l'embedder che solleva non blocca piu' il richiamo. La ricerca
    degrada ai piu' recenti (KnowledgeStore.search -> recent()) invece di
    rifiutare, e l'eccezione non deve propagare al chiamante."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge

    store = KnowledgeStore(str(tmp_path / "guasto.db"))
    store.add_item(kind="fact", content="La caldaia e' del 2019",
                   embedding=[1.0, 0.0], status="approved")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("provider giu' su :11434"))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "caldaia"}, owner="home")

    assert "error" not in res
    contents = [r["content"] for r in res["results"]]
    assert "La caldaia e' del 2019" in contents
    assert res.get("degraded") is True, (
        "il richiamo degradato deve dichiararsi tale"
    )
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_con_vettore_vuoto_degrada_ai_piu_recenti(tmp_path):
    """Stesso esito quando il provider risponde ma senza vettore (caso del
    NullEmbedder di fabbrica, che non solleva)."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge

    store = KnowledgeStore(str(tmp_path / "forma.db"))
    store.add_item(kind="fact", content="La caldaia e' del 2019",
                   embedding=[1.0, 0.0], status="approved")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "caldaia"}, owner="home")

    assert "error" not in res
    contents = [r["content"] for r in res["results"]]
    assert "La caldaia e' del 2019" in contents
    assert res.get("degraded") is True
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_con_embedder_funzionante_non_degrada(tmp_path):
    """Nessuna regressione: con un vettore vero il richiamo ordina per
    somiglianza come prima e NON porta il segnale di degradazione."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge

    store = KnowledgeStore(str(tmp_path / "no_degrado.db"))
    store.add_item(kind="fact", content="La caldaia e' del 2019",
                   embedding=[1.0, 0.0], status="approved")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "caldaia"}, owner="home")

    assert "error" not in res
    contents = [r["content"] for r in res["results"]]
    assert "La caldaia e' del 2019" in contents
    assert not res.get("degraded"), (
        "una ricerca vettoriale vera non deve portare il segnale di degradazione"
    )
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_degradato_applica_lo_stesso_filtro_di_riservatezza(tmp_path):
    """Task 6 punto 4: il richiamo degradato non deve perdere il filtro di
    riservatezza. Una riga sensibile non deve comparire a chi non puo'
    vederla -- e' la stessa invariante pinnata dentro lo store (Task 1),
    verificata qui dal lato del chiamante."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge

    store = KnowledgeStore(str(tmp_path / "riservato.db"))
    store.add_item(kind="fact", content="dato pubblico", embedding=[1.0, 0.0],
                   status="approved", sensitivity="normal")
    store.add_item(kind="fact", content="dato sensibile", embedding=[1.0, 0.0],
                   status="approved", sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "qualunque cosa"}, owner="home",
        allow_sensitive=False)

    assert res.get("degraded") is True
    contents = [r["content"] for r in res["results"]]
    assert "dato sensibile" not in contents
    assert "dato pubblico" in contents
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_vuoto_legittimo_non_e_un_errore(tmp_path):
    """Il caso opposto, che deve restare distinguibile: la ricerca funziona e
    non trova nulla."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge

    store = KnowledgeStore(str(tmp_path / "vuoto.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "caldaia"}, owner="home")

    assert res["results"] == []
    assert "error" not in res
    store.close()


@pytest.mark.asyncio
async def test_recall_includes_document_chunks(tmp_path):
    """A normal-sensitivity document chunk is returned by recall_knowledge."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge

    store = KnowledgeStore(str(tmp_path / "b3.db"))
    doc = store.add_item(kind="document", content="Estratto", source="mayan",
                         source_ref="42", sensitivity="normal")
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=0,
                             content="canone mensile 9.99", embedding=[1.0, 0.0])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "canone"}, owner="home",
        allow_sensitive=False)
    contents = [r["content"] for r in res["results"]]
    assert "canone mensile 9.99" in contents
    kinds = [r["kind"] for r in res["results"]]
    assert "document_chunk" in kinds
    store.close()


@pytest.mark.asyncio
async def test_recall_pseudonymizes_sensitive_chunk_for_cloud(tmp_path):
    """A sensitive document chunk is pseudonymized when cloud=True and a pseudonymizer is provided."""
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b4.db"))
    doc = store.add_item(kind="document", content="Estratto conto",
                         source="mayan", source_ref="99", sensitivity="sensitive")
    store.add_document_chunk(item_id=doc, mayan_doc_id="99", chunk_index=0,
                             content="Bonifico da IT60X0542811101000000123456",
                             embedding=[1.0, 0.0])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v4.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    # Sensitive chunk must be pseudonymized: raw IBAN must not appear
    contents = [r["content"] for r in res["results"]]
    chunk_contents = [
        r["content"] for r in res["results"] if r["kind"] == "document_chunk"
    ]
    assert chunk_contents, "no document_chunk in results"
    assert "IT60X0542811101000000123456" not in chunk_contents[0]
    assert "[IBAN_1]" in chunk_contents[0]
    store.close()


@pytest.mark.asyncio
async def test_dispatcher_routes_save_knowledge(tmp_path):
    """ToolDispatcher.dispatch('save_knowledge') must route to _knowledge_store
    and return status='pending'; a pending item must be recorded in the store."""
    from hiris.app.tools.dispatcher import ToolDispatcher

    store = KnowledgeStore(str(tmp_path / "dispatch_brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    # Minimal stubs for required ToolDispatcher constructor args
    ha_stub = MagicMock()
    notify_cfg: dict = {}

    dispatcher = ToolDispatcher(
        ha_client=ha_stub,
        notify_config=notify_cfg,
        knowledge_store=store,
        embedder=embedder,
    )

    result = await dispatcher.dispatch(
        "save_knowledge",
        {"kind": "preference", "content": "Paolo ama la pizza"},
    )

    assert result.get("status") == "pending"
    pending = store.list_items(status="pending")
    assert len(pending) == 1
    assert pending[0]["content"] == "Paolo ama la pizza"
    store.close()
