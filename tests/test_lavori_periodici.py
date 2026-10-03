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

from hiris.app import server
from tests._avvio import started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

pytestmark = pytest.mark.asyncio(loop_scope="module")


def _job(app, job_id):
    job = app["scheduler"].get_job(job_id)
    assert job is not None, f"il lavoro {job_id} non e' registrato"
    return job


async def test_i_lavori_del_cervello_sono_registrati(started_app):
    """L'aggregazione notturna e la potatura. Senza il primo il grezzo si
    accumula e nessun oggetto nasce; senza il secondo l'archivio cresce per
    sempre."""
    _job(started_app, "hiris_mind_aggregation")
    _job(started_app, "hiris_mind_pruning")


async def test_l_aggregazione_gira_alle_00_20_della_casa(started_app):
    """Aggregare a mezzanotte esatta prenderebbe un giorno ancora aperto: le
    00:20 sono l'ora vera.

    Mutazione ESEGUITA: `hour=0` -> `hour=23` nell'`add_job` -- rossa."""
    assert str(_job(started_app, "hiris_mind_aggregation").trigger) == \
        "cron[hour='0', minute='20']"


async def test_la_potatura_gira_alle_03_00(started_app):
    """Lontana dall'aggregazione apposta: l'una deve finire prima che l'altra
    cominci a leggere il grezzo."""
    assert str(_job(started_app, "hiris_mind_pruning").trigger) == \
        "cron[hour='3', minute='0']"


async def test_le_condizioni_di_sistema_si_rileggono_ogni_dieci_minuti(started_app):
    """Senza questo lavoro `watch_system_conditions` non ha nessun chiamante
    di produzione, e i guasti non diventano oggetti.

    Mutazione ESEGUITA: il lavoro chiama un'altra funzione -- rossa (nessuna
    chiamata a `watch_system_conditions`)."""
    job = _job(started_app, "hiris_mind_conditions")
    assert str(job.trigger) == "interval[0:10:00]"
    with mock.patch.object(server, "watch_system_conditions",
                           mock.AsyncMock()) as watched:
        await job.func()
    watched.assert_awaited_once()
    assert watched.await_args.args[0] is started_app


async def test_le_tracce_delle_automazioni_si_rileggono_ogni_due_minuti(started_app):
    """Senza questo lavoro le automazioni segnate resterebbero segnate per
    sempre senza che nessuno rileggesse le loro tracce."""
    job = _job(started_app, "hiris_mind_automation_traces")
    assert str(job.trigger) == "interval[0:02:00]"
    with mock.patch.object(server, "watch_automation_outcomes",
                           mock.AsyncMock()) as watched:
        await job.func()
    watched.assert_awaited_once()


async def test_l_inventario_si_ricarica_ogni_due_minuti(started_app):
    """Un'indisponibilita' passeggera di Home Assistant deve rientrare in
    pochi minuti, non alla prossima notte."""
    job = _job(started_app, "hiris_entity_cache_reload")
    assert str(job.trigger) == "interval[0:02:00]"
    with mock.patch.object(server, "reload_entity_inventory",
                           mock.AsyncMock()) as reloaded:
        await job.func()
    reloaded.assert_awaited_once()
    assert reloaded.await_args.args[0] is started_app["entity_cache"]


async def test_i_lavori_periodici_sono_sedici_come_dichiara_il_readme(started_app):
    """Un lavoro periodico gira per sempre e costa per sempre: aggiungerne uno
    senza accorgersene e' il modo in cui una casa comincia a fare rumore di
    notte. Il numero vive anche nel README, e questa prova esiste perche' non
    divergano (la storia dei sedici: `docs/BACKLOG.md` e il README).

    Mutazione ESEGUITA: un `add_job` in piu' in `_on_startup` -- rossa."""
    jobs = started_app["scheduler"].get_jobs()
    assert len(jobs) == 16, sorted(job.id for job in jobs)
    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8")
    assert "registers **sixteen** APScheduler jobs" in readme, (
        "il README non dichiara piu' sedici lavori periodici: il numero "
        "vive in due posti e questa prova esiste perche' non divergano.")


async def test_l_attuatore_e_in_pausa_e_niente_lo_fa_girare(tmp_path):
    """**L'attuatore e' fermo dal 01/10/2026, per decisione del proprietario**
    (voce «L'attuatore e' in pausa» in `docs/BACKLOG.md`): il suo lavoro non e'
    registrato, e niente all'avvio lo chiama. Chi lo riaccende toglie questa
    prova insieme alla pausa, non la aggira.

    Mutazione ESEGUITA: rimesso l'`add_job` di `hiris_mind_actuator` --
    rossa."""
    called = mock.AsyncMock()
    with mock.patch.object(server, "actuator_round", called):
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
            assert app["scheduler"].get_job("hiris_mind_actuator") is None
            for job in app["scheduler"].get_jobs():
                assert "actuator" not in job.id
    called.assert_not_awaited()


async def test_le_condizioni_si_leggono_anche_una_volta_all_avvio(tmp_path):
    """«Ogni 10 minuti, e una volta all'avvio»: senza la prima lettura un
    guasto gia' aperto prima del riavvio resterebbe invisibile per dieci
    minuti.

    Mutazione ESEGUITA: tolta la chiamata all'avvio -- rossa."""
    watched = mock.AsyncMock()
    with mock.patch.object(server, "watch_system_conditions", watched):
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)):
            pass
    assert watched.await_count >= 1
