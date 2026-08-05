"""La prova che serviva -- il resoconto funziona a scatola chiusa.

Le task 1-4 della fetta 2a erano state verificate ognuna per conto suo, ma
nessuna attraversava l'intero percorso: una scadenza detta in chat, su
un'installazione senza alcun embedder configurato (il default di fabbrica),
che arriva davvero al resoconto delle 08:00. All'epoca quel percorso era rotto
in due punti indipendenti (handle_save_knowledge rifiutava di scrivere senza
un vettore; l'approvazione rispondeva 503 senza un provider configurato) --
entrambi chiusi dalla fetta 2a.

Task 2 (memoria unica) toglie un TERZO ostacolo dallo stesso percorso: non
c'e' piu' una coda da approvare. `handle_save_memory` scrive gia'
`status='approved'`, quindi il percorso e' oggi piu' corto -- salvato in chat
-> subito trovato da upcoming_obligations -> nel bundle del resoconto -- non
piu' lungo. Questo file usa il `NullEmbedder` VERO -- quello che gira in
produzione su ogni installazione stock -- non un finto, perche' e'
esattamente il caso che il difetto originale colpiva."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.briefing import build_briefing_bundle
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_scadenza_senza_embedder_arriva_al_resoconto(tmp_path):
    """Il percorso intero, su un'installazione di fabbrica (NullEmbedder):
    salvata in chat -> subito approvata (niente coda, Task 2) -> trovata da
    upcoming_obligations -> presente nel bundle del resoconto."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = NullEmbedder()
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()

    # 1. Salvata dalla chat, senza alcun embedder che calcoli un vettore.
    saved = await handle_save_memory(
        store, embedder,
        {
            "kind": "obligation",
            "content": "Revisione caldaia",
            "due_date": due,
        },
        owner="home", chatbot_id="hiris-default",
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

    # 4. E il bundle del resoconto delle 08:00 la include fra le scadenze.
    bundle = build_briefing_bundle(
        store, entity_cache=None, today=today, allow_sensitive=True,
        horizon_days=7, owner="home",
    )
    contenuti = [d["content"] for d in bundle["deadlines"]]
    assert "Revisione caldaia" in contenuti

    store.close()


@pytest.mark.asyncio
async def test_stesso_percorso_con_embedder_funzionante_non_regredisce(tmp_path):
    """Non-regresso: con un embedder che funziona lo stesso percorso continua
    a funzionare, e la riga porta gia' un vettore fin dal salvataggio."""
    from unittest.mock import AsyncMock
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()

    saved = await handle_save_memory(
        store, embedder,
        {
            "kind": "obligation",
            "content": "Revisione caldaia (con embedder)",
            "due_date": due,
        },
        owner="home", chatbot_id="hiris-default",
    )
    assert "error" not in saved
    assert saved.get("saved") is True

    item = store.get_item(saved["id"])
    assert item["status"] == "approved"
    assert item["has_embedding"]

    before = (today + timedelta(days=7)).isoformat()
    upcoming = store.upcoming_obligations(before=before, owner="home")
    assert any(row["id"] == saved["id"] for row in upcoming)

    bundle = build_briefing_bundle(
        store, entity_cache=None, today=today, allow_sensitive=True,
        horizon_days=7, owner="home",
    )
    contenuti = [d["content"] for d in bundle["deadlines"]]
    assert "Revisione caldaia (con embedder)" in contenuti

    store.close()


@pytest.mark.asyncio
async def test_save_memory_expense_conserva_amount_e_category(tmp_path):
    """Copertura persa da una pulizia precedente: `add_item` accetta ancora
    `amount` e `category`, alimentati da save_memory per kind='expense'."""
    from hiris.app.tools.memory_tools import handle_save_memory

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = NullEmbedder()

    saved = await handle_save_memory(
        store, embedder,
        {
            "kind": "expense",
            "content": "Bolletta del gas",
            "amount": 123.45,
            "category": "utenze",
        },
        owner="home", chatbot_id="hiris-default",
    )
    assert "error" not in saved

    item = store.get_item(saved["id"])
    assert item is not None
    assert item["amount"] == pytest.approx(123.45)
    assert item["category"] == "utenze"

    store.close()
