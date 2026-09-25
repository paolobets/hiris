"""Le chat divise, dalle rotte (fetta 2026-09-25, Task 3).

Spec `docs/design/2026-09-25-le-chat-divise.md` §3-§4: ogni soggetto, da ogni
ingresso, ha il suo filo -- cronologia, 409, poll, consegna del ponte, limite
dei turni. E la cronologia di prima va al proprietario, e a nessun altro.

Il confine vero (`middleware_internal_auth`) qui non c'e': lo sostituisce
`_finto_confine`, che scrive `soggetto`/`auth_via` sulla richiesta come fa lui,
leggendo CHI dall'intestazione di prova `X-Chi`. Le prove guardano il fatto --
lo status, il contenuto restituito, cio' che sta nell'archivio.
"""
import os
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hiris.app.api.handlers_chat import handle_chat, handle_chat_reply_poll
from hiris.app.api.handlers_chat_history import (
    handle_clear_chat_history,
    handle_get_chat_history,
)
from hiris.app.api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import append_messages, close_all_stores, load_history
from hiris.app.chat_thread import ChatThread
from hiris.app.reasoning.queue import ReasoningQueue
from tests.test_submit_chat_reply_guards import _load_real_submit_chat_reply

PAOLO = ChatThread("persona:paolo", "pannello")
MARTA = ChatThread("persona:marta", "pannello")


def _persona(pid):
    return {"specie": "persona", "id": pid, "nome": pid.title(), "utente": pid}


@web.middleware
async def _finto_confine(request, handler):
    chi = request.headers.get("X-Chi", "")
    if chi == "ponte":
        request["auth_via"] = "turno"
        request["soggetto"] = {"specie": "nessuno", "id": "ponte"}
    else:
        request["auth_via"] = "ingress"
        request["soggetto"] = _persona(chi)
    return await handler(request)


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


@pytest.fixture(autouse=True)
def il_piano_puo_rispondere(monkeypatch):
    # Stessa premessa di tests/test_chat_subscription_path.py: col token il
    # ponte esiste davvero e il turno si accoda invece di ripiegare.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")


class _FintoHA:
    """Gli utenti di Home Assistant: `paolo` proprietario, `marta` no."""

    async def users(self):
        return {"utenti": [
            {"id": "paolo", "amministratore": True, "proprietario": True},
            {"id": "marta", "amministratore": False, "proprietario": False},
        ]}


def _make_app(tmp_path, *, ponte_attivo=False, max_chat_turns=0):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="risposta sincrona")
    runner.last_tool_calls = []
    runner.last_thinking_blocks = []

    app = web.Application(middlewares=[_finto_confine])
    app["llm_router"] = runner
    app["claude_runner"] = runner
    app["chat_settings"] = ChatSettings(
        name="t", system_prompt="Sei HIRIS.", max_chat_turns=max_chat_turns)
    app["data_dir"] = data_dir
    app["bridge_active"] = ponte_attivo
    app["ha_client"] = _FintoHA()
    app["ruoli"] = {"quando": 0.0, "per_id": {}}
    q = ReasoningQueue(str(tmp_path / "reasoning.db"))
    app["reasoning_queue"] = q
    app["submit_chat_reply"] = _load_real_submit_chat_reply(app, data_dir)

    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)
    app.router.add_get("/api/chat/history", handle_get_chat_history)
    app.router.add_delete("/api/chat/history", handle_clear_chat_history)
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)
    return app, q, data_dir


def _contenuti(body):
    return [m["content"] for m in body["messages"]]


# 1. GET /api/chat/history: ognuno vede solo i suoi messaggi.
@pytest.mark.asyncio
async def test_la_cronologia_di_ognuno_e_solo_sua(tmp_path):
    app, _q, data_dir = _make_app(tmp_path)
    append_messages([{"role": "user", "content": "sono Paolo"}], data_dir, thread=PAOLO)
    append_messages([{"role": "user", "content": "sono Marta"}], data_dir, thread=MARTA)
    async with TestClient(TestServer(app)) as client:
        paolo = await (await client.get("/api/chat/history",
                                        headers={"X-Chi": "paolo"})).json()
        marta = await (await client.get("/api/chat/history",
                                        headers={"X-Chi": "marta"})).json()
    assert _contenuti(paolo) == ["sono Paolo"]
    assert _contenuti(marta) == ["sono Marta"]


# 2. DELETE di Marta non tocca il filo di Paolo.
@pytest.mark.asyncio
async def test_cancellare_la_propria_cronologia_non_tocca_quella_degli_altri(tmp_path):
    app, _q, data_dir = _make_app(tmp_path)
    append_messages([{"role": "user", "content": "sono Paolo"}], data_dir, thread=PAOLO)
    append_messages([{"role": "user", "content": "sono Marta"}], data_dir, thread=MARTA)
    async with TestClient(TestServer(app)) as client:
        resp = await client.delete("/api/chat/history", headers={"X-Chi": "marta"})
        assert resp.status == 200
    assert load_history(data_dir, thread=MARTA) == []
    assert load_history(data_dir, thread=PAOLO) == [
        {"role": "user", "content": "sono Paolo"}]


# 3 + 4. Il 409 e' per filo; il job porta filo e soggetto.
@pytest.mark.asyncio
async def test_una_risposta_in_volo_blocca_solo_il_suo_filo(tmp_path):
    app, q, _data_dir = _make_app(tmp_path, ponte_attivo=True)
    async with TestClient(TestServer(app)) as client:
        primo = await client.post("/api/chat", json={"message": "ciao"},
                                  headers={"X-Chi": "paolo"})
        assert primo.status == 202
        job_id = (await primo.json())["job_id"]

        marta = await client.post("/api/chat", json={"message": "ciao"},
                                  headers={"X-Chi": "marta"})
        assert marta.status == 202

        ancora_paolo = await client.post("/api/chat", json={"message": "ci sei?"},
                                         headers={"X-Chi": "paolo"})
        assert ancora_paolo.status == 409

    job = q.get(job_id)
    assert job["thread"] == PAOLO
    assert job["context"]["thread"] == {"subject_key": "persona:paolo",
                                        "entry_point": "pannello"}
    assert job["context"]["soggetto"] == _persona("paolo")


# 5. Il poll di un job altrui risponde come un id che non esiste.
@pytest.mark.asyncio
async def test_il_poll_di_un_job_altrui_e_un_404(tmp_path):
    app, _q, _data_dir = _make_app(tmp_path, ponte_attivo=True)
    async with TestClient(TestServer(app)) as client:
        primo = await client.post("/api/chat", json={"message": "ciao"},
                                  headers={"X-Chi": "paolo"})
        job_id = (await primo.json())["job_id"]

        altrui = await client.get(f"/api/chat/reply/{job_id}",
                                  headers={"X-Chi": "marta"})
        inesistente = await client.get("/api/chat/reply/non-esiste",
                                       headers={"X-Chi": "marta"})
        proprio = await client.get(f"/api/chat/reply/{job_id}",
                                   headers={"X-Chi": "paolo"})

        assert altrui.status == 404
        assert await altrui.json() == {"error": "not found"}
        assert await altrui.json() == await inesistente.json()
        assert proprio.status == 200
        assert (await proprio.json())["status"] == "pending"


# 6. La consegna del ponte scrive nel filo del job, non in un altro.
@pytest.mark.asyncio
async def test_la_risposta_del_ponte_arriva_nel_filo_di_chi_ha_chiesto(tmp_path):
    app, _q, data_dir = _make_app(tmp_path, ponte_attivo=True)
    async with TestClient(TestServer(app)) as client:
        primo = await client.post("/api/chat", json={"message": "che ore sono?"},
                                  headers={"X-Chi": "paolo"})
        assert primo.status == 202
        preso = await (await client.post("/api/reasoning/claim",
                                         headers={"X-Chi": "ponte"})).json()
        # Sul filo HTTP il filo del job viaggia come dizionario.
        assert preso["job"]["thread"] == {"subject_key": "persona:paolo",
                                          "entry_point": "pannello"}
        consegna = await client.post(
            "/api/reasoning/submit", headers={"X-Chi": "ponte"},
            json={"job_id": preso["job"]["job_id"], "nonce": preso["job"]["nonce"],
                  "decision": {"reply": "Sono le cinque."}})
        assert (await consegna.json())["outcome"] == "chat_reply_recorded"

    assert load_history(data_dir, thread=PAOLO) == [
        {"role": "user", "content": "che ore sono?"},
        {"role": "assistant", "content": "Sono le cinque."},
    ]
    assert load_history(data_dir, thread=MARTA) == []


# Un job di chat accodato prima della fetta non ha filo: la risposta non si
# scrive in un filo inventato.
@pytest.mark.asyncio
async def test_un_job_senza_filo_non_scrive_da_nessuna_parte(tmp_path, caplog):
    app, q, data_dir = _make_app(tmp_path)
    q.enqueue("chat", {}, {"history": []}, deadline_ts=9e12, job_id="VECCHIO", now=1.0)
    async with TestClient(TestServer(app)) as client:
        preso = await (await client.post("/api/reasoning/claim",
                                         headers={"X-Chi": "ponte"})).json()
        with caplog.at_level("WARNING"):
            consegna = await client.post(
                "/api/reasoning/submit", headers={"X-Chi": "ponte"},
                json={"job_id": "VECCHIO", "nonce": preso["job"]["nonce"],
                      "decision": {"reply": "risposta orfana"}})
        assert (await consegna.json())["outcome"] == "chat_reply_senza_filo"

    from hiris.app.chat_store import _get_store

    conn = _get_store(data_dir)._conn
    assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
    assert any("VECCHIO" in r.getMessage() for r in caplog.records)


# 7. Il limite dei turni e' per filo.
@pytest.mark.asyncio
async def test_il_limite_dei_turni_di_paolo_non_ferma_marta(tmp_path):
    app, _q, _data_dir = _make_app(tmp_path, max_chat_turns=1)
    async with TestClient(TestServer(app)) as client:
        primo = await client.post("/api/chat", json={"message": "uno"},
                                  headers={"X-Chi": "paolo"})
        assert (await primo.json())["response"] == "risposta sincrona"
        secondo = await (await client.post("/api/chat", json={"message": "due"},
                                           headers={"X-Chi": "paolo"})).json()
        marta = await (await client.post("/api/chat", json={"message": "uno"},
                                         headers={"X-Chi": "marta"})).json()
    assert secondo["error"] == "max_turns_reached"
    assert marta["response"] == "risposta sincrona"


def _semina_orfane(data_dir):
    """La cronologia di prima delle chat divise: una sessione aperta senza filo."""
    from hiris.app.chat_store import _get_store

    conn = _get_store(data_dir)._conn
    conn.execute("INSERT INTO chat_sessions(session_id, started_at, last_msg_at) "
                 "VALUES('prima', '2099-01-01T00:00:00Z', '2099-01-01T00:00:00Z')")
    conn.execute("INSERT INTO chat_messages(session_id, role, content, timestamp) "
                 "VALUES('prima', 'user', 'detto prima delle chat divise', "
                 "'2099-01-01T00:00:00Z')")
    conn.commit()


# 8. La cronologia di prima va al proprietario, e a nessun altro.
@pytest.mark.asyncio
async def test_la_cronologia_di_prima_va_al_proprietario(tmp_path):
    app, _q, data_dir = _make_app(tmp_path)
    _semina_orfane(data_dir)
    async with TestClient(TestServer(app)) as client:
        marta = await (await client.get("/api/chat/history",
                                        headers={"X-Chi": "marta"})).json()
        assert _contenuti(marta) == []
        from hiris.app.chat_store import has_orphans
        assert has_orphans(data_dir), "una non proprietaria non adotta nulla"

        paolo = await (await client.get("/api/chat/history",
                                        headers={"X-Chi": "paolo"})).json()
    assert _contenuti(paolo) == ["detto prima delle chat divise"]
    assert not has_orphans(data_dir)
