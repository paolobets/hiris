import pytest
from aiohttp import web

from hiris.app.api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
from hiris.app.reasoning.queue import ReasoningQueue


def _app(tmp_path):
    app = web.Application()
    q = ReasoningQueue(str(tmp_path / "r.db"))
    app["reasoning_queue"] = q
    app["_clock"] = lambda: 10.0
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)
    return app, q


@pytest.mark.asyncio
async def test_claim_returns_null_when_empty(aiohttp_client, tmp_path):
    app, _q = _app(tmp_path)
    client = await aiohttp_client(app)
    r = await client.post("/api/reasoning/claim")
    assert (await r.json())["job"] is None


# test_claim_then_submit_executes, che viveva qui, e' cancellato dalla fetta
# E3 Task 9 (rilievo 1 della review indipendente sul blocco 5-8): wirava
# `app["execute_decision"]` via `_app()` e verificava che un submit non-chat
# lo chiamasse (outcome "notify"). Quell'hook e' uscito per intero da
# handlers_reasoning.py -- non e' un ramo che si possa piu' wirare, ne' in
# produzione ne' nei test. Verificato che cade per costruzione prima della
# cancellazione: con l'hook rimosso l'assert diventava
# `'recorded' == 'notify'`, falso. Resta solo il test sotto, che oggi non e'
# piu' "il caso senza hook wired" ma l'UNICO comportamento possibile.


@pytest.mark.asyncio
async def test_submit_without_execute_decision_wired_records_and_logs(
    aiohttp_client, tmp_path, caplog
):
    """fetta E3 Task 4: server.py smise di wirare app["execute_decision"] --
    la ronda/revisione olistica che lo attuava era uscita, e con lei l'unico
    produttore di job non-"chat". fetta E3 Task 9: l'hook stesso e' uscito
    da handlers_reasoning.py (rilievo 1 della review indipendente) -- oggi
    non e' piu' "il caso in cui non e' wired", e' l'unico comportamento che
    il codice sa fare. Un submit non-chat che raggiunge questa rotta puo'
    arrivare solo da un job scaduto/legacy; non deve sparire in silenzio --
    resta "recorded" e logga un warning esplicito che nomina il job."""
    app = web.Application()
    q = ReasoningQueue(str(tmp_path / "r.db"))
    app["reasoning_queue"] = q
    app["_clock"] = lambda: 10.0
    # No app["execute_decision"] wired -- exactly like production since this task.
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info",
              "evidence": {}, "ts": 1.0}, {"snapshot": {}}, deadline_ts=100.0, job_id="J", now=1.0)
    client = await aiohttp_client(app)
    c = await (await client.post("/api/reasoning/claim")).json()
    assert c["job"]["job_id"] == "J"

    with caplog.at_level("WARNING", logger="hiris.app.api.handlers_reasoning"):
        r = await client.post("/api/reasoning/submit", json={
            "job_id": "J", "nonce": c["job"]["nonce"],
            "decision": {
                "verdict": "anomalia", "severity": "info", "message": "ok", "action": None,
            },
        })
    body = await r.json()
    assert body["ok"] is True and body["outcome"] == "recorded"
    assert any("execute_decision" in rec.message and "J" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_submit_delivers_reply_even_with_legacy_id_key_in_context(aiohttp_client, tmp_path):
    """fetta E4 Task 5 ("un bot solo"): handle_reasoning_submit non estrae
    piu' nessun chatbot_id/agent_id dal context -- chat_store non ne ha
    piu' bisogno, c'e' UNA cronologia. Prima di questo task, un job
    enqueued pre-deploy con SOLO `agent_id` nel context (prima della
    rinomina agent_id -> chatbot_id) dipendeva da un fallback a doppia
    chiave per non perdere la risposta; oggi il context non viene nemmeno
    piu' letto per un id, quindi qualunque chiave (o nessuna) ci sia
    dentro e' irrilevante -- verificato che questo pin cade per
    costruzione se si torna al vecchio `submit_chat_reply(chatbot_id,
    reply)`: `TypeError: _submit_chat_reply() takes 1 positional argument
    but 2 were given` nel chiamante reale (handlers_reasoning.py)."""
    app, q = _app(tmp_path)
    replies = []
    async def _submit_chat_reply(reply):
        replies.append(reply)
    app["submit_chat_reply"] = _submit_chat_reply
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, job_id="J", now=1.0)
    client = await aiohttp_client(app)
    c = await (await client.post("/api/reasoning/claim")).json()
    assert c["job"]["job_id"] == "J"
    r = await client.post("/api/reasoning/submit", json={"job_id": "J", "nonce": c["job"]["nonce"],
        "decision": {"reply": "ecco la risposta"}})
    body = await r.json()
    assert body["ok"] is True and body["outcome"] == "chat_reply_recorded"
    assert replies == ["ecco la risposta"]


@pytest.mark.asyncio
async def test_submit_bad_nonce_409(aiohttp_client, tmp_path):
    app, q = _app(tmp_path)
    q.enqueue("holistic", {}, {}, deadline_ts=100.0, job_id="J", now=1.0)
    await q.claim(now=10.0) if False else q.claim(now=10.0)
    client = await aiohttp_client(app)
    r = await client.post(
        "/api/reasoning/submit", json={"job_id": "J", "nonce": "bad", "decision": {}}
    )
    assert r.status == 409 and (await r.json())["ok"] is False
