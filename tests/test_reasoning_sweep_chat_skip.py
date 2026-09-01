"""Slice 4b Task 2, Fix 1: the ponte-push sweep (server.py's
``_reasoning_sweep``, scheduled as ``hiris_reasoning_sweep``) must not treat
an expired ``kind="chat"`` job as anything else -- it stays 'expired' for its
own caller (the chat poll route) to surface.

fetta E3 Task 4: the holistic branch that used to reason locally over an
expired ``kind="holistic"`` job (the ponte-push fallback, via ``_run_decision``)
is GONE -- it left with ``_holistic_reason``, the only producer of
``kind="holistic"`` jobs. No such job is ever enqueued anymore. If one is
swept anyway (only possible from a ``reasoning.db`` left by a pre-upgrade
install), the sweep must NOT silently drop it: it logs an explicit warning
naming the job and its stale kind, then lets it expire -- same as it always
did for chat, just declared instead of silent. This file used to pin "an
expired holistic job is still reasoned over"; that behavior no longer exists
in the product, so the test adapts to what replaced it rather than being
deleted outright -- the subject (the sweep's per-kind branching) survives,
only its outcome for non-chat kinds changed.

``_reasoning_sweep`` is a closure defined inside ``server._on_startup`` (same
reason test_reasoning_wiring.py mirrors ``_execute_decision``'s verdict logic
rather than instantiating the whole app -- full startup wires Supervisor/
MQTT/etc and every existing fixture calls ``app.on_startup.clear()`` before
use). Rather than hand-maintaining a mirror copy that could silently drift
from the shipped code, this test extracts the REAL function source via
``inspect.getsource`` and executes it against a test double for its one
remaining free variable of interest (``reasoning_queue``) -- everything else
it references (``_time``, ``logger``, ``app``) is either a plain importable
symbol in server.py or a simple closure value supplied directly, not
per-instance state, so binding them is exact, not a guess.

Dalla 2.4.0 la spazzata passava dal combinatore condiviso con l'instradamento
(``_ponte_attivo``), e il namespace glielo forniva insieme a ``env_bool`` e
``_sub_first_class``. Dalla VERSIONE B (3.0.0) non deriva piu' niente: LEGGE
``app["ponte_attivo"]``, che ``_ricalcola_catena`` ha gia' scritto -- una
lettura sola invece di due derivazioni. I tre simboli sono usciti dal
namespace, e uscirne e' la difesa: rimettere una derivazione dentro la
spazzata farebbe fallire l'exec con un NameError, invece di lasciarla passare
su un valore di comodo.
"""
import inspect
import logging
import textwrap
import time as _time

import pytest

from hiris.app import server
from hiris.app.reasoning.queue import ReasoningQueue


def _load_real_reasoning_sweep(reasoning_queue, *, ponte_attivo=True,
                               scadenza_min=None):
    src = inspect.getsource(server._on_startup)
    start = src.index("    async def _reasoning_sweep() -> None:")
    end_marker = "reasoning_queue.prune(_time.time() - 7 * 86400)"
    end = src.index(end_marker, start) + len(end_marker)
    func_src = textwrap.dedent(src[start:end])

    # VERSIONE B (3.0.0): il namespace ha perso TRE simboli -- `env_bool`,
    # `_sub_first_class` e `_ponte_attivo` -- e ne ha guadagnato una chiave.
    # La spazzata non deriva piu' niente: LEGGE `app["ponte_attivo"]`, che
    # `_ricalcola_catena` ha gia' scritto. Toglierli invece di lasciarli per
    # sicurezza e' deliberato ed e' la virtu' di questo file: se qualcuno
    # rimettesse una derivazione dentro la spazzata, l'exec fallirebbe con un
    # NameError rumoroso invece di passare su un valore di comodo.
    namespace = {
        "_time": _time,
        "logger": logging.getLogger("test_reasoning_sweep_chat_skip"),
        "reasoning_queue": reasoning_queue,
        # Task 14: la spazzata legge anche `app["models_config"]`, per sapere
        # dopo quanto un ripiego preso in carico e mai finito e' uno schianto.
        # Il confine e' il DOPPIO della scadenza, perche' il ripiego COMINCIA
        # alla scadenza: il margine e' il tempo che la catena ha per
        # rispondere. `app` e' un dizionario perche' e' cosi' che la spazzata
        # lo usa (`app.get(...)`), non perche' sia comodo.
        "app": ({"ponte_attivo": ponte_attivo} if scadenza_min is None else {
            "ponte_attivo": ponte_attivo,
            "models_config": {"ponte": {"scadenza_min": scadenza_min}},
        }),
    }
    exec(compile(func_src, "<_reasoning_sweep extracted from server.py>", "exec"), namespace)
    return namespace["_reasoning_sweep"]


@pytest.mark.asyncio
async def test_expired_chat_job_left_expired_without_warning(tmp_path, monkeypatch, caplog):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue(
        "chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
        now - 10, job_id="chat-job", now=now - 100,
    )

    sweep = _load_real_reasoning_sweep(q)
    with caplog.at_level("WARNING"):
        await sweep()

    job = q.get("chat-job")
    assert job["status"] == "expired"
    assert not caplog.records, "chat jobs must never trigger the orphan-kind warning"
    q.close()


@pytest.mark.asyncio
async def test_expired_holistic_job_is_logged_and_left_expired(tmp_path, monkeypatch, caplog):
    """fetta E3 Task 4: a stray kind="holistic" job (only possible from a
    pre-upgrade reasoning.db -- nothing in the product enqueues this kind
    anymore, `_holistic_reason` is gone) is no longer reasoned locally: it
    is declared via an explicit warning and left to expire, never silently
    dropped."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue(
        "holistic",
        {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
        {"snapshot": {"foo": "bar"}},
        now - 10, job_id="holistic-job", now=now - 100,
    )

    sweep = _load_real_reasoning_sweep(q)
    with caplog.at_level("WARNING"):
        await sweep()

    job = q.get("holistic-job")
    assert job["status"] == "expired"
    assert any("holistic-job" in rec.message for rec in caplog.records)
    q.close()


@pytest.mark.asyncio
async def test_mixed_sweep_only_non_chat_kind_logged(tmp_path, monkeypatch, caplog):
    """Both kinds expire in the same sweep pass: only the non-chat one is
    logged as orphaned; the chat one is simply left in 'expired' state
    (surfaced to the user via the poll route, Fix 2), silently."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
              now - 10, job_id="chat-job", now=now - 100)
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
              {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)

    sweep = _load_real_reasoning_sweep(q)
    with caplog.at_level("WARNING"):
        await sweep()

    assert q.get("chat-job")["status"] == "expired"
    assert q.get("holistic-job")["status"] == "expired"
    messages = [rec.message for rec in caplog.records]
    assert any("holistic-job" in m for m in messages)
    assert not any("chat-job" in m for m in messages)
    q.close()


@pytest.mark.asyncio
async def test_sweep_no_op_when_bridge_and_subscription_both_off(tmp_path, monkeypatch):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
              {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)

    sweep = _load_real_reasoning_sweep(q, ponte_attivo=False)
    await sweep()

    # Early return before sweep_expired: the job is untouched (still 'pending').
    assert q.get("holistic-job")["status"] == "pending"
    q.close()


# ---------------------------------------------------------------------------
# Task 14: lo sweep non ruba il lavoro al poll, e raccoglie i ripieghi
# schiantati.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lo_sweep_non_tocca_un_ripiego_in_corso(tmp_path, monkeypatch):
    """La convivenza fra sweep e poll. Il ripiego vive nella rotta di poll
    (ogni 3,5 s), lo sweep gira ogni 2 minuti: se lo sweep marcasse 'expired'
    un job in 'ripiego', l'utente leggerebbe «La risposta non e' arrivata in
    tempo. Riprova.» mentre la catena sta scrivendo la sua risposta -- e quella
    risposta, gia' pagata, finirebbe in un job che nessuno guarda piu'.

    Non e' una guardia scritta apposta: la `WHERE status IN
    ('pending','claimed')` di `sweep_expired` esclude 'ripiego' da sola. E'
    proprio questa la ragione per cui e' sicura, ed e' per questo che si
    verifica invece di assumerla."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("chat", {}, {"history": []}, now - 10, job_id="chat-job", now=now - 100)
    assert q.reclaim_expired("chat-job", now) is not None

    sweep = _load_real_reasoning_sweep(q, scadenza_min=5)
    await sweep()

    assert q.get("chat-job")["status"] == "ripiego"
    q.close()


@pytest.mark.asyncio
async def test_lo_sweep_raccoglie_i_ripieghi_schiantati(tmp_path, monkeypatch):
    """Un ripiego che non finisce mai -- processo caduto a meta' chiamata --
    non puo' restare in volo per sempre: `prune` cancella 'decided', 'expired'
    e 'failed', mai 'ripiego', e finche' resta li' tiene anche la
    conversazione bloccata sul 409.

    L'orologio non avanza da solo: si finge un ripiego reclamato molto tempo
    fa (oltre il doppio della scadenza) invece di aspettare, che e' l'unico
    modo di provare un confine."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    # Scadenza 5 minuti -> il confine e' 10 minuti fa. Questo ripiego e' stato
    # reclamato 11 minuti fa: e' uno schianto.
    q.enqueue("chat", {}, {"history": []}, now - 11 * 60, job_id="vecchio",
              now=now - 16 * 60)
    q.reclaim_expired("vecchio", now - 11 * 60)
    # E questo un minuto fa: sta ancora lavorando, e non si tocca.
    q.enqueue("chat", {}, {"history": []}, now - 60, job_id="fresco", now=now - 6 * 60)
    q.reclaim_expired("fresco", now - 60)

    sweep = _load_real_reasoning_sweep(q, scadenza_min=5)
    await sweep()

    assert q.get("vecchio")["status"] == "failed"
    assert q.get("vecchio")["context"] == {}
    assert q.get("fresco")["status"] == "ripiego", (
        "il confine e' il DOPPIO della scadenza: un ripiego cominciato un "
        "minuto fa non e' uno schianto")
    q.close()


@pytest.mark.asyncio
async def test_il_confine_dello_schianto_viene_dalla_scadenza_configurata(tmp_path, monkeypatch):
    """La prova gemella della precedente, sul NUMERO: il confine non e' un
    dieci scritto a mano, e' il doppio di `ponte.scadenza_min` -- lo stesso
    valore che `_enqueue_chat_job` usa per scrivere la scadenza. Con una
    scadenza lunga il margine cresce con lei, altrimenti un ripiego legittimo
    verrebbe ucciso mentre lavora."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("chat", {}, {"history": []}, now - 11 * 60, job_id="j", now=now - 71 * 60)
    q.reclaim_expired("j", now - 11 * 60)

    # Scadenza 60 minuti -> confine a 120 minuti fa: undici minuti non bastano.
    await _load_real_reasoning_sweep(q, scadenza_min=60)()
    assert q.get("j")["status"] == "ripiego"

    # Scadenza 5 minuti -> confine a 10 minuti fa: undici bastano.
    await _load_real_reasoning_sweep(q, scadenza_min=5)()
    assert q.get("j")["status"] == "failed"
    q.close()
