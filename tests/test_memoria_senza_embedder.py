"""La prova che serviva -- la conoscenza arriva a scatola chiusa.

Le task 1-4 della fetta 2a erano state verificate ognuna per conto suo, ma
nessuna attraversava l'intero percorso: una scadenza detta in chat, su
un'installazione senza alcun embedder configurato (il default di fabbrica),
che arriva davvero fino a `upcoming_obligations`. All'epoca quel percorso era
rotto in due punti indipendenti (handle_save_knowledge rifiutava di scrivere
senza un vettore; l'approvazione rispondeva 503 senza un provider
configurato) -- entrambi chiusi dalla fetta 2a.

Task 2 (memoria unica) toglie un TERZO ostacolo dallo stesso percorso: non
c'e' piu' una coda da approvare. `handle_save_memory` scrive gia'
`status='approved'`, quindi il percorso e' oggi piu' corto -- salvato in chat
-> subito trovato da upcoming_obligations -- non piu' lungo. Questo file usa
il `NullEmbedder` VERO -- quello che gira in produzione su ogni installazione
stock -- non un finto, perche' e' esattamente il caso che il difetto
originale colpiva.

fetta E3 Task 6: il percorso arrivava fino al bundle del resoconto delle
08:00 (`brain/briefing.build_briefing_bundle`), uscito col Brain che parlava.
I due test end-to-end sotto perdono quell'ultimo passo -- non spostato,
cancellato: nessun codice compone piu' un resoconto da leggere. Il percorso
resta provato fino alla sua nuova destinazione reale, `upcoming_obligations`
(gia' provato di per se' anche da test_knowledge_store.py, ma qui
nell'attraversamento end-to-end salvataggio-senza-embedder che era il punto
del file)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.knowledge_store import KnowledgeStore


# fetta E2 Task 8 ("escono i trentaquattro"): `handle_save_memory` (tools/
# memory_tools.py) e' uscita -- orfana dal Task 7 (il `ToolDispatcher` che la
# chiamava e' uscito), nessun chiamante di produzione la invocava piu'. Questo
# file prova il percorso end-to-end (salvataggio -> upcoming_obligations ->
# resoconto), non l'orchestrazione del wrapper: `_salva` chiama KnowledgeStore
# direttamente, con lo stesso comportamento che il wrapper aveva per i kind
# non-'memory' che questo file esercita (nessuna provenienza chatbot_id,
# subito 'approved').
async def _salva(store: KnowledgeStore, embedder, *, kind: str, content: str,
                 owner: str = "home", due_date: str | None = None,
                 amount: float | None = None, category: str | None = None) -> dict:
    try:
        embedding = await embedder.embed(content)
    except Exception:
        embedding = None
    item_id = store.add_item(
        kind=kind, content=content, owner=owner, due_date=due_date,
        amount=amount, category=category, embedding=embedding or None,
        source="chat",
    )
    return {"saved": True, "id": item_id}


@pytest.mark.asyncio
async def test_scadenza_senza_embedder_arriva_a_upcoming_obligations(tmp_path):
    """Il percorso intero, su un'installazione di fabbrica (NullEmbedder):
    salvata in chat -> subito approvata (niente coda, Task 2) -> trovata da
    upcoming_obligations."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = NullEmbedder()
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()

    # 1. Salvata dalla chat, senza alcun embedder che calcoli un vettore.
    saved = await _salva(
        store, embedder,
        kind="obligation", content="Revisione caldaia", due_date=due,
        owner="home",
    )
    assert "error" not in saved
    assert saved.get("saved") is True

    # 2. Gia' approvata: niente coda da smaltire (Task 2).
    item = store.get_item(saved["id"])
    assert item is not None
    assert item["status"] == "approved"

    # 3. upcoming_obligations la trova, subito.
    before = (today + timedelta(days=7)).isoformat()
    upcoming = store.upcoming_obligations(before=before, owner="home")
    assert any(row["id"] == saved["id"] for row in upcoming)

    store.close()


@pytest.mark.asyncio
async def test_stesso_percorso_con_embedder_funzionante_non_regredisce(tmp_path):
    """Non-regresso: con un embedder che funziona lo stesso percorso continua
    a funzionare, e la riga porta gia' un vettore fin dal salvataggio."""
    from unittest.mock import AsyncMock

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()

    saved = await _salva(
        store, embedder,
        kind="obligation", content="Revisione caldaia (con embedder)", due_date=due,
        owner="home",
    )
    assert "error" not in saved
    assert saved.get("saved") is True

    item = store.get_item(saved["id"])
    assert item["status"] == "approved"
    assert item["has_embedding"]

    before = (today + timedelta(days=7)).isoformat()
    upcoming = store.upcoming_obligations(before=before, owner="home")
    assert any(row["id"] == saved["id"] for row in upcoming)

    store.close()


@pytest.mark.asyncio
async def test_save_memory_expense_conserva_amount_e_category(tmp_path):
    """Copertura persa da una pulizia precedente: `add_item` accetta ancora
    `amount` e `category`, alimentati da save_memory per kind='expense'."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = NullEmbedder()

    saved = await _salva(
        store, embedder,
        kind="expense", content="Bolletta del gas", amount=123.45, category="utenze",
        owner="home",
    )
    assert "error" not in saved

    item = store.get_item(saved["id"])
    assert item is not None
    assert item["amount"] == pytest.approx(123.45)
    assert item["category"] == "utenze"

    store.close()
