"""La prova che serviva -- il resoconto funziona a scatola chiusa.

Le task 1-4 di questa fetta sono state verificate ognuna per conto suo. Nessuna
delle due attraversa l'intero percorso: una scadenza detta in chat, su
un'installazione senza alcun embedder configurato (il default di fabbrica),
che arriva davvero al resoconto delle 08:00.

Oggi quel percorso era rotto in due punti indipendenti:
  1. `handle_save_knowledge` rifiutava di scrivere senza un vettore;
  2. anche se la scrittura fosse riuscita, `handle_approve` rispondeva 503
     senza un provider di embedding configurato.

Questo file usa il `NullEmbedder` VERO -- quello che gira in produzione su
ogni installazione stock -- non un finto, perche' e' esattamente il caso che
il difetto colpiva."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.briefing import build_briefing_bundle
from hiris.app.brain.knowledge_store import KnowledgeStore


def _app_approve(store, embedder):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    app = web.Application()
    app["knowledge_store"] = store
    app["embedding_provider"] = embedder
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    return app


@pytest.mark.asyncio
async def test_scadenza_senza_embedder_arriva_al_resoconto(aiohttp_client, tmp_path):
    """Il percorso intero, su un'installazione di fabbrica (NullEmbedder):
    salvata in chat -> pending -> approvata -> trovata da
    upcoming_obligations -> presente nel bundle del resoconto."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = NullEmbedder()
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()

    # 1. Salvata dalla chat, senza alcun embedder che calcoli un vettore.
    saved = await handle_save_knowledge(
        store, embedder,
        {
            "kind": "obligation",
            "content": "Revisione caldaia",
            "due_date": due,
        },
        owner="home",
    )
    assert "error" not in saved
    assert saved["status"] == "pending"

    # 2. La coda di approvazione non e' cambiata da questa fetta.
    item = store.get_item(saved["id"])
    assert item is not None
    assert item["status"] == "pending"

    # 3. Approvarla riesce -- prima di questa fetta rispondeva 503 qui.
    app = _app_approve(store, embedder)
    client = await aiohttp_client(app)
    r = await client.post(f"/api/knowledge/{saved['id']}/approve")
    assert r.status == 200
    approved = store.get_item(saved["id"])
    assert approved["status"] == "approved"

    # 4. upcoming_obligations la trova.
    before = (today + timedelta(days=7)).isoformat()
    upcoming = store.upcoming_obligations(before=before, owner="home")
    assert any(row["id"] == saved["id"] for row in upcoming)

    # 5. E il bundle del resoconto delle 08:00 la include fra le scadenze.
    bundle = build_briefing_bundle(
        store, entity_cache=None, today=today, allow_sensitive=True,
        horizon_days=7, owner="home",
    )
    contenuti = [d["content"] for d in bundle["deadlines"]]
    assert "Revisione caldaia" in contenuti

    store.close()


@pytest.mark.asyncio
async def test_stesso_percorso_con_embedder_funzionante_non_regredisce(
    aiohttp_client, tmp_path,
):
    """Non-regresso: con un embedder che funziona lo stesso percorso continua
    a funzionare, e la riga finisce per avere un vettore -- non solo la
    chiamata HTTP che riesce."""
    from unittest.mock import AsyncMock
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()

    saved = await handle_save_knowledge(
        store, embedder,
        {
            "kind": "obligation",
            "content": "Revisione caldaia (con embedder)",
            "due_date": due,
        },
        owner="home",
    )
    assert "error" not in saved
    assert saved["status"] == "pending"

    # Con l'embedder che funziona, save_knowledge calcola gia' il vettore:
    # la riga in coda lo porta prima ancora dell'approvazione.
    item = store.get_item(saved["id"])
    assert item["has_embedding"]

    app = _app_approve(store, embedder)
    client = await aiohttp_client(app)
    r = await client.post(f"/api/knowledge/{saved['id']}/approve")
    assert r.status == 200

    approved = store.get_item(saved["id"])
    assert approved["status"] == "approved"
    assert approved["has_embedding"]

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
async def test_save_knowledge_expense_conserva_amount_e_category(tmp_path):
    """Copertura persa da una pulizia precedente in questa fetta: `add_item`
    accetta ancora `amount` e `category`, alimentati da save_knowledge per
    kind='expense'. Nessun test esistente li esercitava piu'."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = NullEmbedder()

    saved = await handle_save_knowledge(
        store, embedder,
        {
            "kind": "expense",
            "content": "Bolletta del gas",
            "amount": 123.45,
            "category": "utenze",
        },
        owner="home",
    )
    assert "error" not in saved

    item = store.get_item(saved["id"])
    assert item is not None
    assert item["amount"] == pytest.approx(123.45)
    assert item["category"] == "utenze"

    store.close()
