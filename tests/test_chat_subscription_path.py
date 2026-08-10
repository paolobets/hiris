"""Slice 4b Task 2: async subscription path for handle_chat.

When ``app["chat_via_subscription"]`` is truthy AND the reasoning-queue
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


def _make_app(tmp_path, *, chat_via_subscription=False, with_queue=True, runner=None,
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
    app["chat_via_subscription"] = chat_via_subscription

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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    #   - i quattro strumenti (STRUMENTI_CONOSCENZA/dispatcher) e `debug`
    #     (tools_called/thinking_blocks): la fetta A non da' strumenti al
    #     ponte (regole-fetta.md), sono della fetta B.
    # Questo e' il test che impedisce a un task futuro di aggiungerne meta'
    # in silenzio, e quello che dice a chi verra' dopo dove guardare.
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


@pytest.mark.asyncio
async def test_flag_off_uses_sync_path_even_with_bridge_on(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=False, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


# ---------------------------------------------------------------------------
# Final-review Fix 1: max_chat_turns must be enforced BEFORE the subscription
# branch, not just on the sync path. Before the fix, an agent with a session
# turn limit chatted indefinitely once chat_via_subscription was on, because
# the check sat after the subscription branch's early return (unreachable in
# that mode).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_turns_reached_blocks_subscription_path(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "salva questo"})
        assert resp.status == 202

    history = load_history(data_dir)
    assert history == [{"role": "user", "content": "salva questo"}]


@pytest.mark.asyncio
async def test_job_context_history_includes_current_user_turn(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "prima domanda"})
        body = await resp.json()

    job = q.get(body["job_id"])
    history = job["context"]["history"]
    assert history[-1] == {"role": "user", "content": "prima domanda"}
    # No leading assistant turn (Claude API would reject it).
    assert history[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Poll route
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_route_pending_then_done(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
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

def test_chat_via_subscription_wiring_requires_bridge_enabled_in_source():
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'app["chat_via_subscription"] =' in src
    # The assigned expression must combine the CHAT_VIA_SUBSCRIPTION config
    # read with a BRIDGE_ENABLED check -- not the config flag alone.
    assign_pos = src.index('app["chat_via_subscription"] =')
    tail = src[assign_pos:assign_pos + 400]
    assert "CHAT_VIA_SUBSCRIPTION" in tail or "_chat_via_subscription_cfg" in tail
    assert "_bridge_enabled" in tail or "BRIDGE_ENABLED" in tail


def test_chat_via_subscription_env_var_read_same_convention_as_bridge_enabled():
    """CHAT_VIA_SUBSCRIPTION must be parsed with the exact same truthy-string
    convention used everywhere else in this module for boolean env vars
    (BRIDGE_ENABLED, BRAIN_NOTIFY_HIGH, ...) --
    '1'/'true'/'yes'/'on' -- so ops behavior is consistent across knobs.

    SP-2 tech-debt: the idiom is now unified behind env_util.env_bool (still
    the same '1'/'true'/'yes'/'on' truthy set), so this pins the call to the
    shared helper instead of a hand-rolled `.strip().lower() in (...)`."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'env_bool("CHAT_VIA_SUBSCRIPTION")' in src


@pytest.mark.parametrize("cfg,bridge,expected", [
    (True, True, True),
    (True, False, False),
    (False, True, False),
    (False, False, False),
])
def test_chat_via_subscription_gate_truth_table(cfg, bridge, expected):
    """Final-review Fix 2: exercises the REAL gate combinator
    (``server._chat_subscription_active``), not a hand-copied truth table --
    so an ``and`` -> ``or`` regression in the actual function fails this
    test. Config flag alone must NEVER activate the async path when the
    bridge (BRIDGE_ENABLED) is off, and vice versa."""
    from hiris.app.server import _chat_subscription_active

    assert _chat_subscription_active(cfg, bridge) is expected


def test_on_startup_wires_chat_via_subscription_through_the_real_gate_function():
    """Complements the truth-table test above: pins that _on_startup's
    wiring point actually CALLS _chat_subscription_active rather than
    reimplementing the boolean logic inline (where an ``and``->``or``
    regression would be invisible to the truth-table test, which only
    exercises the extracted function directly)."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assign_pos = src.index('app["chat_via_subscription"] =')
    line_end = src.index("\n", assign_pos)
    assert "_chat_subscription_active(" in src[assign_pos:line_end]


# ---------------------------------------------------------------------------
# SP-2 Task 3: provider_subscription first-class -- must derive BOTH cfg and
# bridge, preserving the cfg AND bridge fail-safe (never weakened to an OR).
# ---------------------------------------------------------------------------

from hiris.app.server import _chat_subscription_active


def test_subscription_first_class_implies_bridge():
    # provider_subscription attivo => cfg e bridge entrambi True => attivo
    assert _chat_subscription_active(True, True) is True


def test_subscription_without_bridge_still_fails_closed():
    # invariante preservata: manca il bridge => NON attivo (fail-safe #1)
    assert _chat_subscription_active(True, False) is False


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
        tmp_path, chat_via_subscription=True, with_queue=True)

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
