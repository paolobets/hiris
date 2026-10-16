"""I lavori periodici, chiesti allo schedulatore dell'app avviata.

Fino al 03/10/2026 queste prove cercavano nel testo di `server.py` l'`id`
di un `add_job` e ritagliavano 400 caratteri intorno per leggerci l'ora: un
lavoro spostato in un altro modulo le rompeva senza che niente cambiasse, e
un `minutes=2` scritto in un commento vicino le teneva verdi (Tappa 1 dello
sprint «Una fonte sola di verita'»). Adesso l'app si avvia davvero
(`tests/_avvio.py`) e si chiede allo schedulatore cosa c'e', quando gira, e
cosa fa.
"""
import pathlib
import sys
from unittest import mock

import pytest

from hiris.app import startup
from hiris.app.proxy.entity_cache import ENTITY_CACHE_KEY
from hiris.app.proxy.ha_client import HA_CLIENT_KEY
from hiris.app.startup import SCHEDULER_KEY
from tests._avvio import scheduled_job, started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

pytestmark = pytest.mark.asyncio(loop_scope="module")


def _job(app, job_id):
    job = app[SCHEDULER_KEY].get_job(job_id)
    assert job is not None, f"il lavoro {job_id} non e' registrato"
    return job


async def test_i_lavori_del_cervello_sono_registrati(started_app):
    """L'aggregazione notturna e la conservazione. Senza il primo il grezzo
    si accumula e nessun oggetto nasce; senza il secondo gli archivi crescono
    per sempre."""
    _job(started_app, "hiris_mind_aggregation")
    _job(started_app, "hiris_retention")


async def test_l_aggregazione_gira_alle_00_20_della_casa(started_app):
    """Aggregare a mezzanotte esatta prenderebbe un giorno ancora aperto: le
    00:20 sono l'ora vera.

    Mutazione ESEGUITA: `hour=0` -> `hour=23` nell'`add_job` -- rossa."""
    assert str(_job(started_app, "hiris_mind_aggregation").trigger) == \
        "cron[hour='0', minute='20']"


async def test_la_potatura_gira_alle_03_00(started_app):
    """Lontana dall'aggregazione apposta: l'una deve finire prima che l'altra
    cominci a leggere il grezzo. Un lavoro solo per tutti gli archivi (Tappa
    8, Task 6): fino all'08/10/2026 erano due, alla stessa ora.

    Mutazione ESEGUITA (08/10/2026): `hour=3` -> `hour=4` nell'`add_job` di
    `hiris_retention` -- rossa."""
    assert str(_job(started_app, "hiris_retention").trigger) == \
        "cron[hour='3', minute='0']"
    assert started_app[SCHEDULER_KEY].get_job("hiris_mind_pruning") is None


async def test_le_condizioni_di_sistema_si_rileggono_ogni_dieci_minuti(started_app):
    """Senza questo lavoro `watch_system_conditions` non ha nessun chiamante
    di produzione, e i guasti non diventano oggetti.

    Mutazione ESEGUITA: il lavoro chiama un'altra funzione -- rossa (nessuna
    chiamata a `watch_system_conditions`)."""
    job = _job(started_app, "hiris_mind_conditions")
    assert str(job.trigger) == "interval[0:10:00]"
    with mock.patch.object(startup, "watch_system_conditions",
                           mock.AsyncMock()) as watched:
        await scheduled_job(started_app, job.id)()
    watched.assert_awaited_once()
    assert watched.await_args.args[0] is started_app


async def test_il_giro_delle_condizioni_tiene_anche_gli_id_delle_statistiche(started_app):
    """Lo stesso lavoro, dopo le condizioni, rinfresca gli id delle statistiche
    che l'osservatore tiene (`hold_watcher_statistic_ids`). Nessuna prova lo
    guardava: la chiamata tolta dal lavoro lasciava la suite verde (misurato
    il 14/10/2026, F8 passo 1b).

    Mutazione ESEGUITA: tolta la chiamata da `startup.conditions_job` --
    rossa."""
    job = _job(started_app, "hiris_mind_conditions")
    with mock.patch.object(startup, "watch_system_conditions", mock.AsyncMock()), \
            mock.patch.object(startup, "hold_watcher_statistic_ids",
                              mock.AsyncMock()) as held:
        await scheduled_job(started_app, job.id)()
    held.assert_awaited_once_with(started_app, started_app[HA_CLIENT_KEY])


async def test_le_tracce_delle_automazioni_si_rileggono_ogni_due_minuti(started_app):
    """Senza questo lavoro le automazioni segnate resterebbero segnate per
    sempre senza che nessuno rileggesse le loro tracce."""
    job = _job(started_app, "hiris_mind_automation_traces")
    assert str(job.trigger) == "interval[0:02:00]"
    with mock.patch.object(startup, "watch_automation_outcomes",
                           mock.AsyncMock()) as watched:
        await scheduled_job(started_app, job.id)()
    watched.assert_awaited_once()


async def test_l_inventario_si_ricarica_ogni_due_minuti(started_app):
    """Un'indisponibilita' passeggera di Home Assistant deve rientrare in
    pochi minuti, non alla prossima notte."""
    job = _job(started_app, "hiris_entity_cache_reload")
    assert str(job.trigger) == "interval[0:02:00]"
    with mock.patch.object(startup, "reload_entity_inventory",
                           mock.AsyncMock()) as reloaded:
        await scheduled_job(started_app, job.id)()
    reloaded.assert_awaited_once()
    assert reloaded.await_args.args[0] is started_app[ENTITY_CACHE_KEY]


async def test_i_lavori_periodici_sono_sedici_come_dichiara_il_readme(started_app):
    """Un lavoro periodico gira per sempre e costa per sempre: aggiungerne uno
    senza accorgersene e' il modo in cui una casa comincia a fare rumore di
    notte. Il numero vive anche nel README, e questa prova esiste perche' non
    divergano (la storia dei sedici: `docs/BACKLOG.md` e il README; il
    diciassettesimo e' il proponente, attori Task 4.2, 06/10/2026; tornano
    sedici l'08/10/2026, quando le due potature delle 03:00 diventano una,
    Tappa 8 Task 6).

    Mutazione ESEGUITA: un `add_job` in piu' in `_on_startup` -- rossa."""
    jobs = started_app[SCHEDULER_KEY].get_jobs()
    assert len(jobs) == 16, sorted(job.id for job in jobs)
    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8")
    assert "registers **sixteen** APScheduler jobs" in readme, (
        "il README non dichiara piu' sedici lavori periodici: il numero "
        "vive in due posti e questa prova esiste perche' non divergano.")


async def test_il_proponente_gira_ogni_ora(started_app):
    """Il proponente (attori, Task 4.2): lo stesso battito
    dell'analista, col giro che vive in `mind/proposer_round.py`, passando
    dall'interruttore (`proposer_beat`)."""
    from hiris.app.mind.proposer_round import proposer_beat

    job = _job(started_app, "hiris_mind_proposer")
    assert str(job.trigger) == "interval[1:00:00]"
    assert job.func is proposer_beat
    assert job.args == (started_app,)


async def test_il_proponente_e_spento_nella_3_78_0(started_app, monkeypatch):
    """Il proprietario, 12/10/2026: la 3.78.0 esce col proponente «Fermo»; si
    accende dopo la misura dal vivo dello strato 3. Il battito dello
    schedulatore non arriva al giro: nessuna domanda al modello, nessun
    turno in coda.

    Gli avvisi delle proposte `alto` partono lo stesso (N141-1): il
    «Rifalla» resta acceso e puo' farne nascere una.

    Mutazioni ESEGUITE: `ENABLED = True` -- rossa (il giro viene chiamato);
    tolto l'avviso dal ramo spento -- rossa (nessun avviso tentato)."""
    from hiris.app.mind import proposer_round as modulo

    chiamate, avvisi = [], []

    async def giro(app):
        chiamate.append(app)
        return {"giro": "fatto"}

    async def avviso(app):
        avvisi.append(app)

    monkeypatch.setattr(modulo, "proposer_round", giro)
    monkeypatch.setattr(modulo, "_alert_high_safely", avviso)
    job = _job(started_app, "hiris_mind_proposer")
    assert await scheduled_job(started_app, job.id)() is None
    assert chiamate == []
    assert avvisi == [started_app]


async def test_le_condizioni_si_leggono_anche_una_volta_all_avvio(tmp_path):
    """«Ogni 10 minuti, e una volta all'avvio»: senza la prima lettura un
    guasto gia' aperto prima del riavvio resterebbe invisibile per dieci
    minuti.

    Mutazione ESEGUITA: tolta la chiamata all'avvio -- rossa."""
    watched = mock.AsyncMock()
    with mock.patch.object(startup, "watch_system_conditions", watched):
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)):
            pass
    assert watched.await_count >= 1


async def test_ogni_lavoro_porta_il_nome_della_funzione_che_fa_girare(started_app):
    """Il nome di un lavoro e' cio' che il log stampa a ogni giro («Running
    job ...»): misurato sulla 3.79.1 il 15/10/2026, dopo lo spostamento di F8
    i lavori erano `partial(...)` senza `name=`, e il log diceva 2.289 volte
    «partial» per 16 lavori diversi -- non si capiva piu' quale girasse.

    I lavori si chiedono allo schedulatore, non a un elenco: un lavoro nuovo
    entra nella prova da se'. Il nome atteso e' quello della funzione che il
    lavoro chiama davvero, come APScheduler la scrive (`__qualname__`: per
    una funzione chiusa dentro un'altra porta anche il nome di quella).

    Mutazione ESEGUITA (15/10/2026): un lavoro registrato di nuovo come
    `partial(recipes_job, app)` invece che con `args=` -- rossa, con
    «partial» al posto del nome."""
    jobs = started_app[SCHEDULER_KEY].get_jobs()
    assert len(jobs) >= 10, f"lo schedulatore ha {len(jobs)} lavori: la prova non guarda niente"
    wrong = {}
    for job in jobs:
        func = job.func
        while hasattr(func, "func"):
            func = func.func
        if job.name != func.__qualname__:
            wrong[job.id] = job.name
    assert not wrong, f"lavori col nome sbagliato: {wrong}"
