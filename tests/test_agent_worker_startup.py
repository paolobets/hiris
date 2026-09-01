"""Il gate del lavoratore che risponde sul Piano Claude Max.

**VERSIONE B (3.0.0).** `should_start_agent_worker` non legge piu' NIENTE
dall'ambiente per decidere se il ponte e' acceso: `PROVIDER_SUBSCRIPTION` e
`BRIDGE_ENABLED` erano le ultime due opzioni dell'add-on lette qui, e sono
uscite dallo schema. Il valore arriva come argomento -- `app["ponte_attivo"]`,
lo stesso che governa la spazzata e l'instradamento della chat -- e il token
resta letto dall'ambiente perche' e' una credenziale, e le credenziali stanno
ancora fra le opzioni.

L'invariante non e' cambiato di una virgola, ed e' l'unica cosa che questi test
hanno sempre pinnato: **nessuna delle due meta' basta da sola**. Un ponte acceso
senza token fa partire un lavoratore che non puo' rispondere; un token senza
ponte fa girare un ciclo che interroga una coda che nessuno riempie.
"""
import asyncio

import pytest

from hiris.app.server import _govern_bridge_worker, should_start_agent_worker


def test_worker_off_by_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker(False) is False


def test_worker_needs_both_flag_and_token(monkeypatch):
    """Il ponte acceso accende il lavoratore solo INSIEME al token.

    Fino alla 2.3.1 la variabile letta qui era CHAT_VIA_SUBSCRIPTION; dalla
    fusione dei due interruttori era BRIDGE_ENABLED (l'opzione `ponte.attivo`);
    dalla versione B e' `ponte.attivo` nell'archivio, e arriva come argomento.
    Cambia da dove viene il primo booleano, non l'invariante: da solo non basta
    mai.
    """
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker(True) is False
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker(True) is True


def test_il_token_da_solo_non_accende_il_lavoratore(monkeypatch):
    """L'IMPLICAZIONE E' USCITA, e questo e' il test che la tiene fuori.

    Fino alla 2.5.0 `provider_subscription` acceso col suo token accendeva il
    ponte da se' (`_sub_first_class`), e quindi anche questo lavoratore. Era
    l'ultima seconda rappresentazione del prodotto: `app["ponte_attivo"]`
    poteva valere True mentre `ponte.attivo` -- cio' che la pagina Modelli
    mostra e scrive -- diceva False.

    Rimettere l'implicazione da qui (`... or bool(token)`) e' la scrittura piu'
    facile del mondo e sembrerebbe una gentilezza. Questo test la vieta: chi ha
    un token e il ponte spento NON deve avere un lavoratore che gira, o la
    pagina tornerebbe a dire una cosa e il prodotto a farne un'altra.
    """
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker(False) is False


# ---------------------------------------------------------------------------
# Il lavoratore SEGUE l'interruttore, invece di essere deciso una volta
# all'avvio. E' la meta' che rende costruibile il bottone «Mettilo primo»:
# accendere il ponte dalla pagina senza far partire chi risponde vorrebbe dire
# accodare ogni turno in una coda che nessuno serve, e ogni messaggio
# aspetterebbe la scadenza prima di ripiegare sulla catena (Task 14) -- cioe' un
# bottone che risponde 200 e fa aspettare.
# ---------------------------------------------------------------------------

class _CompitoFinto:
    """Una finta SCOMODA: non finisce da sola e ricorda di essere stata fermata.

    Un doppio che si dichiarasse `done()` da solo farebbe passare il ramo
    «spegni» senza che nessuno chiami `cancel()`, cioe' proprio la riga che
    serve a fermare il ciclo."""

    def __init__(self):
        self.fermato = False

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.fermato = True


@pytest.mark.asyncio
async def test_accendere_il_ponte_fa_partire_il_lavoratore(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("HIRIS_AGENT_MODE", "dry-run")
    app = {"ponte_attivo": True}
    _govern_bridge_worker(app)
    compito = app.get("agent_worker_task")
    assert compito is not None, (
        "il ponte e' acceso e il token c'e': senza lavoratore ogni turno "
        "accodato scadrebbe prima di ricevere una risposta"
    )
    compito.cancel()
    with pytest.raises(asyncio.CancelledError):
        await compito


@pytest.mark.asyncio
async def test_spegnere_il_ponte_ferma_il_lavoratore(monkeypatch):
    """Il ramo simmetrico, e non e' una simmetria di cortesia: senza,
    spegnere il ponte lascerebbe un ciclo che interroga la coda ogni tre
    secondi per sempre."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    finto = _CompitoFinto()
    app = {"ponte_attivo": False, "agent_worker_task": finto}
    _govern_bridge_worker(app)
    assert finto.fermato is True
    assert app["agent_worker_task"] is None


@pytest.mark.asyncio
async def test_un_lavoratore_gia_vivo_non_si_duplica(monkeypatch):
    """`_recompute_chain` gira a OGNI salvataggio della pagina Modelli, non
    solo quando il ponte cambia: salvare due volte di fila col ponte acceso
    non deve produrre due cicli che si contendono la stessa coda."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    finto = _CompitoFinto()
    app = {"ponte_attivo": True, "agent_worker_task": finto}
    _govern_bridge_worker(app)
    assert app["agent_worker_task"] is finto
    assert finto.fermato is False


# ---------------------------------------------------------------------------
# C3 della revisione del commit 3.0.0: **il NODO era pinnato, l'ARCO no.**
# I tre test qui sopra chiamano `_govern_bridge_worker` DIRETTAMENTE.
# Nessuno provava che `_recompute_chain` la chiamasse, e sostituire quella
# riga con `pass` lasciava la suite intera verde (1612 passed). E' esattamente
# la quarta condizione senza cui «Mettilo primo» torna a essere un bottone che
# risponde 200 e fa aspettare cinque minuti: il valore arriva al disco, il
# runtime lo segue, ma nessuno risponde sulla coda.
#
# Si prova col COMPORTAMENTO e non col sorgente: `_recompute_chain` sull'app
# vera, e il lavoratore c'e' o non c'e'.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ricalcola_catena_accende_il_lavoratore_non_solo_l_interruttore(monkeypatch):
    """Il gesto «Mettilo primo» passa di qui: la PUT scrive l'archivio e chiama
    `_recompute_chain`. Se questa si limitasse a cablare `app["ponte_attivo"]`
    senza governare il lavoratore, ogni turno andrebbe in una coda senza
    consumatore e aspetterebbe la scadenza prima di ripiegare sulla catena."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("HIRIS_AGENT_MODE", "dry-run")
    from hiris.app import server

    app = {"models_config": {"ponte": {"attivo": True}, "chain_order": []}}
    server._recompute_chain(app)

    assert app["ponte_attivo"] is True
    compito = app.get("agent_worker_task")
    assert compito is not None, (
        "il salvataggio ha acceso il ponte e non ha fatto partire chi "
        "risponde: il bottone «Mettilo primo» risponde 200 e fa aspettare"
    )
    compito.cancel()
    with pytest.raises(asyncio.CancelledError):
        await compito


@pytest.mark.asyncio
async def test_ricalcola_catena_ferma_il_lavoratore_quando_il_ponte_si_spegne(monkeypatch):
    """Il ramo inverso dello stesso arco: «Togli il piano dalla catena» deve
    fermare il ciclo, o resterebbe a interrogare una coda vuota ogni tre
    secondi finche' l'add-on non viene riavviato -- venticinquemila righe in
    due ore, che e' cio' che ha fatto scorrere via un avvio dal registro."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    from hiris.app import server

    finto = _CompitoFinto()
    app = {"models_config": {"ponte": {"attivo": False}, "chain_order": []},
           "agent_worker_task": finto}
    server._recompute_chain(app)

    assert app["ponte_attivo"] is False
    assert finto.fermato is True
    assert app["agent_worker_task"] is None


def test_senza_un_loop_non_si_avvia_niente_e_non_si_solleva_niente(monkeypatch):
    """`_recompute_chain` e' una funzione di modulo e i test la chiamano fuori
    da un server (`test_model_activation.py`). Un compito asincrono non ha dove
    girare, e non averlo non e' un errore da inghiottire: e' il fatto vero."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    app = {"ponte_attivo": True}
    _govern_bridge_worker(app)
    assert app.get("agent_worker_task") is None
