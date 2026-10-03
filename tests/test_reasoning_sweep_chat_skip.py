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

Dal 03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'») la
spazzata non si ritaglia piu' dal sorgente di ``_on_startup`` per eseguirla
in un namespace preparato a mano: si avvia l'app davvero
(``fotografia_porte.mounted``) e si fa girare il lavoro
``hiris_reasoning_sweep`` che lo schedulatore ha registrato, sulla coda vera
dell'app (``app["reasoning_queue"]``). Cio' che il namespace di prima
garantiva -- la spazzata LEGGE ``app["bridge_active"]`` invece di derivarlo --
qui si prova cambiando quella chiave e guardando la spazzata obbedire.
"""
import contextlib
import sys
import time as _time
from pathlib import Path

import pytest

from hiris.app import server
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte


@contextlib.asynccontextmanager
async def _started_sweep(tmp_path, *, bridge_active=True, deadline_min=None):
    """La spazzata VERA, sull'app avviata: `(spazzata, coda, app)`.

    `bridge_active` e `deadline_min` si scrivono nelle chiavi che la spazzata
    legge (`app["bridge_active"]`, `app["models_config"]["ponte"]`), come le
    lascerebbero `_recompute_chain` e la pagina Modelli."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        app["bridge_active"] = bridge_active
        if deadline_min is not None:
            config = dict(app.get("models_config") or {})
            config["ponte"] = {**(config.get("ponte") or {}), "scadenza_min": deadline_min}
            app["models_config"] = config
        sweep = app["scheduler"].get_job("hiris_reasoning_sweep").func
        yield sweep, app["reasoning_queue"], app


@pytest.mark.asyncio
async def test_expired_chat_job_left_expired_without_warning(tmp_path, monkeypatch, caplog):
    async with _started_sweep(tmp_path) as (sweep, q, _app):
        now = _time.time()
        q.enqueue(
            "chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
            now - 10, job_id="chat-job", now=now - 100,
        )
        with caplog.at_level("WARNING", logger="hiris"):
            await sweep()

        job = q.get("chat-job")
        assert job["status"] == "expired"
        assert not [r for r in caplog.records if "chat-job" in r.getMessage()], (
            "chat jobs must never trigger the orphan-kind warning")


@pytest.mark.asyncio
async def test_expired_holistic_job_is_logged_and_left_expired(tmp_path, monkeypatch, caplog):
    """fetta E3 Task 4: a stray kind="holistic" job (only possible from a
    pre-upgrade reasoning.db -- nothing in the product enqueues this kind
    anymore, `_holistic_reason` is gone) is no longer reasoned locally: it
    is declared via an explicit warning and left to expire, never silently
    dropped."""
    async with _started_sweep(tmp_path) as (sweep, q, _app):
        now = _time.time()
        q.enqueue(
            "holistic",
            {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
            {"snapshot": {"foo": "bar"}},
            now - 10, job_id="holistic-job", now=now - 100,
        )
        with caplog.at_level("WARNING", logger="hiris"):
            await sweep()

        job = q.get("holistic-job")
        assert job["status"] == "expired"
        assert any("holistic-job" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_mixed_sweep_only_non_chat_kind_logged(tmp_path, monkeypatch, caplog):
    """Both kinds expire in the same sweep pass: only the non-chat one is
    logged as orphaned; the chat one is simply left in 'expired' state
    (surfaced to the user via the poll route, Fix 2), silently."""
    async with _started_sweep(tmp_path) as (sweep, q, _app):
        now = _time.time()
        q.enqueue("chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
                  now - 10, job_id="chat-job", now=now - 100)
        q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
                               "severity_hint": "info"},
                  {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)
        with caplog.at_level("WARNING", logger="hiris"):
            await sweep()

        assert q.get("chat-job")["status"] == "expired"
        assert q.get("holistic-job")["status"] == "expired"
        messages = [rec.getMessage() for rec in caplog.records]
        assert any("holistic-job" in m for m in messages)
        assert not any("chat-job" in m for m in messages)


@pytest.mark.asyncio
async def test_sweep_no_op_when_bridge_and_subscription_both_off(tmp_path, monkeypatch):
    """The sweep READS `app["bridge_active"]` (written by `_recompute_chain`)
    instead of deriving it: switching that key off stops it.

    Mutation EXECUTED: the early return removed from `_reasoning_sweep` --
    red (the job expires)."""
    async with _started_sweep(tmp_path, bridge_active=False) as (sweep, q, _app):
        now = _time.time()
        q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
                               "severity_hint": "info"},
                  {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)
        await sweep()

        # Early return before sweep_expired: the job is untouched (still 'pending').
        assert q.get("holistic-job")["status"] == "pending"


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
    async with _started_sweep(tmp_path, deadline_min=5) as (sweep, q, _app):
        now = _time.time()
        q.enqueue("chat", {}, {"history": []}, now - 10, job_id="chat-job", now=now - 100)
        assert q.reclaim_expired("chat-job", now) is not None
        await sweep()

        assert q.get("chat-job")["status"] == "ripiego"


@pytest.mark.asyncio
async def test_lo_sweep_raccoglie_i_ripieghi_schiantati(tmp_path, monkeypatch):
    """Un ripiego che non finisce mai -- processo caduto a meta' chiamata --
    non puo' restare in volo per sempre: `prune` cancella 'decided', 'expired'
    e 'failed', mai 'ripiego', e finche' resta li' tiene anche la
    conversazione bloccata sul 409.

    L'orologio non avanza da solo: si finge un ripiego reclamato molto tempo
    fa (oltre il doppio della scadenza) invece di aspettare, che e' l'unico
    modo di provare un confine."""
    async with _started_sweep(tmp_path, deadline_min=5) as (sweep, q, _app):
        now = _time.time()
        # Scadenza 5 minuti -> il confine e' 10 minuti fa. Questo ripiego e'
        # stato reclamato 11 minuti fa: e' uno schianto.
        q.enqueue("chat", {}, {"history": []}, now - 11 * 60, job_id="vecchio",
                  now=now - 16 * 60)
        q.reclaim_expired("vecchio", now - 11 * 60)
        # E questo un minuto fa: sta ancora lavorando, e non si tocca.
        q.enqueue("chat", {}, {"history": []}, now - 60, job_id="fresco", now=now - 6 * 60)
        q.reclaim_expired("fresco", now - 60)
        await sweep()

        assert q.get("vecchio")["status"] == "failed"
        assert q.get("vecchio")["context"] == {}
        assert q.get("fresco")["status"] == "ripiego", (
            "il confine e' il DOPPIO della scadenza: un ripiego cominciato un "
            "minuto fa non e' uno schianto")


@pytest.mark.asyncio
async def test_il_confine_dello_schianto_viene_dalla_scadenza_configurata(tmp_path, monkeypatch):
    """La prova gemella della precedente, sul NUMERO: il confine non e' un
    dieci scritto a mano, e' il doppio di `ponte.scadenza_min` -- lo stesso
    valore che `_enqueue_chat_job` usa per scrivere la scadenza. Con una
    scadenza lunga il margine cresce con lei, altrimenti un ripiego legittimo
    verrebbe ucciso mentre lavora."""
    async with _started_sweep(tmp_path, deadline_min=60) as (sweep, q, app):
        now = _time.time()
        q.enqueue("chat", {}, {"history": []}, now - 11 * 60, job_id="j", now=now - 71 * 60)
        q.reclaim_expired("j", now - 11 * 60)

        # Scadenza 60 minuti -> confine a 120 minuti fa: undici minuti non bastano.
        await sweep()
        assert q.get("j")["status"] == "ripiego"

        # Scadenza 5 minuti -> confine a 10 minuti fa: undici bastano. La
        # stessa app, la stessa spazzata: cambia solo cio' che la pagina
        # Modelli scriverebbe.
        app["models_config"] = {**app["models_config"],
                                "ponte": {**app["models_config"]["ponte"], "scadenza_min": 5}}
        await sweep()
        assert q.get("j")["status"] == "failed"


@pytest.mark.asyncio
async def test_un_turno_di_scope_scaduto_lascia_scritto_che_e_scaduto(tmp_path):
    """**Il piano che non risponde MAI deve distinguersi da un'attesa.**

    Senza questo ramo l'ultimo tentativo resta «accodata» per sempre: la
    pagina dell'osservatore dice «in corso da N minuti» mentre nessuna
    risposta arrivera' -- un worker fermo con un token buono diventa
    indistinguibile da un turno che sta ancora pensando. E' il gemello di
    `_close_expired_promise`, ed e' un rilievo della review indipendente
    dell'11/09/2026.

    Mutazione che la uccide: togliere il ramo `SCOPE_TURN_KIND` dalla
    spazzata -- il turno ricade fra i job orfani, che si loggano e basta.
    """
    async with _started_sweep(tmp_path) as (spazzata, coda, app):
        adesso = _time.time()
        coda.enqueue(server.SCOPE_TURN_KIND, {}, {}, deadline_ts=adesso - 1,
                     job_id="S1", now=adesso - 601)

        await spazzata()

        ultimo = app["observations"].recent_attempts()[0]
        assert ultimo["esito"] == "scaduta"
        assert "non ha risposto" in ultimo["dettaglio"]
        assert coda.get("S1")["status"] == "expired"
