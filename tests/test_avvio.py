"""La montatura condivisa: l'app del prodotto avviata davvero, una volta per file.

E' la base della Tappa 1 dello sprint «Una fonte sola di verita'»: le prove che
leggevano il testo di `server.py` per sapere cosa fa l'avvio lo chiedono
all'app avviata (`tests/_avvio.py`).
"""
import logging

import pytest

from tests._avvio import started_app  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="module")

#: Le app viste dalle prove di questo file, nell'ordine. Gli oggetti, non i
#: loro `id()`: un oggetto liberato puo' lasciare il suo `id` a un altro.
_SEEN: list = []

#: Il livello del registro `hiris` prima che il file avvii l'app.
_HIRIS_LEVEL = logging.getLogger("hiris").level


async def test_l_app_avviata_ha_i_lavori_periodici_e_gli_archivi(started_app):
    """Se la montatura si rompesse, ogni prova costruita sopra guarderebbe
    un'app vuota: `get_job` torna `None`, e `None == None` e' verde.

    Mutazione ESEGUITA: cambiato l'id del lavoro `hiris_mind_aggregation` in
    `server._on_startup` -- rossa."""
    _SEEN.append(started_app)
    jobs = {job.id for job in started_app["scheduler"].get_jobs()}
    assert len(jobs) >= 10, jobs
    assert "hiris_mind_aggregation" in jobs
    assert started_app["workshop"]._journal is started_app["journal"]


async def test_il_registro_hiris_parla_mentre_l_app_e_accesa(started_app):
    """Il montaggio zittisce `hiris` solo durante l'avvio e lo spegnimento.
    Se lo tenesse a CRITICAL finche' l'app e' accesa, ogni prova che usa la
    fixture di modulo e guarda i log (`caplog`) vedrebbe il vuoto, e un
    «non logga X» sarebbe verde senza guardare niente.

    Mutazione ESEGUITA il 03/10/2026: il vecchio `mounted` (livello
    ripristinato solo dopo `_on_cleanup`) -- rossa, «assert 50 == 0»."""
    _SEEN.append(started_app)
    assert logging.getLogger("hiris").level == _HIRIS_LEVEL


async def test_la_stessa_app_serve_tutte_le_prove_del_file(started_app):
    """Un avvio costa secondi: la fixture e' di modulo. Se diventasse di
    funzione la suite raddoppierebbe senza che niente lo dica.

    Sta in CODA apposta e pretende di aver visto le prove prima di lei:
    lanciata da sola non avrebbe niente con cui confrontarsi, e invece di
    passare a vuoto fallisce dicendolo.

    Mutazione ESEGUITA: `scope="function"` in `tests/_avvio.py` -- rossa."""
    _SEEN.append(started_app)
    assert len(_SEEN) >= 2, (
        "lanciata da sola questa prova non confronta niente: "
        "si lancia con il file intero")
    assert all(app is _SEEN[0] for app in _SEEN), "ogni prova ha avviato la sua app"
    assert started_app["scheduler"].running
