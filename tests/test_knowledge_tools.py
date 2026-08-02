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
async def test_save_knowledge_senza_embedding_non_finge_di_aver_salvato(tmp_path):
    """Un elemento senza embedding non e' richiamabile: knowledge_store.search
    filtra su `status='approved' AND embedding IS NOT NULL`. Se il calcolo
    dell'embedding fallisce, salvare comunque riaprirebbe lo stesso fallimento
    silenzioso che la coda di approvazione ha appena chiuso, spostato di un
    passo: il modello dice "salvato", l'elemento compare nella coda, l'utente
    lo approva e resta comunque irraggiungibile. Deve fallire apertamente e
    non scrivere nulla."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "no_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("provider giu'"))

    res = await handle_save_knowledge(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home",
    )

    assert res.get("error"), "senza embedding il salvataggio deve dichiarare l'errore"
    assert "status" not in res, "nessun successo apparente"
    # Nessuna riga scritta: ne' pending ne' approved.
    assert store.list_items() == []
    # L'errore non deve riportare il testo dell'eccezione al chiamante.
    assert "provider giu'" not in res["error"]
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_embedding_vuoto_non_finge_di_aver_salvato(tmp_path):
    """Stesso esito quando il provider risponde ma senza vettore (lista vuota):
    e' il caso del provider non configurato, che non solleva."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "empty_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_save_knowledge(
        store, embedder,
        {"kind": "fact", "content": "La caldaia va revisionata a ottobre"},
        owner="home",
    )

    assert res.get("error")
    assert store.list_items() == []
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
