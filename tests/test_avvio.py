"""La montatura condivisa: l'app del prodotto avviata davvero, una volta per file.

E' la base della Tappa 1 dello sprint «Una fonte sola di verita'»: le prove che
leggevano il testo di `server.py` per sapere cosa fa l'avvio lo chiedono
all'app avviata (`tests/_avvio.py`).
"""
import pytest

from tests._avvio import started_app  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="module")

#: Le app viste dalle prove di questo file, nell'ordine.
_SEEN: list[int] = []


async def test_l_app_avviata_ha_i_lavori_periodici_e_gli_archivi(started_app):
    """Se la montatura si rompesse, ogni prova costruita sopra guarderebbe
    un'app vuota: `get_job` torna `None`, e `None == None` e' verde.

    Mutazione ESEGUITA: cambiato l'id del lavoro `hiris_mind_aggregation` in
    `server._on_startup` -- rossa."""
    _SEEN.append(id(started_app))
    jobs = {job.id for job in started_app["scheduler"].get_jobs()}
    assert len(jobs) >= 10, jobs
    assert "hiris_mind_aggregation" in jobs
    assert started_app["workshop"]._journal is started_app["journal"]


async def test_la_stessa_app_serve_tutte_le_prove_del_file(started_app):
    """Un avvio costa secondi: la fixture e' di modulo. Se diventasse di
    funzione la suite raddoppierebbe senza che niente lo dica.

    Mutazione ESEGUITA: `scope="function"` in `tests/_avvio.py` -- rossa."""
    _SEEN.append(id(started_app))
    assert len(set(_SEEN)) == 1, "ogni prova ha avviato la sua app"
    assert started_app["scheduler"].running
