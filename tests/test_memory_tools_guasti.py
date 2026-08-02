"""A1/A3 — save_memory e recall_memory non devono dire una cosa e farne un'altra.

Un ricordo senza embedding non e' richiamabile: `knowledge_store.search` filtra
su `status='approved' AND embedding IS NOT NULL`. Scriverlo comunque e
rispondere `saved: True` e' il gemello, ancora vivo, del difetto chiuso per
save_knowledge: il modello dice "me lo ricordo" e il ricordo non tornera' mai.

Lo stesso vale in lettura: se il vettore di ricerca non si calcola, "nessun
ricordo" e "non ho potuto guardare" sono due frasi diverse, e solo la seconda
e' vera.
"""
from __future__ import annotations

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.tools.memory_tools import (
    SAVE_MEMORY_TOOL_DEF,
    handle_recall_memory,
    handle_save_memory,
)


class _Embedder:
    """Provider a comportamento dichiarato: registra le chiamate, cosi' i test
    possono verificare anche cio' che NON deve succedere."""

    def __init__(self, vettore=None, esplode=False):
        self._vettore = [0.1, 0.2, 0.3] if vettore is None else vettore
        self._esplode = esplode
        self.chiamate: list[str] = []

    async def embed(self, text):
        self.chiamate.append(text)
        if self._esplode:
            raise RuntimeError("embedder giu' -- dettaglio che non deve uscire")
        return list(self._vettore)

    def dim(self):
        return 3


@pytest.mark.asyncio
async def test_save_memory_con_embedder_rotto_non_dichiara_di_aver_salvato(tmp_path):
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_save_memory(
        store, _Embedder(esplode=True), {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )

    assert res.get("error"), "senza embedding il salvataggio deve dichiarare l'errore"
    assert res.get("saved") is not True, "nessun successo apparente"
    assert "id" not in res
    # Nessuna riga scritta: un ricordo irraggiungibile non deve nemmeno esistere.
    assert store.list_items() == []
    # Il dettaglio dell'eccezione resta nel log del server.
    assert "embedder giu'" not in res["error"]
    store.close()


@pytest.mark.asyncio
async def test_save_memory_con_vettore_vuoto_non_dichiara_di_aver_salvato(tmp_path):
    """Il provider risponde ma senza vettore (caso del provider non
    configurato, che non solleva): stesso esito."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_save_memory(
        store, _Embedder(vettore=[]), {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )

    assert res.get("error")
    assert res.get("saved") is not True
    assert store.list_items() == []
    store.close()


@pytest.mark.asyncio
async def test_save_memory_riuscito_e_davvero_richiamabile(tmp_path):
    """Il percorso buono, verificato dal comportamento e non dalla colonna:
    salvato -> ritrovato dalla ricerca, che e' l'unico modo di richiamarlo."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    embedder = _Embedder()
    salvato = await handle_save_memory(
        store, embedder, {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )
    assert salvato.get("saved") is True

    ricordato = await handle_recall_memory(
        store, embedder, {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )
    assert [m["content"] for m in ricordato["memories"]] == ["preferisco 21 gradi"]
    store.close()


@pytest.mark.asyncio
async def test_save_memory_errore_dello_store_non_riporta_leccezione(tmp_path):
    """Regola del repo: mai fare echo di str(exc) verso il chiamante -- puo'
    contenere percorsi, host, stringhe di connessione."""

    class _StoreRotto:
        def add_item(self, **kwargs):
            raise RuntimeError("database bloccato su /data/knowledge.db")

    res = await handle_save_memory(
        _StoreRotto(), _Embedder(), {"content": "qualcosa"},
        owner="paolo", chatbot_id="agentA",
    )
    assert res.get("error")
    assert "/data/knowledge.db" not in res["error"]
    assert "database bloccato" not in res["error"]


@pytest.mark.asyncio
async def test_recall_memory_con_embedder_rotto_dichiara_il_guasto(tmp_path):
    """"Non ricordo nulla" e "non ho potuto guardare" non sono la stessa cosa:
    la seconda non deve mai arrivare all'utente travestita da prima."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    store.add_item(kind="memory", content="preferisco 21 gradi", owner="paolo",
                   chatbot_id="agentA", status="approved", embedding=[0.1, 0.2, 0.3])

    res = await handle_recall_memory(
        store, _Embedder(esplode=True), {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )

    assert res.get("error"), "il guasto della memoria semantica va dichiarato"
    assert not res.get("memories"), "nessun elenco che sembri una risposta"
    assert res.get("count") != 0, "zero risultati sarebbe una bugia: non si e' cercato"
    assert "embedder giu'" not in res["error"]
    store.close()


@pytest.mark.asyncio
async def test_recall_memory_con_vettore_vuoto_dichiara_il_guasto(tmp_path):
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_recall_memory(
        store, _Embedder(vettore=[]), {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )
    assert res.get("error")
    assert res.get("count") != 0
    store.close()


@pytest.mark.asyncio
async def test_il_guasto_di_recall_memory_non_porta_la_chiave_memories(tmp_path):
    """Fix 3 — la forma del guasto e' una scelta, e va pinnata.

    In caso di guasto la risposta NON porta `memories`/`count`: un chiamante
    che facesse `res["memories"]` deve fallire rumorosamente invece di leggere
    un vuoto silenzioso. Gli altri test qui sopra si accontentano di «elenco
    vuoto o assente, indifferentemente», quindi da soli lascerebbero
    riaggiungere l'elenco vuoto senza che nulla diventi rosso.
    """
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_recall_memory(
        store, _Embedder(esplode=True), {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )

    assert set(res) == {"error"}, "il guasto porta solo l'errore, nessun elenco"
    store.close()


@pytest.mark.asyncio
async def test_recall_memory_vuoto_legittimo_non_e_un_errore(tmp_path):
    """Il caso opposto, che deve restare distinguibile: la ricerca funziona e
    non trova nulla."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_recall_memory(
        store, _Embedder(), {"query": "qualunque cosa"},
        owner="paolo", chatbot_id="agentA",
    )
    assert "error" not in res
    assert res["memories"] == []
    assert res["count"] == 0
    store.close()


def test_descrizione_save_memory_non_promette_persistenza_illimitata():
    """La descrizione diceva "I ricordi persistono tra le conversazioni", ma
    esiste una scadenza configurabile (MEMORY_RETENTION_DAYS, 90 giorni per
    impostazione predefinita) che scrive `valid_until` e fa cancellare il
    ricordo da `purge_expired_chatbot`. La promessa va detta per intero."""
    descrizione = SAVE_MEMORY_TOOL_DEF["description"].lower()
    assert "scad" in descrizione, (
        "la descrizione deve nominare la scadenza dei ricordi, non solo la "
        "loro persistenza tra le conversazioni"
    )
