import os

import pytest
import pytest_asyncio

# Allow unauthenticated non-ingress requests in the test suite.
# The middleware deny-by-default is for production safety; tests hit the server
# directly without HA Supervisor Ingress forwarding X-Ingress-Path.
os.environ.setdefault("HIRIS_ALLOW_NO_TOKEN", "1")

# Disable CSRF middleware in the test suite: tests use bare TestClient that
# does not inject X-Requested-With (real browsers do, via fetch()).
os.environ.setdefault("HIRIS_ALLOW_NO_CSRF", "1")


# --- Fingere l'ingress del Supervisor, dal 22/09/2026 -----------------------
#
# Dal reperto A-2 scrivere `X-Ingress-Path` non basta piu': il confine chiede
# al Supervisor se riconosce il biscotto di sessione. Le prove che fingono una
# richiesta di ingress devono quindi portare un biscotto E avere un Supervisor
# a cui chiederlo.
#
# **Sta qui e non in ogni file** per una ragione sola: una prova nuova che
# finge l'ingress deve trovare l'attrezzo gia' pronto. Se ognuno se lo
# riscrivesse, il primo che lo scrivesse accomodante -- un Supervisor che dice
# sempre di si' -- renderebbe verde proprio il difetto che A-2 chiude, e
# nessuno se ne accorgerebbe.
#
# **Non e' `autouse`, ed e' deliberato**: il Supervisor finto deve entrare in
# scena solo dove una prova lo chiede. Un finto sempre acceso trasformerebbe
# «l'ingress e' verificato» in «l'ingress passa», che e' l'opposto.

#: La sessione che il Supervisor finto riconosce, e l'unica.
SESSIONE_INGRESS = "sessione-che-il-supervisor-conosce"

#: I biscotti da mandare con una richiesta di ingress finta.
BISCOTTI_INGRESS = {"ingress_session": SESSIONE_INGRESS}


@pytest.fixture()
def supervisor_ingress(monkeypatch):
    """Un Supervisor che riconosce UNA sessione: `SESSIONE_INGRESS`.

    Qualunque altro valore e' «no», che e' il caso dell'add-on vicino: puo'
    scrivere l'intestazione, puo' stare nella rete fidata, non puo' avere un
    biscotto che il Supervisor conosce.
    """
    from hiris.app.api import ingresso

    async def chiedi(sessione):
        return sessione == SESSIONE_INGRESS

    monkeypatch.setattr(ingresso, "_domanda_supervisor", chiedi)
    return BISCOTTI_INGRESS


def credenziale_ponte(app, segreto: str) -> dict:
    """Mette nel contenitore una credenziale di TURNO col segreto dato, e torna
    le intestazioni che il sottoprocesso `claude` manderebbe.

    Dal 22/09/2026 il segreto condiviso non apre piu' niente (reperto A-5): chi
    finge il ponte deve fingere cio' che il ponte ha davvero, cioe' una
    credenziale che vive un turno.

    Il vero `conia` sceglie lui il segreto -- 256 bit da `secrets` -- e qui
    serve conoscerlo in anticipo per scriverlo in una costante. La riga
    d'asserzione in fondo **pinna la forma contro la deriva**: se `conia` e
    `riconosci` cambiassero contratto, questa finta se ne accorgerebbe invece
    di restare verde imitando un vecchio contratto.
    """
    import time

    from hiris.app.api import credenziali

    if app.get("credenziali") is None:
        credenziali.prepara_credenziali(app)
    adesso = time.time()
    app["credenziali"][segreto] = {"mestiere": "ponte", "scade": adesso + 3600}
    assert credenziali.riconosci(app["credenziali"], segreto, adesso=adesso), (
        "la forma della credenziale finta non combacia più con quella vera"
    )
    return {"X-HIRIS-Internal-Token": segreto}


@pytest_asyncio.fixture
async def ponte_produzione(aiohttp_client, tmp_path, monkeypatch):
    """L'app VERA col confine acceso, come il ponte la trova in produzione.

    Le due valvole della suite (`HIRIS_ALLOW_NO_TOKEN`, `HIRIS_ALLOW_NO_CSRF`)
    sono TOLTE: con quelle accese le prove che usano questa fixture
    passerebbero anche col guasto in piedi.

    Viveva in `tests/test_internal_token.py`, uscito il 22/09/2026 insieme al
    segreto condiviso che quel file sorvegliava. Qui e' la stessa fixture senza
    il blocco d'avvio del token, che non esiste piu': la credenziale del ponte
    si conia, non si legge da un'opzione.

    Torna `(client, coda, app, intestazioni)` — le intestazioni sono quelle di
    una credenziale di turno viva, cioe' cio' che il worker manda davvero.
    """
    from unittest.mock import AsyncMock, MagicMock

    from hiris.app import server
    from hiris.app.chat_settings import ChatSettings
    from hiris.app.reasoning.queue import ReasoningQueue

    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    monkeypatch.setenv("HIRIS_DATA_DIR", str(tmp_path))

    app = server.create_app()
    finto_ha = AsyncMock()
    finto_ha.start = AsyncMock()
    finto_ha.stop = AsyncMock()
    finto_ha.add_state_listener = MagicMock()
    finto_ha.start_websocket = AsyncMock()
    app["ha_client"] = finto_ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    # La sorgente del client di test e' un loopback, che NON sta nella rete del
    # Supervisor: nessun bypass dell'ingress, si passa per forza dalla
    # credenziale. E' il caso del worker del ponte, che gira nel container.
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app.on_startup.clear()
    app.on_cleanup.clear()

    intestazioni = credenziale_ponte(app, "credenziale-di-turno-della-prova")
    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    app["reasoning_queue"] = coda
    client = await aiohttp_client(app)
    try:
        yield client, coda, app, intestazioni
    finally:
        coda.close()
