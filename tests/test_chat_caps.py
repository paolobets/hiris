"""Slice 4b Task 3: separate chat daily cap + one-in-flight-per-conversation
guard, applied ONLY to the async subscription path (Task 2's
``_enqueue_chat_job`` branch of ``handle_chat``). The sync path (flag off) is
untouched.

Real APIs verified before writing this test (matches Task 2's report /
tests/test_chat_subscription_path.py):
- handle_chat gates on app["ponte_attivo"] AND app["reasoning_queue"]
  present (``_bridge_on``) before taking the async branch.
- ReasoningQueue.enqueue(kind, wake, context, deadline_ts, *, job_id=None, now)
  stores context as JSON; the chat job context carries "chatbot_id" (NOT
  "conversation_id" -- chat_store has no separate conversation_id concept,
  confirmed in Task 1/2).
- ReasoningQueue.submit(job_id, nonce, decision, now) -> bool resolves a job
  (status -> 'decided'), the only way to make a previously-enqueued chat job
  stop counting as "in flight" (pending/claimed).

New in this task:
- ReasoningQueue.has_pending_chat() -> bool: a kind="chat" job in
  pending/claimed state. fetta E4 Task 5 ("un bot solo") dropped the
  `chatbot_id` parameter this originally took (a conversation used to be a
  chatbot's active session, keyed by chatbot_id; with one bot there's one
  conversation, so "in flight for this id" and "in flight" collapsed into
  the same question) -- its unit tests moved to test_reasoning_queue.py,
  the queue class's natural home. What stays here are the HTTP-level 409
  integration tests below (handle_chat's use of the guard), unaffected by
  the signature change.
- ReasoningQueue.count_chat_today(now=None) -> int: kind="chat" jobs whose
  created_ts falls on the same local calendar day as `now` (defaults to
  time.time()). Takes an explicit `now` -- like every other method on this
  class (enqueue/claim/submit/sweep_expired) -- so tests don't depend on wall
  clock.
"""
import os
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock

from hiris.app.api.handlers_chat import handle_chat
from hiris.app.chat_store import close_all_stores
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
    turno viene accodato e muore: e' un RIPIEGO, il turno scende alla catena ed
    esce 200. Un'app di prova col ponte acceso e senza token non descrive piu'
    il ponte -- descrive il ripiego -- e ogni test di questo file che parla di
    202/409 sarebbe diventato un test su un'altra cosa, verde per la ragione
    sbagliata. Il token si mette qui, una volta: e' la condizione in cui il
    ponte esiste davvero. I test che vogliono il ripiego lo tolgono a mano
    (`monkeypatch.delenv`), e si leggono per quello che sono."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")


# fetta E4 Task 4 ("un bot solo"): non c'e' piu' un `Chatbot` per id da
# mockare -- `_make_agent`/l'`engine` MagicMock sono sostituiti da
# un'`ImpostazioniChat` vera (nessuna selezione da simulare: e' l'unica
# istanza, sempre quella). Il `chatbot_id`/`agent_id` che i test mandano nel
# body resta nel payload delle richieste sotto (per continuare a coprire "un
# id qualsiasi non rompe nulla"), ma non seleziona piu' niente. fetta E4
# Task 5: nemmeno una chiave interna fissa resta -- chat_store e la coda non
# hanno proprio piu' un concetto di id (vedi handlers_chat.py).
def _make_impostazioni(*, max_chat_turns=0):
    return ImpostazioniChat(
        nome="test-agent",
        system_prompt="You are a helpful assistant.",
        max_chat_turns=max_chat_turns,
    )


def _make_app(tmp_path, *, ponte_attivo=True, with_queue=True,
              tetto_giornaliero=None, runner=None, max_chat_turns=0):
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
    # Task 14: il tetto giornaliero del ponte si legge dall'ARCHIVIO
    # (`ponte.tetto_giornaliero`), dove l'utente lo cambia dalla pagina
    # Modelli, e non piu' da `app["chat_daily_cap"]` -- una copia di
    # `CHAT_DAILY_CAP` presa all'avvio, che nessun salvataggio aggiornava.
    if tetto_giornaliero is not None:
        app["models_config"] = {"ponte": {"tetto_giornaliero": tetto_giornaliero}}

    q = None
    if with_queue:
        q = ReasoningQueue(str(tmp_path / "reasoning.db"))
        app["reasoning_queue"] = q

    app.router.add_post("/api/chat", handle_chat)
    return app, q, runner, impostazioni, data_dir


# ---------------------------------------------------------------------------
# ReasoningQueue.has_pending_chat: le unit test dirette sulla coda si sono
# spostate in test_reasoning_queue.py (fetta E4 Task 5, "un bot solo" --
# senza piu' un chatbot_id da passare, la loro casa naturale e' li' insieme
# alle altre unit test di ReasoningQueue). Qui restano solo le integration
# test HTTP piu' sotto (handle_chat che usa la guardia 409).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ReasoningQueue.count_chat_today
# ---------------------------------------------------------------------------

def test_count_chat_today_zero_when_no_jobs(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    assert q.count_chat_today(now=1_700_000_000.0) == 0


def test_count_chat_today_counts_jobs_created_same_day(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0  # arbitrary anchor timestamp
    q.enqueue("chat", {}, {"chatbot_id": "a1"}, deadline_ts=base + 300, now=base)
    q.enqueue("chat", {}, {"chatbot_id": "a2"}, deadline_ts=base + 300, now=base + 60)
    assert q.count_chat_today(now=base + 120) == 2


def test_count_chat_today_excludes_other_days(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0
    yesterday = base - 86400
    q.enqueue("chat", {}, {"chatbot_id": "a1"}, deadline_ts=yesterday + 300, now=yesterday)
    q.enqueue("chat", {}, {"chatbot_id": "a2"}, deadline_ts=base + 300, now=base)
    assert q.count_chat_today(now=base) == 1


def test_count_chat_today_excludes_non_chat_kinds(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
              "severity_hint": "info", "evidence": {}, "ts": base},
              {}, deadline_ts=base + 300, now=base)
    assert q.count_chat_today(now=base) == 0


def test_count_chat_today_counts_regardless_of_status(tmp_path):
    """The cap is about how many chat turns were enqueued today, not how many
    are still in flight -- a resolved/expired job still consumed the cap."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0
    q.enqueue("chat", {}, {"chatbot_id": "a1"}, deadline_ts=base + 300, now=base)
    claimed = q.claim(now=base + 1)
    q.submit(claimed["job_id"], claimed["nonce"], {"reply": "x"}, now=base + 2)
    q.enqueue("chat", {}, {"chatbot_id": "a2"}, deadline_ts=base + 300, now=base + 3)
    q.sweep_expired(now=base + 10_000_000)  # would expire a2 if far enough, unrelated to count
    assert q.count_chat_today(now=base) == 2


# ---------------------------------------------------------------------------
# handle_chat guards -- subscription path ONLY
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_enqueue_same_conversation_returns_409(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima"})
        assert first.status == 202

        second = await client.post("/api/chat", json={"message": "seconda"})
        assert second.status == 409
        body = await second.json()
        assert body == {"error": "C'è già una risposta in arrivo per questa conversazione."}


# fetta E4 Task 4 ("un bot solo"): test_409_guard_scoped_per_conversation_not_
# global pinnava una scoping PER CHATBOT che non esiste piu' -- un
# `chatbot_id` diverso nel body non produce piu' una conversazione diversa
# (vedi handlers_chat.py: l'id inviato dal client e' accettato e ignorato,
# la chiave effettiva e' sempre `ID_CHAT_DEFAULT`). Con un bot solo la guardia
# 409 e' necessariamente globale, non piu' "per conversazione" -- e' esattamente
# quello che la riscritta sotto verifica: un secondo `chatbot_id`, anche
# distinto, finisce comunque nella STESSA corsia e prende 409. Il vecchio
# corpo del test non e' nemmeno piu' eseguibile cosi' com'era (mockava
# `app["engine"].get_chatbot.side_effect` -- `_make_app` non valorizza piu'
# quella chiave: `KeyError: 'engine'` al primo accesso, prima ancora di
# arrivare all'assert); la riscritta sotto e' stata verificata girando
# davvero contro il codice nuovo (vedi il comando nel report).
@pytest.mark.asyncio
async def test_409_guard_e_ora_globale_un_chatbot_id_diverso_non_lo_evita(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima", "chatbot_id": "a"})
        assert first.status == 202

        other = await client.post("/api/chat", json={"message": "altro id", "chatbot_id": "b"})
        assert other.status == 409


@pytest.mark.asyncio
async def test_409_guard_clears_once_first_job_resolved(tmp_path):
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima"})
        job_id = (await first.json())["job_id"]

        claimed = q.claim(now=time.time())
        q.submit(job_id, claimed["nonce"], {"reply": "ok"}, now=time.time())

        second = await client.post("/api/chat", json={"message": "seconda"})
        assert second.status == 202


@pytest.mark.asyncio
async def test_col_tetto_pieno_il_turno_scende_alla_catena_invece_di_dare_429(tmp_path):
    """Il 429 ESCE, e con lui la sua stringa.

    Fino alla 2.4.1 il tetto pieno finiva il turno con «Limite giornaliero di
    messaggi chat raggiunto»: il messaggio era perso e la catena -- che poteva
    rispondere benissimo -- non veniva consultata. E' uno dei due casi che
    sono, alla lettera, «il piano non e' disponibile». Adesso il turno scende
    al provider successivo, sincrono, 200.

    Il prezzo si annuncia: la risposta porta una `nota` che dichiara il ripiego
    (i test della nota stanno in test_chat_subscription_path.py). Senza quella
    riga questo cambio sarebbe un prelievo silenzioso -- dal forfait al
    consumo, senza che nessuno lo abbia chiesto."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, tetto_giornaliero=1)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima"})
        assert first.status == 202
        job_id = (await first.json())["job_id"]

        # Si risolve il primo job: altrimenti la guardia «una risposta per
        # volta» risponderebbe 409 e il tetto non si vedrebbe.
        claimed = q.claim(now=time.time())
        q.submit(job_id, claimed["nonce"], {"reply": "ok"}, now=time.time())

        second = await client.post("/api/chat", json={"message": "seconda"})
        assert second.status == 200
        assert (await second.json())["response"] == "sync reply"
    runner.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_cap_default_is_generous_enough_for_normal_use(tmp_path):
    # Nessun `ponte.tetto_giornaliero` nell'archivio -> il lettore deve
    # ricadere su un predefinito sensato (50), non su 0/None -- che
    # ripiegherebbe sulla catena a ogni turno, cioe' spegnerebbe il ponte in
    # silenzio.
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, tetto_giornaliero=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202


@pytest.mark.asyncio
async def test_flag_off_guards_do_not_apply_sync_path_unchanged(tmp_path):
    """Con il ponte SPENTO, handle_chat deve usare il percorso sincrono
    regardless of pending jobs or the daily cap -- guards are subscription-only."""
    app, q, runner, impostazioni, data_dir = _make_app(
        tmp_path, ponte_attivo=False, tetto_giornaliero=0)
    # Pre-seed a "pending" chat job on the queue -- fetta E4 Task 5:
    # has_pending_chat() is unconditional now (no id to key it by) -- if the
    # guard wrongly applied to the sync path this would still 409.
    q.enqueue("chat", {}, {}, deadline_ts=time.time() + 300, now=time.time())

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


@pytest.mark.asyncio
async def test_chat_accepts_new_chatbot_id_key(tmp_path):
    """fetta E4 Task 4: il body key "chatbot_id" non seleziona piu' nessun
    Chatbot (l'entita' e' uscita) -- viene accettato e ignorato. Quello che
    resta da verificare e' che mandarlo non rompa nulla: la chat risponde
    comunque sul percorso sincrono."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "chatbot_id": "qualunque-id"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"


@pytest.mark.asyncio
async def test_chat_still_accepts_legacy_agent_id_key(tmp_path):
    """Retro-compat: older clients / Lovelace card configs sending "agent_id"
    must keep working unchanged after the chat-wire rename to "chatbot_id" --
    stesso discorso di sopra, anche questo id non seleziona piu' niente."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, ponte_attivo=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": "qualunque-id"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"


@pytest.mark.asyncio
async def test_sync_path_degrades_gracefully_on_runner_backend_error(tmp_path):
    """Review C/#13: runners now raise RunnerBackendError instead of
    returning a friendly string on an API failure (needed so LLMRouter's
    fallback loop actually engages). handle_chat's sync path must catch it
    at its own call site and still return a normal 200 with the friendly
    message in `response` -- not let it propagate into aiohttp as an
    unhandled exception (which would 500 instead of degrading gracefully,
    a real regression this test guards against)."""
    from hiris.app.claude_runner import RunnerBackendError

    runner = AsyncMock()
    runner.chat = AsyncMock(
        side_effect=RunnerBackendError("Errore temporaneo del servizio AI. Riprova tra poco.")
    )
    runner.last_tool_calls = []
    runner.last_thinking_blocks = []
    app, q, runner, impostazioni, data_dir = _make_app(
        tmp_path, ponte_attivo=False, tetto_giornaliero=0, runner=runner)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "Errore temporaneo del servizio AI. Riprova tra poco."


@pytest.mark.asyncio
async def test_bridge_off_falls_back_to_sync_guards_do_not_apply(tmp_path):
    """ponte_attivo on but bridge not wired (no reasoning_queue) ->
    existing Task 2 fallback to sync path; the new guards must not blow up
    without a queue to query."""
    app, q, runner, impostazioni, data_dir = _make_app(
        tmp_path, ponte_attivo=True, with_queue=False, tetto_giornaliero=0)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"


@pytest.mark.asyncio
async def test_409_takes_precedence_when_both_conditions_true(tmp_path):
    """La guardia «una risposta per volta» viene PRIMA del tetto, e dal Task 14
    la precedenza non e' piu' una questione di quale messaggio sia piu' utile.

    Col tetto pieno il turno adesso RIPIEGA sulla catena, sincrono: se il tetto
    fosse controllato per primo, questo turno partirebbe verso la catena mentre
    il ponte ne ha ancora uno in volo -- e quello, quando arriva, si scrive in
    cronologia da solo (`server._submit_chat_reply`). Due risposte in volo
    sulla stessa conversazione, che e' esattamente cio' che questa guardia
    esiste per impedire: la seconda arriverebbe in una cronologia che la prima
    sta per riscrivere."""
    app, q, runner, impostazioni, data_dir = _make_app(tmp_path, tetto_giornaliero=1)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima"})
        assert first.status == 202
        # Il primo job e' ancora pending E il tetto (1) e' gia' consumato.
        second = await client.post("/api/chat", json={"message": "seconda"})
        assert second.status == 409
    runner.chat.assert_not_awaited()
