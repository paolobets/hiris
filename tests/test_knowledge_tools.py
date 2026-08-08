"""Task 2 (memoria unica) -- questi test coprivano save_knowledge/
recall_knowledge, il tool gemello di save_memory/recall_memory (stessa
funzione sulla stessa tabella, due nomi). Dopo il merge non esiste piu' un
tool separato: sono riscritti sul sopravvissuto (handle_save_memory/
handle_recall_memory, tools/memory_tools.py), passando `kind` esplicito dove
prima lo decideva il nome del tool chiamato. Ogni salvataggio nasce ora
`status='approved'` -- niente piu' coda -- quindi le asserzioni su 'pending'
sono diventate asserzioni sul comportamento reale: subito approvato, subito
ritrovabile."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.tools.memory_tools import (
    SAVE_MEMORY_TOOL_DEF,
    RECALL_MEMORY_TOOL_DEF,
)
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_recall_pseudonymizes_sensitive_for_cloud(tmp_path):
    from hiris.app.tools.memory_tools import handle_recall_memory
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v.db")))

    res = await handle_recall_memory(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    txt = res["results"][0]["content"]
    assert "IT60X0542811101000000123456" not in txt
    assert "[IBAN_1]" in txt
    store.close()


@pytest.mark.asyncio
async def test_recall_sensitive_raw_for_local(tmp_path):
    from hiris.app.tools.memory_tools import handle_recall_memory
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b2.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v2.db")))

    res = await handle_recall_memory(
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
    from hiris.app.tools.memory_tools import handle_recall_memory
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b5.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="confidential")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v5.db")))

    res = await handle_recall_memory(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    txt = res["results"][0]["content"]
    assert "IT60X0542811101000000123456" not in txt
    assert "[IBAN_1]" in txt
    store.close()


def test_tool_defs_have_names():
    assert SAVE_MEMORY_TOOL_DEF["name"] == "save_memory"
    assert RECALL_MEMORY_TOOL_DEF["name"] == "recall_memory"


@pytest.mark.asyncio
async def test_save_memory_kind_esplicito_e_gia_approvato(tmp_path):
    """Task 2: niente piu' coda. Un kind esplicito (il vocabolario del vecchio
    save_knowledge) nasce subito status='approved', non 'pending'."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])
    res = await handle_save_memory(
        store,
        embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home", chatbot_id="agentA",
    )
    assert res.get("saved") is True
    item = store.get_item(res["id"])
    assert item["status"] == "approved"
    assert item["kind"] == "preference"
    assert item["content"] == "Paolo ama la pizza"
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_k_negativo_non_diventa_limit_illimitato(tmp_path):
    """`k` finisce in una `LIMIT` SQL sul percorso degradato (recent()): in
    SQLite `LIMIT -1` significa 'nessun limite', quindi un k negativo
    restituirebbe ogni riga nello scope invece di essere clampato."""
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "k_negativo.db"))
    for i in range(5):
        store.add_item(kind="note", content=f"nota {i}", owner="home")

    res = await handle_recall_memory(
        store, None, {"query": "nota", "k": -1}, owner="home",
    )

    assert res["degraded"] is True
    assert len(res["results"]) == 1, "k negativo deve clampare a 1, non diventare LIMIT -1"
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_embedder_che_solleva_salva_comunque_senza_vettore(tmp_path):
    """Un elemento senza embedding resta comunque ritrovabile: `KnowledgeStore.
    search` degrada a `recent()` (stessi filtri di riservatezza) quando non
    c'e' un vettore di query. Un embedder che solleva non deve impedire di
    ricordare: il salvataggio deve riuscire, senza propagare l'eccezione, e
    senza vettore -- e nasce gia' approvato."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "no_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("provider giu'"))

    res = await handle_save_memory(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home", chatbot_id="agentA",
    )

    assert "error" not in res, "l'embedder rotto non deve impedire di salvare"
    assert res.get("saved") is True
    approvati = store.list_items(status="approved")
    assert [p["content"] for p in approvati] == ["Paolo ama la pizza"]
    assert approvati[0]["id"] == res["id"]
    # Nessun vettore salvato: has_embedding lo dice senza esporre il blob.
    item = store.get_item(res["id"])
    assert item["has_embedding"] is False
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_embedding_vuoto_salva_comunque_senza_vettore(tmp_path):
    """Stesso esito quando il provider risponde ma senza vettore (lista vuota):
    e' il caso del provider non configurato (NullEmbedder), che non solleva."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "empty_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_save_memory(
        store, embedder,
        {"kind": "fact", "content": "La caldaia va revisionata a ottobre"},
        owner="home", chatbot_id="agentA",
    )

    assert "error" not in res
    approvati = store.list_items(status="approved")
    assert [p["content"] for p in approvati] == ["La caldaia va revisionata a ottobre"]
    item = store.get_item(res["id"])
    assert item["has_embedding"] is False
    store.close()


@pytest.mark.asyncio
async def test_save_knowledge_con_embedder_funzionante_salva_ancora_il_vettore(tmp_path):
    """Nessuna regressione: se l'embedder c'e' e funziona, il vettore si
    calcola e si salva esattamente come prima -- pinnato via has_embedding,
    non per assunzione."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "with_emb.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    res = await handle_save_memory(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home", chatbot_id="agentA",
    )

    assert "error" not in res
    embedder.embed.assert_awaited_once_with("Paolo ama la pizza")
    item = store.get_item(res["id"])
    assert item["has_embedding"] is True
    store.close()


@pytest.mark.asyncio
async def test_save_memory_kind_esplicito_senza_embedder_riesce_comunque(tmp_path):
    """Un tempo il vecchio save_knowledge rifiutava anche senza embedder,
    perche' senza vettore l'elemento non sarebbe mai stato richiamabile. Non
    e' piu' vero: `KnowledgeStore.search` degrada a `recent()` quando non c'e'
    un vettore di query (stessi filtri di riservatezza), quindi un elemento
    senza embedding resta comunque ritrovabile. Il default di fabbrica
    (NullEmbedder) non calcola MAI un vettore, quindi il rifiuto colpiva ogni
    installazione stock: qui deve riuscire.

    fetta E2 Task 7: chiamato direttamente (era `ToolDispatcher.dispatch`,
    uscito) -- stessa funzione, stesso comportamento."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "dispatch_no_emb.db"))

    res = await handle_save_memory(
        store, None,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home", chatbot_id="hiris-default",
    )

    assert "error" not in res, "l'assenza di embedder non deve impedire di salvare"
    assert res.get("saved") is True
    rows = store.list_items(status="approved")
    assert len(rows) == 1
    assert rows[0]["content"] == "Paolo ama la pizza"
    assert rows[0]["kind"] == "preference"
    store.close()


@pytest.mark.asyncio
async def test_save_memory_senza_store_fallisce(tmp_path):
    """Lo store, a differenza dell'embedder, resta un motivo reale di
    rifiuto: senza store non c'e' dove scrivere l'elemento.

    fetta E2 Task 7: chiamato direttamente (era `ToolDispatcher.dispatch`,
    uscito)."""
    from hiris.app.tools.memory_tools import handle_save_memory

    res = await handle_save_memory(
        None, None,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home", chatbot_id="hiris-default",
    )

    assert isinstance(res, dict) and res.get("error")
    assert res.get("saved") is not True


@pytest.mark.asyncio
async def test_recall_knowledge_con_embedder_rotto_degrada_ai_piu_recenti(tmp_path):
    """L'embedder che solleva non blocca il richiamo. La ricerca degrada ai
    piu' recenti (KnowledgeStore.search -> recent()) invece di rifiutare, e
    l'eccezione non deve propagare al chiamante."""
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "guasto.db"))
    store.add_item(kind="fact", content="La caldaia e' del 2019",
                   embedding=[1.0, 0.0], status="approved")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("provider giu' su :11434"))

    res = await handle_recall_memory(
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
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "forma.db"))
    store.add_item(kind="fact", content="La caldaia e' del 2019",
                   embedding=[1.0, 0.0], status="approved")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_recall_memory(
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
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "no_degrado.db"))
    store.add_item(kind="fact", content="La caldaia e' del 2019",
                   embedding=[1.0, 0.0], status="approved")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    res = await handle_recall_memory(
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
    """Il richiamo degradato non deve perdere il filtro di riservatezza. Una
    riga sensibile non deve comparire a chi non puo' vederla."""
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "riservato.db"))
    store.add_item(kind="fact", content="dato pubblico", embedding=[1.0, 0.0],
                   status="approved", sensitivity="normal")
    store.add_item(kind="fact", content="dato sensibile", embedding=[1.0, 0.0],
                   status="approved", sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[])

    res = await handle_recall_memory(
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
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "vuoto.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    res = await handle_recall_memory(
        store, embedder, {"query": "caldaia"}, owner="home")

    assert res["results"] == []
    assert "error" not in res
    store.close()


@pytest.mark.asyncio
async def test_recall_includes_document_chunks(tmp_path):
    """A normal-sensitivity document chunk is returned by recall_memory."""
    from hiris.app.tools.memory_tools import handle_recall_memory

    store = KnowledgeStore(str(tmp_path / "b3.db"))
    doc = store.add_item(kind="document", content="Estratto", source="mayan",
                         source_ref="42", sensitivity="normal")
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=0,
                             content="canone mensile 9.99", embedding=[1.0, 0.0])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])

    res = await handle_recall_memory(
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
    from hiris.app.tools.memory_tools import handle_recall_memory
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

    res = await handle_recall_memory(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    # Sensitive chunk must be pseudonymized: raw IBAN must not appear
    chunk_contents = [
        r["content"] for r in res["results"] if r["kind"] == "document_chunk"
    ]
    assert chunk_contents, "no document_chunk in results"
    assert "IT60X0542811101000000123456" not in chunk_contents[0]
    assert "[IBAN_1]" in chunk_contents[0]
    store.close()


@pytest.mark.asyncio
async def test_save_memory_kind_esplicito_instrada_alla_knowledge_store(tmp_path):
    """`save_memory` con un kind esplicito deve instradare alla KnowledgeStore
    e tornare gia' approvato -- niente coda.

    fetta E2 Task 7: chiamato direttamente (era `ToolDispatcher.dispatch`,
    uscito)."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "dispatch_brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    result = await handle_save_memory(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home", chatbot_id="hiris-default",
    )

    assert result.get("saved") is True
    approvati = store.list_items(status="approved")
    assert len(approvati) == 1
    assert approvati[0]["content"] == "Paolo ama la pizza"
    assert approvati[0]["kind"] == "preference"
    store.close()
