"""Slice 4b Task 2: async subscription path for handle_chat.

When ``app["ponte_attivo"]`` is truthy AND the reasoning-queue
bridge is wired (``app["reasoning_queue"]`` present — see
``handlers_chat._bridge_on``), ``handle_chat`` must:
  1. persist the user turn to chat_store BEFORE enqueueing — otherwise a
     session could start on an assistant turn, which the Claude API rejects
     (contract from Task 1's report);
  2. enqueue a ``kind="chat"`` reasoning job whose context carries
     ``history``/``system_prompt`` (no id at all — see below);
  3. return HTTP 202 ``{"status": "pending", "job_id": ...}`` WITHOUT
     calling the runner.

Otherwise (flag off, or bridge not wired) the existing synchronous path is
unchanged — runner is called, 200 is returned.

A new ``GET /api/chat/reply/{job_id}`` route polls the same queue
(``ReasoningQueue.get``) and returns ``{"status": "pending"}`` until a
decision exists, then ``{"status": "done", "reply": ...}``.

fetta E4 Task 5 ("un bot solo"): chat_store lost the `chatbot_id` it used to
be keyed by (there's one conversation, full stop) — `append_messages`/
`load_history` take no id, and the enqueued job context no longer carries
one either (`handlers_chat.py::_enqueue_chat_job`).

Real APIs verified before writing this test (matches Task 1's report):
- ReasoningQueue.enqueue(kind, wake, context, deadline_ts, *, job_id=None, now)
- ReasoningQueue.get(job_id) -> dict with "kind"/"context"/"decision" (decision
  is None until ReasoningQueue.submit() has been called)
- ReasoningQueue.submit(job_id, nonce, decision, now) -> bool
- chat_store.append_messages(messages, data_dir) / chat_store.load_history(data_dir)
"""
import os
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock

from hiris.app.api.handlers_chat import handle_chat, handle_chat_reply_poll
from hiris.app.chat_store import append_messages, close_all_stores, load_history
from hiris.app.impostazioni_chat import ImpostazioniChat
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


@pytest.fixture(autouse=True)
def il_piano_puo_rispondere(monkeypatch):
    """Il token del piano, in tutti i test di questo file.

    Dal Task 14 «ponte acceso senza token» non e' piu' uno stato in cui il
    turno viene accodato e muore: e' un RIPIEGO -- il turno scende alla catena
    ed esce 200, sincrono. Un'app di prova col ponte acceso e senza token non
    descrive piu' il ponte, descrive il ripiego: senza questo token ogni test
    di questo file che parla di 202/job/context sarebbe diventato un test su
    un'altra cosa. Il token e' la condizione in cui il ponte esiste davvero, e
    si mette qui una volta sola; i test del ripiego se lo tolgono a mano
    (`monkeypatch.delenv`), e cosi' si leggono per quello che sono."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")


# fetta E4 Task 4 ("un bot solo"): non c'e' piu' un `Chatbot` per id da
# mockare -- `_make_agent`/l'`engine` MagicMock sono sostituiti da
# un'`ImpostazioniChat` vera. Il `chatbot_id`/`agent_id` che i test mandano
# nel body resta nel payload (continua a coprire "un id qualsiasi non rompe
# nulla"), ma non seleziona piu' niente. fetta E4 Task 5: nemmeno una
# chiave interna fissa resta -- chat_store e la coda non hanno proprio piu'
# un concetto di id (vedi handlers_chat.py).
def _make_impostazioni(*, max_chat_turns=0):
    return ImpostazioniChat(
        nome="test-agent",
        system_prompt="You are a helpful assistant.",
        max_chat_turns=max_chat_turns,
    )


def _make_app(tmp_path, *, ponte_attivo=False, with_queue=True, runner=None,
              max_chat_turns=0):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)

    impostazioni = _make_impostazioni(max_chat_turns=max_chat_turns)

    if runner is None:
        runner = AsyncMock()
        runner.chat = AsyncMock(return_value="sync reply")
        runner.last_tool_calls = []
        runner.last_thinking_blocks = []

    app = web.Application()
    app["llm_router"] = runner
    app["claude_runner"] = runner
    app["impostazioni_chat"] = impostazioni
    app["data_dir"] = data_dir
    app["ponte_attivo"] = ponte_attivo

    q = None
    if with_queue:
        q = ReasoningQueue(str(tmp_path / "reasoning.db"))
        app["reasoning_queue"] = q

    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)
    return app, q, runner, impostazioni, data_dir


# ---------------------------------------------------------------------------
# Flag + bridge gating
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flag_on_bridge_on_enqueues_pending_no_runner_call(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202
        body = await resp.json()
        assert body["status"] == "pending"
        assert isinstance(body["job_id"], str) and body["job_id"]

    runner.chat.assert_not_called()

    job = q.get(body["job_id"])
    assert job["kind"] == "chat"
    # fetta E4 Task 5 ("un bot solo"): il context del job non porta piu' un
    # chatbot_id -- non c'e' piu' nulla da instradare per chiave, c'e' UNA
    # conversazione.
    assert "chatbot_id" not in job["context"]


@pytest.mark.asyncio
async def test_context_del_job_porta_esattamente_queste_sei_chiavi_ne_una_di_piu(tmp_path):
    # fetta "il ponte riceve il nucleo" (parita' A, Task 4, Step 3): il pin
    # dell'INSIEME ESATTO -- il silenzio su cio' che NON attraversa il ponte.
    # Dopo i Task 1-4 il context porta `history` + `system_prompt` (originari,
    # Slice 4b) + `contesto` (Task 1/2) + `restrict_to_home`/`response_mode`
    # (Task 3) + `model` (Task 4, questo task). Chi resta fuori, e perche':
    #   - `thinking_budget` e `max_tokens` (CHAT_MAX_TOKENS): nessun
    #     equivalente sulla riga di comando della CLI `claude` -- non c'e'
    #     un `--thinking-budget` ne' un `--max-tokens` da passargli;
    #   - `nome`: non e' letto da nessuno dei due percorsi (sincrono o
    #     ponte), solo dal campo di compatibilita' `ImpostazioniChat.nome`
    #     stesso (impostazioni_chat.py);
    #   - gli strumenti (STRUMENTI_CONOSCENZA/dispatcher) e `debug`
    #     (tools_called/thinking_blocks): la fetta A non da' strumenti al
    #     ponte (regole-fetta.md), sono della fetta B.
    # Questo e' il test che impedisce a un task futuro di aggiungerne meta'
    # in silenzio, e quello che dice a chi verra' dopo dove guardare.
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202
        body = await resp.json()

    job = q.get(body["job_id"])
    assert set(job["context"]) == {
        "history", "system_prompt", "contesto",
        "restrict_to_home", "response_mode", "model",
    }


@pytest.mark.asyncio
async def test_flag_on_bridge_off_falls_back_to_sync(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


@pytest.mark.asyncio
async def test_flag_off_uses_sync_path_even_with_bridge_on(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=False, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


# ---------------------------------------------------------------------------
# Final-review Fix 1: max_chat_turns must be enforced BEFORE the subscription
# branch, not just on the sync path. Before the fix, an agent with a session
# turn limit chatted indefinitely once the bridge was on, because
# the check sat after the subscription branch's early return (unreachable in
# that mode).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_turns_reached_blocks_subscription_path(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    impostazioni.max_chat_turns = 1
    from hiris.app.chat_store import append_messages
    append_messages([
        {"role": "user", "content": "prima"},
        {"role": "assistant", "content": "risposta"},
    ], data_dir)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "seconda"})
        assert resp.status == 200
        body = await resp.json()
        assert body.get("error") == "max_turns_reached"
        assert body["turns"] == 1
        assert body["limit"] == 1

    runner.chat.assert_not_called()
    # Nothing must have been enqueued into the reasoning queue either.
    assert q.claim(now=time.time()) is None


@pytest.mark.asyncio
async def test_max_turns_not_reached_still_enqueues_on_subscription_path(tmp_path):
    """Sanity check: the hoisted check must not block turns that are still
    under the limit -- the subscription path must remain reachable."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    impostazioni.max_chat_turns = 5
    from hiris.app.chat_store import append_messages
    append_messages([
        {"role": "user", "content": "prima"},
        {"role": "assistant", "content": "risposta"},
    ], data_dir)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "seconda"})
        assert resp.status == 202
        body = await resp.json()
        assert body["status"] == "pending"

    runner.chat.assert_not_called()


# ---------------------------------------------------------------------------
# User message persisted BEFORE enqueue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_message_persisted_before_enqueue(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "salva questo"})
        assert resp.status == 202

    history = load_history(data_dir)
    assert history == [{"role": "user", "content": "salva questo"}]


@pytest.mark.asyncio
async def test_job_context_history_includes_current_user_turn(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "prima domanda"})
        body = await resp.json()

    job = q.get(body["job_id"])
    history = job["context"]["history"]
    assert history[-1] == {"role": "user", "content": "prima domanda"}
    # No leading assistant turn (Claude API would reject it).
    assert history[0]["role"] == "user"


# ---------------------------------------------------------------------------
# fetta "Modelli" (2.0), Task 12: il secondo lavoro di `giorni_conservazione`
# vale anche sul ramo del ponte (`_enqueue_chat_job`), non solo sul sincrono
# (vedi tests/test_api.py per il gemello sul ramo sincrono) -- il ponte non
# deve rileggere piu' conversazione di quanto l'utente abbia scelto.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_context_history_e_limitata_dai_giorni_di_conservazione(tmp_path):
    from datetime import datetime, timezone, timedelta
    from hiris.app.chat_store import _get_store

    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    impostazioni.giorni_conservazione = 5

    store = _get_store(data_dir)
    vecchio_ts = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ora_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at) VALUES(?,?,?)",
        ("sess-mista", vecchio_ts, ora_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
        ("sess-mista", "user", "messaggio di dieci giorni fa", vecchio_ts),
    )
    conn.commit()

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "prima domanda"})
        body = await resp.json()

    job = q.get(body["job_id"])
    contenuti = [m["content"] for m in job["context"]["history"]]
    assert "messaggio di dieci giorni fa" not in contenuti


# ---------------------------------------------------------------------------
# Poll route
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_route_pending_then_done(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda"})
        job_id = (await resp.json())["job_id"]

        poll1 = await client.get(f"/api/chat/reply/{job_id}")
        assert poll1.status == 200
        assert (await poll1.json()) == {"status": "pending"}

        # Simulate the external runner claiming + submitting a decision,
        # exactly like Task 1's submit path.
        claimed = q.claim(now=5.0)
        assert claimed["job_id"] == job_id
        ok = q.submit(job_id, claimed["nonce"], {"reply": "ecco la risposta"}, now=6.0)
        assert ok is True

        poll2 = await client.get(f"/api/chat/reply/{job_id}")
        assert poll2.status == 200
        assert (await poll2.json()) == {"status": "done", "reply": "ecco la risposta"}


@pytest.mark.asyncio
async def test_poll_route_unknown_job_id_404(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/chat/reply/does-not-exist")
        assert resp.status == 404


# ---------------------------------------------------------------------------
# Poll route: terminal states (Task 2, Fix 2) -- an expired job, a failed
# job, or a decided job whose decision carries no usable reply (Task 1's
# chat_reply_skipped outcome) must all poll as a TERMINAL error, never as
# pending-forever. Only genuinely still-in-flight jobs poll as "pending".
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_route_expired_job_returns_error_not_pending(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda"})
        job_id = (await resp.json())["job_id"]

        # Simulate the ponte-push sweep expiring the job (deadline passed,
        # no runner ever claimed/submitted it).
        q.sweep_expired(now=time.time() + 10 * 60)
        assert q.get(job_id)["status"] == "expired"

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()
        assert body["status"] == "error"
        assert "message" in body and body["message"]


@pytest.mark.asyncio
async def test_poll_route_failed_job_returns_error_not_pending(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda"})
        job_id = (await resp.json())["job_id"]

    # ReasoningQueue has no public API to force status='failed' directly;
    # write it through the same connection the queue already owns so this
    # test doesn't depend on internal column layout beyond the 'status' field
    # documented in reasoning/queue.py's _row().
    with q._lock:
        q._conn.execute("UPDATE reasoning_jobs SET status='failed' WHERE job_id=?", (job_id,))
        q._conn.commit()

    async with TestClient(TestServer(app)) as client:
        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()
        assert body["status"] == "error"


@pytest.mark.asyncio
async def test_poll_route_decided_without_usable_reply_returns_error(tmp_path):
    """Mirrors Task 1's chat_reply_skipped outcome: the job reached
    'decided' but the decision carries no truthy 'reply' (e.g. the runner's
    decision was empty/garbage). The UI must stop polling, not spin forever."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda"})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        ok = q.submit(job_id, claimed["nonce"], {"message": "no reply field here"}, now=6.0)
        assert ok is True
        assert q.get(job_id)["status"] == "decided"

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()
        assert body["status"] == "error"


@pytest.mark.asyncio
async def test_poll_route_pending_job_still_returns_pending(tmp_path):
    """Sanity check: a genuinely in-flight job (not yet claimed) still polls
    as pending -- the terminal-state handling must not regress this."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda"})
        job_id = (await resp.json())["job_id"]

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        assert (await poll.json()) == {"status": "pending"}


@pytest.mark.asyncio
async def test_poll_route_claimed_job_still_returns_pending(tmp_path):
    """A job claimed by the external runner but not yet submitted is still
    in-flight -- must poll as pending, not error."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda"})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        assert claimed["job_id"] == job_id
        assert q.get(job_id)["status"] == "claimed"

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        assert (await poll.json()) == {"status": "pending"}


# ---------------------------------------------------------------------------
# fetta "il ponte riceve gli strumenti" (parita' B, Task 5): `debug.tools_called`
# sul poll. Il giro completo -- accoda, il worker (qui simulato, come fa gia'
# `test_poll_route_pending_then_done` sopra, con `q.submit`) risolve con una
# `decision` che porta `tools_called`, e il poll la restituisce come
# `debug.tools_called`, nella STESSA forma del ramo sincrono
# (`handlers_chat.py`: `[{"tool": ..., "input": ...}, ...]`).
#
# Perche' conta piu' di una chiave in piu' nella risposta: da questa fetta
# `ricorda` (che scrive in `memoria.db`) e' raggiungibile ANCHE dal ponte, e
# con le sicurezze fuori dall'UAT (decisione del proprietario) questo e'
# l'UNICA cosa che rende visibile una scrittura in memoria fatta dal ponte --
# vedi il docstring in cima a `agent/runner.py`.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_route_decision_con_tools_called_porta_debug_nella_stessa_forma_del_sincrono(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ricordati che la caldaia perde"})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        assert claimed["job_id"] == job_id
        # La forma che `_reason_chat` produce davvero (agent/runner.py,
        # `_reply`): `reply` + `tools_called`, quest'ultima nella forma
        # ESATTA del ramo sincrono -- Step 6, ④ del brief: una chiamata a
        # `mcp__hiris__ricorda` compare nella lista, ed e' il caso che questo
        # task esiste per rendere visibile.
        ok = q.submit(job_id, claimed["nonce"], {
            "reply": "Preso nota: la caldaia perde.",
            "tools_called": [
                {"tool": "mcp__hiris__ricorda", "input": {"testo": "la caldaia perde"}},
            ],
        }, now=6.0)
        assert ok is True

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()

    assert body == {
        "status": "done",
        "reply": "Preso nota: la caldaia perde.",
        "debug": {"tools_called": [
            {"tool": "mcp__hiris__ricorda", "input": {"testo": "la caldaia perde"}},
        ]},
    }


@pytest.mark.asyncio
async def test_poll_route_decision_senza_tools_called_non_porta_debug(tmp_path):
    # Il complemento, e non un dettaglio: una `decision` senza la chiave (job
    # legacy accodato prima di questo deploy, o un mock) non deve inventarsi
    # un `debug` vuoto -- resta esattamente come prima di questo task
    # (`test_poll_route_pending_then_done`, sopra, lo pinna gia' su questo
    # stesso ramo: qui si pinna che il comportamento non e' cambiato).
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        ok = q.submit(job_id, claimed["nonce"], {"reply": "ciao anche a te"}, now=6.0)
        assert ok is True

        poll = await client.get(f"/api/chat/reply/{job_id}")
        body = await poll.json()

    assert body == {"status": "done", "reply": "ciao anche a te"}
    assert "debug" not in body


@pytest.mark.asyncio
async def test_poll_route_decision_con_tools_called_vuota_porta_comunque_debug(tmp_path):
    # Una lista VUOTA e' un turno vero senza chiamate -- non l'assenza della
    # chiave (quella e' il caso del test sopra). La chiave deve comparire lo
    # stesso, con la lista vuota dentro: e' cosi' che la E5 distingue "il
    # ponte ha girato e non ha chiamato nulla" da "questa decision non lo sa".
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "che ore sono?"})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        ok = q.submit(job_id, claimed["nonce"],
                      {"reply": "Sono le tre.", "tools_called": []}, now=6.0)
        assert ok is True

        poll = await client.get(f"/api/chat/reply/{job_id}")
        body = await poll.json()

    assert body == {"status": "done", "reply": "Sono le tre.",
                    "debug": {"tools_called": []}}


# ---------------------------------------------------------------------------
# Task 5: server.py wiring -- the addon option only takes effect when the
# bridge is ALSO truly usable (BRIDGE_ENABLED), otherwise chat jobs would be
# enqueued into a queue nothing sweeps/claims/prunes -> eternal pending + DB
# growth (the queue itself is created unconditionally in _on_startup, so
# handlers_chat._bridge_on's "queue present" check alone can't catch this).
#
# Full _on_startup is HA-client/engine-heavy and out of scope for a unit
# test here -- verified at the source level instead, same convention as the
# other inspect.getsource wiring tests in test_coverage_wiring.py (README'd
# as "runtime wiring verified separately via manual/integration checks").
# fetta E3 Task 5: the two examples this comment used to cite
# (test_coverage_review_runs_before_bridge_enabled_branch,
# test_suggestion_store_instantiated_in_server_source) exited with the
# Brain auto-proponente. fetta E3 Task 11: the next two examples
# (test_supervisor_client_lifecycle_wired_in_server_source,
# test_health_monitor_lifecycle_wired_in_server_source) exited with the
# HealthMonitor and SupervisorClient; the convention itself is unaffected.
# Review finale fetta E3, Minor: la dicitura "mqtt-heavy" e' uscita -- MQTT
# stesso e' uscito col Task 14 di questa fetta ("esce mqtt"), e questo file
# e' stato toccato dalla fetta senza aggiornare la nota.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# IL PONTE, DA DUE LEVE A UN VALORE SOLO (2.4.0 -> 3.0.0).
#
# Qui stavano sei test che pinnavano un AND: `_chat_subscription_active(cfg,
# bridge)` doveva essere `and`, mai `or`, perche' era il fail-safe numero uno
# del rilascio -- senza, si poteva instradare la chat in una coda che nessuno
# spazzava. Il proprietario ha fuso `bridge_enabled` e `chat_via_subscription`
# in un interruttore solo (`ponte.attivo`, 2.4.0): l'AND non ha piu' due valori
# da combinare, e quei sei test non hanno piu' un soggetto.
#
# Poi ne sono stati scritti quattro sulla forma intermedia -- `_ponte_attivo`
# come `or` fra l'interruttore e l'implicazione del piano -- e anche quelli
# hanno finito il loro soggetto con la versione B (3.0.0): `provider_
# subscription` e' uscita dallo schema, e con lei l'implicazione. Erano
# «il Piano Claude Max da solo basta» e «il piano implica il ponte solo se lo
# hai acceso TU», cioe' due affermazioni su un `or` che non c'e' piu'.
#
# Il fail-safe non e' stato rimosso in nessuno dei due passaggi: ha finito di
# cambiare natura. Da regola da non sbagliare (un `and` scritto a mano in due
# punti), a espressione condivisa (la stessa funzione chiamata due volte), a
# VALORE condiviso: `_ricalcola_catena` scrive `app["ponte_attivo"]`, e la
# spazzata e l'instradamento lo LEGGONO. Due letture dello stesso slot non
# possono divergere nemmeno per distrazione.
#
# Quello che segue pinna la forma di oggi, e soprattutto cio' che oggi NON deve
# poter tornare.
# ---------------------------------------------------------------------------

from hiris.app.server import _ponte_attivo


@pytest.mark.parametrize("archivio,atteso", [
    ({"ponte": {"attivo": True}}, True),
    ({"ponte": {"attivo": False}}, False),
    # Un archivio senza il blocco, o senza la chiave, o vuoto, o assente: il
    # ponte e' SPENTO. Non e' un dettaglio di robustezza -- e' la direzione in
    # cui l'ignoranza deve cadere. Se cadesse dall'altra parte, un archivio
    # illeggibile instraderebbe la chat su una coda che nessuno serve.
    ({"ponte": {}}, False),
    ({}, False),
    (None, False),
])
def test_il_ponte_e_un_valore_solo(archivio, atteso):
    """Prova per mutazione della forma finale.

    C'e' UN ingresso: l'archivio. Chiunque ne aggiunga un secondo -- un `or`
    con una credenziale (l'implicazione appena tolta), un `and` con un
    interruttore (la coppia di leve del 2023) -- deve far cadere qualcosa, e
    questo e' il posto.
    """
    assert _ponte_attivo(archivio) is atteso


def test_il_token_da_solo_non_accende_il_ponte(monkeypatch):
    """L'IMPLICAZIONE E' USCITA (versione B), ed e' il fatto piu' facile da
    rimettere per gentilezza.

    Fino alla 2.5.0 `provider_subscription` acceso col suo token accendeva il
    ponte da se' (`_sub_first_class`): chi stava nella configurazione
    consigliata non doveva accendere niente. Costava pero' l'ultima seconda
    rappresentazione del prodotto -- `app["ponte_attivo"]` poteva valere True
    mentre `ponte.attivo`, cioe' cio' che la pagina Modelli mostra e scrive,
    diceva False -- e rendeva IMPOSSIBILE spegnere il ponte a chiunque avesse
    un token, oltre a rendere inutile il bottone che lo accende.

    Il token c'e', l'archivio dice di no: il ponte e' spento. Chi lo aveva
    acceso attraverso il piano se lo sente dire all'avvio
    (`_avvisi_del_ponte`) e lo rivede in cima alla pagina Modelli, col gesto
    accanto.
    """
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert _ponte_attivo({"ponte": {"attivo": False}}) is False


def test_lo_stesso_gate_governa_la_spazzata_e_l_instradamento():
    """E' cosi' che il fail-safe regge ora che non c'e' piu' un AND.

    Prima l'invariante «non accodare mai in una coda che nessuno spazza» era
    una regola da non sbagliare: due opzioni distinte, combinate a mano nel
    punto giusto. Poi due chiamate alla stessa funzione. Adesso e' una
    struttura: `_ricalcola_catena` e' l'UNICO posto che deriva il valore, e
    `_reasoning_sweep` lo legge invece di ricalcolarlo. Se qualcuno riscrivesse
    uno dei due a mano, l'invariante tornerebbe a dipendere dall'attenzione:
    questo test lo impedisce, e guarda tutti e tre i lati.
    """
    import inspect

    from hiris.app import server

    ricalcola = inspect.getsource(server._ricalcola_catena)
    riga_cablaggio = [r for r in ricalcola.splitlines()
                      if 'app["ponte_attivo"] =' in r]
    assert len(riga_cablaggio) == 1, riga_cablaggio
    assert "_ponte_attivo(" in riga_cablaggio[0], (
        "il cablaggio non passa piu' dal combinatore condiviso: la logica "
        "booleana e' stata riscritta a mano nel punto di assegnazione"
    )

    src = inspect.getsource(server._on_startup)
    assert 'app["ponte_attivo"] =' not in src, (
        "il ponte e' tornato a essere cablato UNA volta all'avvio: da li' non "
        "puo' seguire un salvataggio della pagina Modelli, e accendere il "
        "ponte tornerebbe a essere una PUT che risponde 200 e non fa niente "
        "fino al riavvio"
    )

    sweep_pos = src.index("async def _reasoning_sweep()")
    corpo_sweep = src[sweep_pos:sweep_pos + 900]
    assert 'app.get("ponte_attivo")' in corpo_sweep, (
        "la spazzata non legge piu' il valore condiviso: puo' tornare a essere "
        "in disaccordo con l'instradamento, ed e' esattamente il buco che l'AND "
        "di prima serviva a chiudere"
    )
    assert "_ponte_attivo(" not in corpo_sweep, (
        "la spazzata RIDERIVA il valore invece di leggerlo: due derivazioni "
        "possono divergere, una lettura sola no"
    )


def test_il_ponte_non_ha_piu_nessuna_leva_nelle_opzioni_dell_addon():
    """Le due leve del 2023, e la terza del 2026, non devono rientrare dalla
    porta di servizio.

    Un'opzione vive in cinque posti: bastava che ne resuscitasse uno perche'
    tornasse a esserci una leva da tenere allineata a mano. Con la versione B
    non ne resta nessuna -- `ponte:` per intero e `provider_subscription` sono
    usciti -- e `server.py` non legge piu' nessuna delle due variabili
    d'ambiente per DECIDERE. `BRIDGE_ENABLED` resta nominata in una riga viva
    sola, quella della migrazione (`_catena_com_era`), che copia la catena
    com'era e non decide niente: si guarda quindi il gate, non il nome.
    """
    import pathlib as _pl

    import yaml

    base = _pl.Path(__file__).resolve().parents[1] / "hiris"
    cfg = yaml.safe_load((base / "config.yaml").read_text(encoding="utf-8"))
    for chiave in ("ponte", "provider_subscription", "chat_via_subscription"):
        assert chiave not in cfg["options"], chiave
        assert chiave not in cfg["schema"], chiave

    vive = [r for r in (base / "run.sh").read_text(encoding="utf-8").splitlines()
            if not r.lstrip().startswith("#")]
    for variabile in ("CHAT_VIA_SUBSCRIPTION", "BRIDGE_ENABLED",
                      "PROVIDER_SUBSCRIPTION"):
        assert not [r for r in vive if variabile in r], variabile

    for lingua in ("it", "en"):
        tradotte = yaml.safe_load(
            (base / "translations" / f"{lingua}.yaml").read_text(encoding="utf-8")
        )["configuration"]
        assert "ponte" not in tradotte
        assert "provider_subscription" not in tradotte

    app_py = (base / "app" / "server.py").read_text(encoding="utf-8").splitlines()
    codice = [r for r in app_py if not r.lstrip().startswith("#")]
    assert not [r for r in codice if 'env_bool("CHAT_VIA_SUBSCRIPTION")' in r]
    assert not [r for r in codice if 'env_bool("PROVIDER_SUBSCRIPTION")' in r], (
        "l'ultimo dei cinque interruttori e' tornato a decidere qualcosa"
    )
    # L'IMPLICAZIONE, non il suo nome: la docstring di `_ponte_attivo` racconta
    # apposta che cosa era `_sub_first_class` e perche' e' uscita, e una
    # docstring non e' un commento `#` -- il filtro qui sopra non la toglie. Si
    # guarda quindi la scrittura che la farebbe rientrare (l'assegnazione), non
    # la citazione che la spiega. Stesso criterio di
    # `test_chat_policy_e_uscita_da_tutti_e_cinque_i_posti`.
    assert not [r for r in codice if r.strip().startswith("_sub_first_class =")], (
        "l'implicazione «il piano acceso accende il ponte» e' rientrata"
    )


# ---------------------------------------------------------------------------
# I due avvisi d'avvio sul ponte. Vivevano in `run.sh` e leggevano
# PROVIDER_SUBSCRIPTION/BRIDGE_ENABLED; con la versione B quelle opzioni non
# esistono e il ponte vive nell'archivio, che da uno script di avvio non si
# legge. Non si cancellano -- descrivono i due stati che costano soldi senza
# dirlo -- si spostano dove l'archivio c'e'.
# ---------------------------------------------------------------------------

from hiris.app.server import _avvisi_del_ponte


def test_il_ponte_acceso_senza_token_si_sente_dire_all_avvio():
    """Invariante 5, nel registro. Dal Task 14 il turno non si perde piu' (scende
    alla catena), ma scende a un provider a consumo: un ripiego silenzioso dal
    forfait al consumo si scopre a fine mese."""
    righe = _avvisi_del_ponte(True, False)
    assert len(righe) == 1, righe
    assert "dal forfait al consumo" in righe[0], righe[0]
    # Il campo si nomina col nome VERO, come il 503 di primo avvio: mandare a
    # cercare un'etichetta che non esiste e' il difetto che il Task 15 ha chiuso.
    assert "«Provider · Piano Claude Max — token»" in righe[0], righe[0]


def test_il_token_senza_ponte_si_sente_dire_all_avvio_DOVE_si_accende():
    """Lo stato in cui si ritrova chi aggiorna alla 3.0.0 avendo il piano acceso
    via `provider_subscription` senza aver mai acceso il ponte: l'implicazione
    e' uscita, e la copia d'archivio della 2.5.0 aveva copiato l'OPZIONE
    `ponte.attivo`, non lo stato effettivo. Il ponte si spegne.

    E' l'unica perdita di comportamento di questa versione, e questa riga e'
    cio' che la rende rumorosa invece che silenziosa. Deve dire anche DOVE si
    ripara: mandare a cercare l'opzione nell'add-on sarebbe mandare a cercare
    un campo che non esiste piu'."""
    righe = _avvisi_del_ponte(False, True)
    assert len(righe) == 1, righe
    assert "pagina Modelli" in righe[0], righe[0]
    assert "a consumo" in righe[0], righe[0]
    assert "Configurazione add-on" not in righe[0], (
        "l'avviso manda ancora a cercare un'opzione dell'add-on che non c'e' piu'"
    )


@pytest.mark.parametrize("ponte,token", [(True, True), (False, False)])
def test_gli_stati_sani_non_dicono_niente(ponte, token):
    """Il gemello obbligatorio: un avviso che compare sempre e' rumore, e il
    rumore e' cio' che ha fatto scorrere via l'avvio dal registro consegnato col
    cancello di questa fetta. Ponte acceso col token e ponte spento senza token
    sono due stati COERENTI: non c'e' niente da dire."""
    assert _avvisi_del_ponte(ponte, token) == []


# ---------------------------------------------------------------------------
# fetta «il ponte riceve il nucleo» (parita' A, Task 2): il job accodato porta
# anche il CONTESTO della casa. Prima di questa fetta il ponte riceveva solo
# `history` + `system_prompt` e rispondeva senza sapere nulla della casa,
# mentre il percorso sincrono aveva il nucleo: era la disparita' che la fetta
# chiude. Il pin decisivo non e' "il contesto c'e'" ma "e' IDENTICO a quello
# del ramo sincrono": entrambi vengono da `componi_contesto_chat`, e due
# composizioni separate divergerebbero in silenzio (la "funzione doppia"
# vietata da CLAUDE.md).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_context_porta_il_nucleo_identico_al_ramo_sincrono(tmp_path):
    from hiris.app.api.handlers_chat import componi_contesto_chat
    from hiris.app.casa.archivio import ArchivioCasa
    from hiris.app.memoria.archivio import ArchivioMemoria

    app, q, runner, impostazioni, data_dir = _make_app(
        tmp_path, ponte_attivo=True, with_queue=True)

    archivio_casa = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio_casa.sostituisci({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [],
        "entita": [{"entity_id": "light.cucina", "name": "Faretti",
                    "area_id": "cucina"}],
        "etichette": [], "categorie": [], "integrazioni": [],
    })
    archivio_memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    archivio_memoria.ricorda("La cucina ha i faretti dimmerabili", "paolo")
    app["archivio_casa"] = archivio_casa
    app["archivio_memoria"] = archivio_memoria

    try:
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat", json={"message": "che c'e' in cucina?"})
            assert resp.status == 202
            body = await resp.json()

        job = q.get(body["job_id"])
        contesto = job["context"]["contesto"]

        # ① la casa seminata e' arrivata davvero al ponte -- le sezioni del
        # nucleo, la stanza seminata e il ricordo seminato
        assert "## La casa" in contesto and "Cucina" in contesto
        assert "## Cio' che le persone hanno detto" in contesto
        assert "faretti dimmerabili" in contesto

        # ② ed e' ESATTAMENTE la stringa che il ramo sincrono compone per la
        # stessa app: se un giorno i due percorsi divergono, questo assert e'
        # il primo a saperlo.
        assert contesto == componi_contesto_chat(app, data_dir)
    finally:
        archivio_casa.chiudi()
        archivio_memoria.chiudi()


# ---------------------------------------------------------------------------
# fetta E5 Task 2, fix round 1 (I-2): thinking_budget non attraversa il ponte,
# e da oggi lo dice. Il pin dell'INSIEME ESATTO delle sei chiavi (sopra)
# certifica l'ASSENZA; questo certifica che l'assenza non sia piu' MUTA.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_ponte_dichiara_che_thinking_budget_non_viene_applicato(tmp_path, caplog):
    """Il tester imposta 8000 dalla pagina «Impostazioni chat», legge
    «Salvato», e in modalita' abbonamento non ottiene nessun ragionamento
    esteso: la CLI di Claude Code non ha un budget per richiesta da ricevere.
    Fino al fix round 1 non c'era una riga da nessuna parte -- l'impostazione
    risultava salvata e non faceva niente, in silenzio."""
    app, q, runner, impostazioni, data_dir = _make_app(
        tmp_path, ponte_attivo=True, with_queue=True)
    app["impostazioni_chat"] = ImpostazioniChat(
        nome="test-agent", system_prompt="You are a helpful assistant.",
        thinking_budget=8000,
    )
    with caplog.at_level("WARNING"):
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat", json={"message": "ciao"})
            assert resp.status == 202

    detto = " ".join(r.getMessage() for r in caplog.records)
    assert "thinking_budget=8000" in detto, "il valore scartato va detto"
    assert "NON viene applicato" in detto
    assert "resta salvata" in detto, "deve dire che l'impostazione risulta salvata"
    # L'assenza dal context resta vera e non si aggira: la certifica il pin
    # dell'insieme esatto delle sei chiavi, qui sopra in questo stesso file.


@pytest.mark.asyncio
async def test_il_ponte_non_dice_niente_con_thinking_budget_a_zero(tmp_path, caplog):
    """A 0 (il default) non c'e' niente da dichiarare: un warning a ogni turno
    su ogni installazione sarebbe rumore che insegna a ignorare i log."""
    app, q, runner, impostazioni, data_dir = _make_app(
        tmp_path, ponte_attivo=True, with_queue=True)
    with caplog.at_level("WARNING"):
        async with TestClient(TestServer(app)) as client:
            assert (await client.post("/api/chat", json={"message": "ciao"})).status == 202
    assert not [r for r in caplog.records if "thinking_budget" in r.getMessage()]


# ---------------------------------------------------------------------------
# fetta «la catena diventa l'unica verita'» (Task 4): lo scavalco del modello
# esce da «Impostazioni chat». I DUE percorsi devono chiedere `auto`: uno solo
# dei due sarebbe mezza impostazione che scavalca, cioe' peggio di prima.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_turno_sincrono_chiede_sempre_auto_e_quindi_sempre_la_catena(tmp_path):
    """Fino alla 2.4.1 un modello fissato in «Impostazioni chat» sceglieva il
    provider da solo (`LLMRouter._route`), saltava la catena e annullava il
    ripiego -- e la pagina Modelli non lo nominava mai. Il campo è uscito: da
    qui in poi il turno chiede sempre `auto`, cioè sempre la catena."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
    assert runner.chat.await_args.kwargs["model"] == "auto"


@pytest.mark.asyncio
async def test_il_ponte_risolve_il_modello_dalla_pagina_modelli_non_dalle_impostazioni(tmp_path):
    """La gemella sull'ALTRO percorso. `_enqueue_chat_job` compone il modello
    della CLI da `resolve_model("auto", "chat", provider_models["claude"])`:
    la sorgente è la pagina Modelli, per provider. Se un giorno tornasse a
    leggere un campo delle impostazioni, questo test cadrebbe con `sonnet`."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=True)
    app["models_config"] = {"provider_models": {"claude": "claude-opus-4-7"}}
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202
        body = await resp.json()
    assert q.get(body["job_id"])["context"]["model"] == "opus"


# ---------------------------------------------------------------------------
# La scadenza del turno viene dall'ARCHIVIO (Task 10)
#
# Fino alla 2.4.1 `_enqueue_chat_job` leggeva `BRIDGE_DEADLINE_MIN`, cioe'
# l'opzione dell'add-on, mentre `models_config["ponte"]["scadenza_min"]` ne
# teneva una copia (Task 6) che nessuno leggeva e che la pagina Modelli poteva
# riscrivere: due rappresentazioni dello stesso numero, e quella che l'utente
# cambiava non era quella che il turno subiva. In piu' la pagina dichiarava il
# numero d'ambiente sul connettore del piano, quindi mostrava un'attesa e ne
# applicava un'altra appena qualcuno salvava da li'.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_la_scadenza_del_turno_viene_dall_archivio_non_dall_ambiente(
        tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_DEADLINE_MIN", "44")
    app, q, runner, _imp, _dd = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    app["models_config"] = {"ponte": {"scadenza_min": 9}}

    prima = time.time()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202
        job_id = (await resp.json())["job_id"]
    dopo = time.time()

    attesa = q.get(job_id)["deadline_ts"]
    assert prima + 9 * 60 <= attesa <= dopo + 9 * 60, (
        "il turno scade col numero che l'utente ha salvato, non con quello "
        "dell'opzione dell'add-on"
    )


@pytest.mark.asyncio
async def test_senza_archivio_la_scadenza_resta_il_predefinito_di_sempre(tmp_path):
    """`_on_startup` puo' non essere girato (ogni fixture lo azzera) e un turno
    puo' comunque arrivare: cinque minuti, come il predefinito dell'archivio e
    dell'opzione da cui e' stato seminato."""
    app, q, runner, _imp, _dd = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    assert "models_config" not in app

    prima = time.time()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        job_id = (await resp.json())["job_id"]
    dopo = time.time()
    attesa = q.get(job_id)["deadline_ts"]
    assert prima + 5 * 60 <= attesa <= dopo + 5 * 60


# ---------------------------------------------------------------------------
# fetta «la catena diventa l'unica verita'», Task 14: IL PONTE DIVENTA UN
# ANELLO.
#
# Il proprietario aveva chiesto una cosa sola, con parole sue: «utilizza
# abbonamento, ma se token finiti o per qualsiasi altro motivo non e'
# accessibile, utilizza OpenRouter o altro». Non era un difetto
# dell'interfaccia: quel comportamento non esisteva. Il ponte era un BIVIO a
# monte del router, e chi lo prendeva non tornava indietro -- se il piano non
# rispondeva, il turno moriva, e la catena non veniva consultata mai.
#
# Il ripiego si fa in DUE META' separate, e i test qui sotto seguono la stessa
# divisione:
#   - a monte, sincrono: il piano NON PUO' ricevere il turno (manca il token,
#     oppure il tetto giornaliero e' pieno). Non si accoda niente, si scende
#     alla catena nella stessa richiesta, 200.
#   - a valle, alla scadenza: il turno era stato accodato e il piano non ha
#     risposto in tempo. Il ripiego avviene nella ROTTA DI POLL, e la risposta
#     arriva sullo STESSO job -- il browser non cambia niente.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_senza_token_il_turno_scende_alla_catena_invece_di_scadere(tmp_path, monkeypatch):
    """Lo stato dell'invariante 5, visto dal lato della chat: il ponte e'
    acceso, il worker non parte (`should_start_agent_worker` pretende il
    token), e fino alla 2.4.1 il messaggio veniva accodato e scadeva dopo
    cinque minuti. Adesso passa al provider successivo."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        assert (await resp.json())["response"] == "sync reply"
    runner.chat.assert_awaited_once()
    # E niente e' stato accodato: non si mette un messaggio in una coda che
    # nessuno servira'.
    assert q.count_chat_today() == 0


@pytest.mark.asyncio
async def test_col_tetto_pieno_il_turno_scende_alla_catena_invece_di_dare_429(tmp_path):
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    app["models_config"] = {"ponte": {"tetto_giornaliero": 0}}
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
    runner.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_una_risposta_gia_in_volo_NON_ripiega(tmp_path):
    """Due risposte in volo sulla stessa conversazione sarebbero peggio del
    409: la seconda arriverebbe in una cronologia che la prima sta per
    riscrivere. La guardia sta PRIMA di «il piano puo' rispondere?» apposta --
    col tetto pieno il ripiego partirebbe verso la catena mentre il ponte ha
    ancora un turno in volo che si scrivera' in cronologia da solo."""
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    app["models_config"] = {"ponte": {"tetto_giornaliero": 0}}
    q.enqueue("chat", {}, {}, time.time() + 300, now=time.time())
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 409
    runner.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_i_tre_motivi_del_ripiego_sono_quelli_che_la_nota_sa_dire(tmp_path, monkeypatch):
    """Il test che lega i due file.

    `_piano_puo_rispondere` restituisce una PAROLA, e quella parola dev'essere
    una chiave di `decisione_modelli._MOTIVI_RIPIEGO`, o la nota non si scrive.
    Non produrrebbe un errore: produrrebbe silenzio, cioe' un ripiego dal
    forfait al consumo che non si annuncia -- esattamente cio' che la decisione
    del proprietario vieta. Nessun test lo direbbe, perche' la nota e'
    facoltativa per costruzione."""
    from hiris.app.api.handlers_chat import _piano_puo_rispondere
    from hiris.app.decisione_modelli import _MOTIVI_RIPIEGO

    app, q, _, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    puo, motivo = _piano_puo_rispondere(app)
    assert puo is False and motivo in _MOTIVI_RIPIEGO, motivo

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    app["models_config"] = {"ponte": {"tetto_giornaliero": 0}}
    puo, motivo = _piano_puo_rispondere(app)
    assert puo is False and motivo in _MOTIVI_RIPIEGO, motivo

    app["models_config"] = {"ponte": {"tetto_giornaliero": 50}}
    assert _piano_puo_rispondere(app) == (True, "")

    # E la terza chiave e' quella del ripiego a valle, che non passa da
    # `_piano_puo_rispondere`: la scrive `_ripiega_sulla_catena`.
    assert "scadenza" in _MOTIVI_RIPIEGO


# ── L'annuncio: il ripiego si dichiara, ogni volta ─────────────────────────


def _con_registro(app, *, catena, chi_ha_risposto=None):
    """Un registro degli esiti VERO, non una finta comoda.

    Chi ha risposto si MISURA: si scrive un successo su un solo backend e si
    lascia che l'helper lo trovi scorrendo la catena. Se il ripiego nominasse
    `catena_modelli[0]` invece di chi ha davvero risposto, i test che mettono
    un fallimento in testa lo direbbero."""
    from hiris.app.esiti_provider import RegistroEsiti

    registro = RegistroEsiti(orologio=lambda: 1000.0)
    app["registro_esiti"] = registro
    app["catena_modelli"] = list(catena)
    if chi_ha_risposto:
        registro.successo(chi_ha_risposto)
    return registro


@pytest.mark.asyncio
async def test_il_ripiego_a_monte_si_annuncia_e_dice_chi_ha_risposto(tmp_path, monkeypatch):
    """Decisione del proprietario, 13 agosto: il ripiego si annuncia OGNI
    VOLTA, perche' un passaggio silenzioso dal forfait al consumo si scopre a
    fine mese."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    _con_registro(app, catena=["claude", "openrouter"], chi_ha_risposto="openrouter")
    async with TestClient(TestServer(app)) as client:
        body = await (await client.post("/api/chat", json={"message": "ciao"})).json()
    assert body["nota"] == (
        "Il Piano Claude Max non ha un token con cui rispondere: ha risposto "
        "OpenRouter, a consumo.")
    # La forma della risposta NON cambia: `nota` si aggiunge, non sostituisce.
    assert body["response"] == "sync reply"
    assert body["debug"] == {"tools_called": []}


@pytest.mark.asyncio
async def test_la_nota_nomina_CHI_HA_RISPOSTO_non_il_primo_della_catena(tmp_path, monkeypatch):
    """La trappola di questo passo. Il router RIPIEGA: il primo della catena
    puo' aver fallito e aver risposto il secondo. Una nota che nomina il
    provider sbagliato afferma piu' di quanto il sistema sa -- e per giunta sui
    soldi, che e' la meta' per cui la nota esiste."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    registro = _con_registro(app, catena=["claude", "openrouter"])
    registro.fallimento("claude", famiglia="credenziale", codice=400,
                        messaggio="credit balance too low", durata_s=0.3)
    registro.successo("openrouter")
    async with TestClient(TestServer(app)) as client:
        body = await (await client.post("/api/chat", json={"message": "ciao"})).json()
    assert "OpenRouter" in body["nota"]
    assert "Claude API" not in body["nota"]


@pytest.mark.asyncio
async def test_senza_sapere_chi_ha_risposto_la_nota_non_si_scrive(tmp_path, monkeypatch):
    """Meglio nessuna nota che una che nomina il provider sbagliato: la nota
    parla di soldi, e una nota falsa sui soldi e' peggio del silenzio."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    app["registro_esiti"] = None
    app["catena_modelli"] = []
    async with TestClient(TestServer(app)) as client:
        body = await (await client.post("/api/chat", json={"message": "ciao"})).json()
    assert "nota" not in body
    assert body["response"] == "sync reply"


@pytest.mark.asyncio
async def test_un_turno_che_NON_ha_ripiegato_non_porta_nessuna_nota(tmp_path):
    """La prova gemella: la nota non e' una riga che si scrive sempre. Col
    ponte spento non c'e' stato nessun ripiego da annunciare, e il registro
    porta un successo -- cioe' tutto quello che serve per scriverla per
    sbaglio."""
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=False, with_queue=True)
    _con_registro(app, catena=["openrouter"], chi_ha_risposto="openrouter")
    async with TestClient(TestServer(app)) as client:
        body = await (await client.post("/api/chat", json={"message": "ciao"})).json()
    assert "nota" not in body


# ── La seconda meta': il ripiego alla scadenza ─────────────────────────────
#
# La finta mente come mente la realta': il job si accoda con una scadenza GIA'
# PASSATA (`ora - 1`) e una nascita nel passato (`now=ora - 300`), cioe'
# esattamente cio' che il poll trova quando il piano non ha risposto. Nessuna
# finta che restituisca subito l'esito comodo: il tempo e' passato davvero, e
# il runner della catena e' quello vero della fixture.


def _accoda_scaduto(q, *, ora=None, history=None, **contesto):
    ora = time.time() if ora is None else ora
    ctx = {"history": history if history is not None
           else [{"role": "user", "content": "ciao"}]}
    ctx.update(contesto)
    return q.enqueue("chat", {}, ctx, ora - 1, now=ora - 300)


@pytest.mark.asyncio
async def test_alla_scadenza_il_turno_passa_alla_catena_e_la_risposta_arriva_sullo_stesso_job(tmp_path):
    app, q, runner, _, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    jid = _accoda_scaduto(q, system_prompt="p", contesto="c",
                          restrict_to_home=False, response_mode="auto",
                          model="sonnet")
    async with TestClient(TestServer(app)) as client:
        body = await (await client.get("/api/chat/reply/" + jid)).json()
    assert body == {"status": "done", "reply": "sync reply"}
    kwargs = runner.chat.await_args.kwargs
    # La cronologia del job CONTIENE GIA' il turno dell'utente: passarla intera
    # e ripetere il messaggio lo manderebbe due volte.
    assert kwargs["user_message"] == "ciao"
    assert kwargs["conversation_history"] == []
    # "auto" e' l'UNICO valore che fa girare il ciclo di ripiego del router.
    assert kwargs["model"] == "auto"
    # Il contesto del job non porta `thinking_budget`: inventarne uno
    # applicherebbe al ripiego un'impostazione che il ponte aveva dichiarato
    # inapplicabile.
    assert kwargs["thinking_budget"] == 0
    assert kwargs["system_prompt"] == "p" and kwargs["context_str"] == "c"


@pytest.mark.asyncio
async def test_il_ripiego_non_duplica_il_turno_dell_utente(tmp_path):
    """Il messaggio e' gia' in cronologia da prima dell'accodamento
    (`_enqueue_chat_job` lo scrive PRIMA di accodare)."""
    app, q, runner, _, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    append_messages([{"role": "user", "content": "ciao"}], data_dir)
    jid = _accoda_scaduto(q)
    async with TestClient(TestServer(app)) as client:
        await client.get("/api/chat/reply/" + jid)
    assert [m["role"] for m in load_history(data_dir)] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_due_poll_concorrenti_ripiegano_una_volta_sola(tmp_path):
    """Il browser ne fa uno ogni 3,5 s, e due schede aperte sulla stessa
    conversazione ne fanno due. Il reclamo e' atomico: il secondo trova lo
    stato 'ripiego' e continua ad aspettare."""
    import asyncio

    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    jid = _accoda_scaduto(q)
    async with TestClient(TestServer(app)) as client:
        await asyncio.gather(client.get("/api/chat/reply/" + jid),
                             client.get("/api/chat/reply/" + jid))
    assert runner.chat.await_count == 1


@pytest.mark.asyncio
async def test_un_job_non_ancora_scaduto_continua_ad_aspettare_il_piano(tmp_path):
    """La prova gemella: il ripiego non e' una scorciatoia che accorcia
    l'attesa. Finche' la scadenza non e' passata, il piano ha la sua
    occasione."""
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    ora = time.time()
    jid = q.enqueue("chat", {}, {}, ora + 300, now=ora)
    async with TestClient(TestServer(app)) as client:
        body = await (await client.get("/api/chat/reply/" + jid)).json()
    assert body == {"status": "pending"}
    runner.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_senza_nessun_provider_in_catena_il_ripiego_lo_dice_invece_di_tacere(tmp_path):
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    app["llm_router"] = None
    app["claude_runner"] = None
    jid = _accoda_scaduto(q)
    async with TestClient(TestServer(app)) as client:
        body = await (await client.get("/api/chat/reply/" + jid)).json()
    assert body["status"] == "error"
    assert "nessun altro provider in catena" in body["message"]
    # E il job e' chiuso: lasciarlo in 'ripiego' farebbe ritentare ogni poll.
    assert q.get(jid)["status"] == "decided"


@pytest.mark.asyncio
async def test_il_ripiego_a_valle_si_annuncia_e_la_nota_resta_sul_job(tmp_path):
    """La nota vive nel JOB, non nella richiesta che per caso lo ha raccolto:
    un poll successivo, o un ricaricamento della pagina, la ritrova
    invariata. Esattamente come `tools_called`, e per lo stesso motivo."""
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    _con_registro(app, catena=["claude", "openrouter"], chi_ha_risposto="openrouter")
    jid = _accoda_scaduto(q)
    async with TestClient(TestServer(app)) as client:
        primo = await (await client.get("/api/chat/reply/" + jid)).json()
        secondo = await (await client.get("/api/chat/reply/" + jid)).json()
    atteso = ("Il Piano Claude Max non ha risposto in tempo: ha risposto "
              "OpenRouter, a consumo.")
    assert primo == {"status": "done", "reply": "sync reply", "nota": atteso}
    assert secondo["nota"] == atteso


@pytest.mark.asyncio
async def test_la_nota_non_finisce_in_cronologia(tmp_path):
    """Una nota persistita diventa contesto che il modello rilegge al turno
    dopo, e su cui ragiona. E' la stessa famiglia del difetto dichiarato su
    «Errore temporaneo del servizio AI», che in cronologia ci finisce e non
    dovrebbe."""
    app, q, runner, _, data_dir = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    _con_registro(app, catena=["openrouter"], chi_ha_risposto="openrouter")
    append_messages([{"role": "user", "content": "ciao"}], data_dir)
    jid = _accoda_scaduto(q)
    async with TestClient(TestServer(app)) as client:
        body = await (await client.get("/api/chat/reply/" + jid)).json()
    assert body["nota"]
    for m in load_history(data_dir):
        assert "Piano Claude Max" not in m["content"]


@pytest.mark.asyncio
async def test_la_scadenza_del_piano_finisce_nel_registro_degli_esiti(tmp_path):
    """Il registro, per il piano, era VUOTO PER COSTRUZIONE: il ponte non passa
    dal router, quindi nessuno registrava mai un esito per `subscription` e la
    sua riga nella pagina Modelli diceva per sempre «non l'hai ancora usato».
    Questo e' l'unico punto del prodotto in cui si osserva qualcosa sul piano.

    E la famiglia e' `scaduto`, non il ramo di scorta: quello direbbe «ha
    rifiutato», che e' piu' largo del fatto -- il piano non ha rifiutato, non
    ha risposto."""
    from hiris.app.decisione_modelli import frase_esito

    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    registro = _con_registro(app, catena=["openrouter"], chi_ha_risposto="openrouter")
    ora = time.time()
    jid = _accoda_scaduto(q, ora=ora)
    async with TestClient(TestServer(app)) as client:
        await client.get("/api/chat/reply/" + jid)

    esito = registro.esito("subscription")
    assert esito["tipo"] == "rifiutato" and esito["famiglia"] == "scaduto"
    assert esito["codice"] is None
    # `durata_s` e' quanto il piano ha AVUTO, misurato sul job (nato 300 s
    # prima della scadenza), non riletto dall'archivio -- che l'utente puo'
    # aver cambiato mentre il turno era in volo.
    assert 298 < esito["durata_s"] < 302, esito["durata_s"]
    frase = frase_esito(esito, posizione=1, adesso=esito["quando"] + 120)
    assert frase == "non ha risposto in tempo — l'ultima richiesta, 2 min fa"
    assert "rifiutato" not in frase


@pytest.mark.asyncio
async def test_mentre_ripiega_la_conversazione_e_occupata(tmp_path):
    """Un ripiego in corso e' un turno in corso: la chiamata al modello puo'
    durare decine di secondi, e lasciar partire un secondo turno intanto
    significherebbe due risposte in volo sulla stessa conversazione. Lo stato
    'ripiego' conta come in volo SENZA il filtro sulla scadenza -- che per lui
    sarebbe sempre passata."""
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    jid = _accoda_scaduto(q)
    assert q.has_pending_chat() is False, "scaduto e non ancora reclamato: libera"
    assert q.reclama_scaduto(jid, time.time()) is not None
    assert q.has_pending_chat() is True

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "seconda"})
        assert resp.status == 409
    runner.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_un_ripiego_in_corso_si_aspetta_e_non_si_ritenta(tmp_path):
    """Lo stato 'ripiego' non e' terminale e non e' un errore: si aspetta come
    si aspettava il piano. Se il poll lo trattasse come `expired`, l'utente
    leggerebbe «La risposta non e' arrivata in tempo» mentre la catena sta
    ancora scrivendo la sua risposta."""
    app, q, runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    jid = _accoda_scaduto(q)
    q.reclama_scaduto(jid, time.time())
    async with TestClient(TestServer(app)) as client:
        body = await (await client.get("/api/chat/reply/" + jid)).json()
    assert body == {"status": "pending"}
    runner.chat.assert_not_awaited()
