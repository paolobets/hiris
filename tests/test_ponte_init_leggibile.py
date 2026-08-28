"""L'`init` del ponte diventa leggibile dopo, non solo nel momento in cui passa.

**Il difetto che queste prove chiudono, misurato il 28/08/2026.** Due fatti che
nessun file del repository puo' dire — quale CLI e' arrivata DAVVERO nel
container, e se il ponte parli con l'abbonamento invece che con una chiave a
consumo — vivevano soltanto dentro una riga di log, leggibile solo mentre un
turno passava.

Costo reale: il pin della CLI e' stato alzato a `2.1.241` il 24 agosto con la
verifica rimandata «al prossimo giro», e cinque giorni dopo non era ancora
stata fatta. Non per pigrizia: perche' richiedeva di essere nel posto giusto al
momento giusto. Un fatto che si puo' osservare solo di sfuggita e' un fatto che
prima o poi nessuno osserva.
"""
import time

import pytest

from hiris.app.agent import runner


@pytest.fixture(autouse=True)
def _init_pulito():
    """Ogni prova parte da un processo che non ha ancora visto nessun turno.

    Senza questo, l'ordine dei test deciderebbe l'esito: chi gira per secondo
    troverebbe il valore lasciato dal primo e passerebbe per la ragione
    sbagliata.
    """
    runner._ULTIMO_INIT.clear()
    yield
    runner._ULTIMO_INIT.clear()


def test_prima_di_ogni_turno_e_none_non_un_valore_inventato():
    """`None` vuol dire **non ancora visto**, e non «assente».

    Sono due fatti diversi: un container appena riavviato non e' un container
    guasto, e un chiamante che li confondesse leggerebbe un allarme dove c'e'
    solo un processo giovane.
    """
    assert runner.ultimo_init_del_ponte() is None


def test_dopo_un_turno_la_cli_e_la_fonte_della_chiave_si_rileggono():
    """La prova che il pin e' arrivato fino al container.

    `2.1.999` non e' una versione vera, ed e' voluto: se questa prova leggesse
    il numero pinnato nel `Dockerfile` passerebbe anche se il codice
    restituisse una costante, e si romperebbe a ogni bump legittimo.
    """
    esito = runner.EsitoFlusso()
    esito.init = {"claude_code_version": "2.1.999",
                  "apiKeySource": "none",
                  "tools": [],
                  "mcp_servers": []}

    runner._logga_init(esito, job_id="prova")

    visto = runner.ultimo_init_del_ponte()
    assert visto["cli"] == "2.1.999"
    # `none` e' l'UNICA prova a runtime che si stia usando l'abbonamento e non
    # una chiave a consumo: la denylist dei due nomi non puo' provare cio' che
    # NON e' passato, questo campo si'.
    assert visto["apiKeySource"] == "none"
    assert visto["visto_ts"] == pytest.approx(time.time(), abs=30)


def test_un_init_che_non_arriva_non_cancella_quello_che_si_era_visto():
    """Un turno morto prima dell'`init` non deve trasformare in «mai visto» un
    container che una CLI l'aveva gia' dichiarata: cancellare qui renderebbe la
    lettura un rumore che dipende dall'ultimo turno andato male."""
    primo = runner.EsitoFlusso()
    primo.init = {"claude_code_version": "2.1.999", "apiKeySource": "none",
                  "tools": [], "mcp_servers": []}
    runner._logga_init(primo, job_id="uno")

    runner._logga_init(runner.EsitoFlusso(), job_id="due")  # init assente

    assert runner.ultimo_init_del_ponte()["cli"] == "2.1.999"


def test_chi_legge_non_puo_sporcare_lo_stato_conservato():
    """Si restituisce una copia. Un chiamante che modificasse il dizionario
    ricevuto riscriverebbe la misura di tutti gli altri."""
    esito = runner.EsitoFlusso()
    esito.init = {"claude_code_version": "2.1.999", "apiKeySource": "none",
                  "tools": [], "mcp_servers": []}
    runner._logga_init(esito, job_id="prova")

    runner.ultimo_init_del_ponte()["cli"] = "manomessa"

    assert runner.ultimo_init_del_ponte()["cli"] == "2.1.999"
