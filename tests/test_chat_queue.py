"""Slice 4b Task 1: kind="chat" reasoning jobs must route their submitted
reply into chat_store instead of actuating the house via execute_decision.

fetta E4 Task 5 ("un bot solo"): chat_store non ha piu' un `chatbot_id` --
c'e' UNA cronologia, non piu' una per agent. `submit_chat_reply` prende solo
`reply_text` e chiama `append_messages([{"role": "assistant", ...}], data_dir)`.
Il `context_json` di un job puo' ancora portare una chiave `chatbot_id`
(scritta da un client/server piu' vecchio, o qui sotto per continuare a
coprire "una chiave qualsiasi nel context non rompe nulla") ma
`handle_reasoning_submit` non la legge piu' -- vedi
tests/test_reasoning_api.py per quel caso.

Real APIs verified before writing this test:
- ReasoningQueue.enqueue(kind, wake, context, deadline_ts, *, job_id=None, now)
- ReasoningQueue.claim(now) -> dict with job_id/kind/context/nonce/status
- ReasoningQueue.submit(job_id, nonce, decision, now) -> bool
- ReasoningQueue.get(job_id) -> dict including "kind", "context", "decision"
- chat_store.append_messages(messages, data_dir)
- submit_chat_reply(reply_text) calls append_messages([{"role": "assistant", ...}], data_dir).
"""
import os

import pytest
from aiohttp import web

from hiris.app.api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
from hiris.app.chat_store import append_messages, close_all_stores, load_history
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _app(tmp_path, *, submit_chat_reply=None):
    app = web.Application()
    q = ReasoningQueue(str(tmp_path / "r.db"))
    app["reasoning_queue"] = q
    app["_clock"] = lambda: 10.0
    if submit_chat_reply is not None:
        app["submit_chat_reply"] = submit_chat_reply
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)
    return app, q


@pytest.mark.asyncio
async def test_chat_job_submit_routes_reply_to_submit_chat_reply(aiohttp_client, tmp_path):
    """fetta E3 Task 9: questo test wirava anche un `execute_decision` finto
    e verificava che NON venisse chiamato per un job kind="chat" -- da
    quando l'hook `app["execute_decision"]` e' uscito per intero
    (handlers_reasoning.py, rilievo 1 della review indipendente sul blocco
    5-8), quella distinzione non esiste piu': nessun kind lo chiama mai.
    Il soggetto vivo che resta -- un job "chat" instrada la risposta a
    submit_chat_reply -- e' l'unica cosa ancora verificata qui."""
    recorded = []

    async def _submit_chat_reply(reply_text):
        recorded.append(reply_text)

    app, q = _app(tmp_path, submit_chat_reply=_submit_chat_reply)
    q.enqueue("chat", {}, {"history": []}, deadline_ts=100.0, job_id="C1", now=1.0)
    client = await aiohttp_client(app)

    c = await (await client.post("/api/reasoning/claim")).json()
    assert c["job"]["job_id"] == "C1"
    assert c["job"]["kind"] == "chat"

    r = await client.post("/api/reasoning/submit", json={
        "job_id": "C1", "nonce": c["job"]["nonce"], "decision": {"reply": "ciao!"}})
    body = await r.json()

    assert body["ok"] is True
    assert recorded == ["ciao!"]


@pytest.mark.asyncio
async def test_chat_job_missing_reply_fails_closed_but_job_resolved(aiohttp_client, tmp_path):
    recorded = []

    async def _submit_chat_reply(reply_text):
        recorded.append(reply_text)

    app, q = _app(tmp_path, submit_chat_reply=_submit_chat_reply)
    q.enqueue("chat", {}, {}, deadline_ts=100.0, job_id="C2", now=1.0)
    client = await aiohttp_client(app)

    c = await (await client.post("/api/reasoning/claim")).json()
    r = await client.post("/api/reasoning/submit", json={
        "job_id": "C2", "nonce": c["job"]["nonce"], "decision": {"reply": ""}})
    body = await r.json()

    assert body["ok"] is True
    assert recorded == []  # empty reply -> no chat_store write

    job = q.get("C2")
    assert job["status"] == "decided"  # job still marked resolved


@pytest.mark.asyncio
async def test_chat_job_legacy_context_key_does_not_break_delivery(aiohttp_client, tmp_path):
    """fetta E4 Task 5 ("un bot solo"): un job rimasto in reasoning.db da
    prima di questo task puo' ancora portare `chatbot_id` nel proprio
    context_json (scritto da un server piu' vecchio) -- handle_reasoning_submit
    non lo legge piu' per niente, quindi quella chiave extra non deve
    impedire la consegna della risposta (prima del Task 5, un context senza
    ne' `chatbot_id` ne' `agent_id` faceva risolvere l'id a `None` e la
    consegna saltava -- vedi test_chat_job_missing_agent_id_fails_closed,
    cancellato qui: verificato che il suo assert `recorded == []` cadeva
    per costruzione, `AssertionError: assert ['ciao!'] == []`, prima di
    rimuoverlo -- oggi la consegna avviene SEMPRE che la reply sia
    presente, con o senza id nel context)."""
    recorded = []

    async def _submit_chat_reply(reply_text):
        recorded.append(reply_text)

    app, q = _app(tmp_path, submit_chat_reply=_submit_chat_reply)
    q.enqueue("chat", {}, {"chatbot_id": "agentX"}, deadline_ts=100.0, job_id="C3", now=1.0)
    client = await aiohttp_client(app)

    c = await (await client.post("/api/reasoning/claim")).json()
    r = await client.post("/api/reasoning/submit", json={
        "job_id": "C3", "nonce": c["job"]["nonce"], "decision": {"reply": "ciao!"}})
    body = await r.json()

    assert body["ok"] is True
    assert body["outcome"] == "chat_reply_recorded"
    assert recorded == ["ciao!"]
    assert q.get("C3")["status"] == "decided"


# test_non_chat_job_still_uses_execute_decision_unchanged, che viveva qui,
# e' cancellato dalla fetta E3 Task 9 (rilievo 1 della review indipendente
# sul blocco 5-8): verificava che un job non-chat facesse ancora chiamare
# `app["execute_decision"]" -- quel soggetto non esiste piu', l'hook e'
# uscito per intero da handlers_reasoning.py. Verificato che cade per
# costruzione prima della cancellazione: con l'hook rimosso l'assert
# `body["outcome"] == "notify"` falliva (`outcome` resta "recorded"). Il suo
# gemello per il caso "nessun hook wired" resta vivo in
# test_reasoning_api.py::test_submit_without_execute_decision_wired_records_and_logs
# -- e' quello, non piu' un ramo alternativo, il comportamento reale oggi.


@pytest.mark.asyncio
async def test_chat_job_missing_submit_chat_reply_handler_does_not_crash(aiohttp_client, tmp_path):
    """If app["submit_chat_reply"] isn't wired (misconfiguration), submit must
    still resolve the job instead of 500ing."""
    app, q = _app(tmp_path)  # no submit_chat_reply, no execute_decision
    q.enqueue("chat", {}, {}, deadline_ts=100.0, job_id="C4", now=1.0)
    client = await aiohttp_client(app)

    c = await (await client.post("/api/reasoning/claim")).json()
    r = await client.post("/api/reasoning/submit", json={
        "job_id": "C4", "nonce": c["job"]["nonce"], "decision": {"reply": "ciao!"}})
    body = await r.json()

    assert body["ok"] is True
    assert q.get("C4")["status"] == "decided"


@pytest.mark.asyncio
async def test_chat_reply_lands_in_real_chat_store(aiohttp_client, tmp_path):
    """End-to-end with the real chat_store.append_messages (server.py's
    submit_chat_reply wraps exactly this call)."""
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)

    async def _submit_chat_reply(reply_text):
        if not reply_text:
            return
        append_messages([{"role": "assistant", "content": reply_text}], data_dir)

    app, q = _app(tmp_path, submit_chat_reply=_submit_chat_reply)
    q.enqueue("chat", {}, {"history": []}, deadline_ts=100.0, job_id="C5", now=1.0)
    client = await aiohttp_client(app)

    c = await (await client.post("/api/reasoning/claim")).json()
    r = await client.post("/api/reasoning/submit", json={
        "job_id": "C5", "nonce": c["job"]["nonce"], "decision": {"reply": "risposta dalla coda"}})
    body = await r.json()
    assert body["ok"] is True

    history = load_history(data_dir)
    assert history == [{"role": "assistant", "content": "risposta dalla coda"}]
