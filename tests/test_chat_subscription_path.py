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
from hiris.app.chat_store import close_all_stores, load_history
from hiris.app.impostazioni_chat import ImpostazioniChat
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


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
# LA FUSIONE DEI DUE INTERRUTTORI (2.4.0).
#
# Qui stavano sei test che pinnavano un AND: `_chat_subscription_active(cfg,
# bridge)` doveva essere `and`, mai `or`, perche' era il fail-safe numero uno
# del rilascio -- senza, si poteva instradare la chat in una coda che nessuno
# spazzava. Il proprietario ha fuso `bridge_enabled` e `chat_via_subscription`
# in un interruttore solo (`ponte.attivo`): l'AND non ha piu' due valori da
# combinare, e quei sei test non hanno piu' un soggetto.
#
# Il fail-safe pero' NON e' stato rimosso: e' diventato strutturale. La stessa
# espressione (`server._ponte_attivo`) governa adesso la spazzata E
# l'instradamento, quindi i due non possono divergere -- mentre prima erano
# governati da opzioni diverse e potevano. Quello che segue pinna la nuova
# forma dell'invariante, non la vecchia.
# ---------------------------------------------------------------------------

from hiris.app.server import _ponte_attivo


@pytest.mark.parametrize("interruttore,piano,atteso", [
    (True, False, True),    # l'interruttore da solo basta -- era False con l'AND
    (False, True, True),    # il Piano Claude Max da solo basta -- era False con l'AND
    (True, True, True),
    (False, False, False),  # nessuno dei due: il ponte resta spento
])
def test_il_ponte_e_un_interruttore_solo(interruttore, piano, atteso):
    """Prova per mutazione della fusione.

    Le prime due righe sono quelle che cadono se qualcuno rimette l'AND: con
    `and` darebbero entrambe False. Sono qui apposta, e il commento accanto
    dice cosa valevano prima, cosi' chi legge il fallimento capisce subito che
    ha riportato indietro la coppia di leve invece di aver rotto altro.

    L'ultima riga e' l'invariante che sopravvive alla fusione: senza ne'
    interruttore ne' piano, il ponte NON si accende.
    """
    assert _ponte_attivo(interruttore, piano) is atteso


def test_lo_stesso_gate_governa_la_spazzata_e_l_instradamento():
    """E' cosi' che il fail-safe regge ora che non c'e' piu' un AND.

    Prima l'invariante «non accodare mai in una coda che nessuno spazza» era
    una regola da non sbagliare: due opzioni distinte, combinate a mano nel
    punto giusto. Adesso e' una struttura: `_reasoning_sweep` e il cablaggio di
    `app["ponte_attivo"]` chiamano la STESSA funzione sullo STESSO valore, e
    non possono dire cose diverse. Se qualcuno riscrivesse uno dei due gate a
    mano, l'invariante tornerebbe a dipendere dall'attenzione: questo test lo
    impedisce.
    """
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)

    riga_cablaggio = next(
        r for r in src.splitlines() if 'app["ponte_attivo"] =' in r)
    assert "_ponte_attivo(" in riga_cablaggio, (
        "il cablaggio non passa piu' dal combinatore condiviso: la logica "
        "booleana e' stata riscritta a mano nel punto di assegnazione"
    )

    sweep_pos = src.index("async def _reasoning_sweep()")
    corpo_sweep = src[sweep_pos:sweep_pos + 500]
    assert "_ponte_attivo(" in corpo_sweep, (
        "la spazzata non passa piu' dal combinatore condiviso: puo' tornare a "
        "essere in disaccordo con l'instradamento, ed e' esattamente il buco "
        "che l'AND di prima serviva a chiudere"
    )


def test_il_gate_legge_la_variabile_col_convenzionale_env_bool():
    """La convenzione dei booleani non cambia con la fusione: '1'/'true'/'yes'/
    'on' via `env_util.env_bool`, come ogni altro interruttore del modulo."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'env_bool("BRIDGE_ENABLED")' in src


def test_la_seconda_leva_non_esiste_piu_da_nessuna_parte():
    """L'opzione fusa non deve rientrare dalla porta di servizio.

    Un'opzione vive in cinque posti: bastava che ne resuscitasse uno perche'
    tornasse a esserci una seconda leva da tenere allineata a mano.
    """
    import pathlib as _pl

    import yaml

    base = _pl.Path(__file__).resolve().parents[1] / "hiris"
    cfg = yaml.safe_load((base / "config.yaml").read_text(encoding="utf-8"))
    assert "chat_via_subscription" not in cfg["options"]["ponte"]
    assert "chat_via_subscription" not in cfg["schema"]["ponte"]

    vive = [r for r in (base / "run.sh").read_text(encoding="utf-8").splitlines()
            if not r.lstrip().startswith("#")]
    assert not [r for r in vive if "CHAT_VIA_SUBSCRIPTION" in r]

    for lingua in ("it", "en"):
        testo = (base / "translations" / f"{lingua}.yaml").read_text(encoding="utf-8")
        tradotte = yaml.safe_load(testo)["configuration"]
        assert "chat_via_subscription" not in tradotte["ponte"]

    app_py = (base / "app" / "server.py").read_text(encoding="utf-8").splitlines()
    codice = [r for r in app_py if not r.lstrip().startswith("#")]
    assert not [r for r in codice if 'env_bool("CHAT_VIA_SUBSCRIPTION")' in r]


def test_il_piano_implica_il_ponte_solo_se_lo_hai_acceso_TU():
    """fetta «la catena diventa l'unica verita'»: `_sub_first_class` non viene
    piu' da `derive_active_providers` (interruttore AND credenziale, con la
    regola di compatibilita' che su un'installazione «tutti spenti» lo faceva
    valere `credenziale AND BRIDGE_ENABLED`) ma dall'espressione scritta a
    vista, `credenziale AND PROVIDER_SUBSCRIPTION`.

    Il valore governa `app["ponte_attivo"]`, quindi togliere l'interruttore da
    quell'espressione accenderebbe il ponte a chiunque abbia un token in
    configurazione, senza averlo chiesto -- ed e' l'invariante 5 al contrario.
    La riga vive dentro `_on_startup`, che nessuna fixture esegue: si legge dal
    sorgente vero, come gia' fanno i due test qui sopra."""
    import inspect

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    riga = [r.strip() for r in src.splitlines() if r.strip().startswith("_sub_first_class =")]
    assert len(riga) == 1, riga
    assert 'env_bool("PROVIDER_SUBSCRIPTION")' in riga[0], riga[0]
    assert '_credenziali["subscription"]' in riga[0], riga[0]


def test_il_piano_claude_max_continua_a_implicare_il_ponte():
    """Il comportamento che la fusione NON doveva cambiare: chi sta nella
    configurazione consigliata (Piano Claude Max acceso col suo token) ha il
    ponte acceso senza toccare niente. E' la ragione per cui questa fusione
    costava poco, quindi merita un test suo."""
    assert _ponte_attivo(False, True) is True


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
