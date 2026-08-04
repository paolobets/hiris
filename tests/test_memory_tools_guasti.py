"""A1/A3 — save_memory e recall_memory non devono dire una cosa e farne un'altra.

save_memory non rifiuta piu' un ricordo solo perche' manca il vettore: dopo la
fetta 2a `KnowledgeStore.search` degrada a `recent()` quando non c'e' un
vettore di query, quindi un ricordo senza embedding resta comunque
ritrovabile. Il salvataggio deve riuscire -- senza vettore, senza propagare
l'eccezione dell'embedder -- e, quando l'embedder funziona, il vettore deve
comunque essere calcolato e salvato esattamente come prima (nessuna
regressione).

Task 6 (fetta 2a): anche in lettura il rifiuto sparisce. Se il vettore di
ricerca non si calcola, `recall_memory` non risponde piu' con un errore: passa
a `KnowledgeStore.search` un vettore vuoto, che degrada da se' a `recent()`
(piu' recenti prima, stessi filtri di riservatezza). Il richiamo riesce
sempre; il risultato porta pero' `degraded: True` quando il confronto dei
significati non e' avvenuto, cosi' il modello puo' dirlo all'utente invece di
presentare i piu' recenti come i piu' pertinenti.
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
async def test_save_memory_con_embedder_rotto_salva_comunque_senza_vettore(tmp_path):
    """Un ricordo senza embedding resta comunque ritrovabile: dopo la fetta 2a
    `KnowledgeStore.search` degrada a `recent()` quando non c'e' un vettore di
    query. Un embedder che solleva non deve impedire di ricordare: il
    salvataggio riesce, senza vettore, senza propagare l'eccezione."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_save_memory(
        store, _Embedder(esplode=True), {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )

    assert res.get("saved") is True
    assert "error" not in res
    # La riga e' davvero nel db, recuperabile via store.recent() -- save_memory
    # scrive sempre status='approved', quindi (a differenza di save_knowledge)
    # e' il percorso di lettura corretto.
    trovati = store.recent(owner="paolo", chatbot_id="agentA", kinds=["memory"])
    assert [m["content"] for m in trovati] == ["preferisco 21 gradi"]
    assert trovati[0]["id"] == res["id"]
    item = store.get_item(res["id"])
    assert item["has_embedding"] is False
    store.close()


@pytest.mark.asyncio
async def test_save_memory_con_vettore_vuoto_salva_comunque_senza_vettore(tmp_path):
    """Il provider risponde ma senza vettore (caso del provider non
    configurato, che non solleva): stesso esito -- salvataggio riuscito."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    res = await handle_save_memory(
        store, _Embedder(vettore=[]), {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )

    assert res.get("saved") is True
    assert "error" not in res
    trovati = store.recent(owner="paolo", chatbot_id="agentA", kinds=["memory"])
    assert [m["content"] for m in trovati] == ["preferisco 21 gradi"]
    item = store.get_item(res["id"])
    assert item["has_embedding"] is False
    store.close()


@pytest.mark.asyncio
async def test_save_memory_con_embedder_funzionante_salva_ancora_il_vettore(tmp_path):
    """Nessuna regressione: se l'embedder c'e' e funziona, il vettore si
    calcola e si salva esattamente come prima -- pinnato via has_embedding,
    non per assunzione."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    embedder = _Embedder()
    res = await handle_save_memory(
        store, embedder, {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )

    assert res.get("saved") is True
    assert embedder.chiamate == ["preferisco 21 gradi"]
    item = store.get_item(res["id"])
    assert item["has_embedding"] is True
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
async def test_recall_memory_con_embedder_rotto_degrada_ai_piu_recenti(tmp_path):
    """Task 6: l'embedder che solleva non blocca piu' il richiamo. La ricerca
    degrada ai ricordi piu' recenti (KnowledgeStore.search -> recent()) invece
    di rifiutare, e l'eccezione non deve propagare al chiamante."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    store.add_item(kind="memory", content="preferisco 21 gradi", owner="paolo",
                   chatbot_id="agentA", status="approved", embedding=[0.1, 0.2, 0.3])

    res = await handle_recall_memory(
        store, _Embedder(esplode=True), {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )

    assert "error" not in res
    assert [m["content"] for m in res["memories"]] == ["preferisco 21 gradi"]
    assert res["count"] == 1
    assert res.get("degraded") is True, (
        "il richiamo degradato deve dichiararsi tale, non presentarsi come "
        "un confronto di significati"
    )
    store.close()


@pytest.mark.asyncio
async def test_recall_memory_con_vettore_vuoto_degrada_ai_piu_recenti(tmp_path):
    """Stesso esito quando il provider risponde ma senza vettore (caso del
    NullEmbedder di fabbrica, che non solleva)."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    store.add_item(kind="memory", content="preferisco 21 gradi", owner="paolo",
                   chatbot_id="agentA", status="approved", embedding=[0.1, 0.2, 0.3])

    res = await handle_recall_memory(
        store, _Embedder(vettore=[]), {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )
    assert "error" not in res
    assert [m["content"] for m in res["memories"]] == ["preferisco 21 gradi"]
    assert res.get("degraded") is True
    store.close()


@pytest.mark.asyncio
async def test_recall_memory_con_embedder_funzionante_non_degrada(tmp_path):
    """Nessuna regressione: con un vettore vero il richiamo ordina per
    somiglianza come prima e NON porta il segnale di degradazione."""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    store.add_item(kind="memory", content="preferisco 21 gradi", owner="paolo",
                   chatbot_id="agentA", status="approved", embedding=[0.1, 0.2, 0.3])

    res = await handle_recall_memory(
        store, _Embedder(), {"query": "temperatura"},
        owner="paolo", chatbot_id="agentA",
    )
    assert "error" not in res
    assert [m["content"] for m in res["memories"]] == ["preferisco 21 gradi"]
    assert not res.get("degraded"), (
        "una ricerca vettoriale vera non deve portare il segnale di degradazione"
    )
    store.close()


@pytest.mark.asyncio
async def test_recall_memory_degradato_applica_gli_stessi_filtri_di_riservatezza(tmp_path):
    """Task 6 punto 4: il richiamo degradato non deve perdere il filtro di
    riservatezza. Una riga sensibile non deve comparire a chi non puo'
    vederla -- una degradazione che perde un filtro e' una falla, non una
    degradazione. (recall_memory chiama sempre con allow_sensitive di default,
    quindi qui verifichiamo lo scoping owner/chatbot_id, l'altro asse che
    recall_memory applica.)"""
    store = KnowledgeStore(str(tmp_path / "memoria.db"))
    store.add_item(kind="memory", content="segreto di agentB", owner="paolo",
                   chatbot_id="agentB", status="approved", embedding=[0.1, 0.2, 0.3])
    store.add_item(kind="memory", content="nota di agentA", owner="paolo",
                   chatbot_id="agentA", status="approved", embedding=[0.1, 0.2, 0.3])

    res = await handle_recall_memory(
        store, _Embedder(vettore=[]), {"query": "qualunque cosa"},
        owner="paolo", chatbot_id="agentA",
    )
    assert res.get("degraded") is True
    contents = [m["content"] for m in res["memories"]]
    assert "segreto di agentB" not in contents
    assert contents == ["nota di agentA"]
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
