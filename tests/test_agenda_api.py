"""Le due rotte -- e la prova che dalla porta HTTP esce la STESSA promessa.

Fixture `client`: l'app VERA (`create_app`), non un'app costruita a mano con
le sole due rotte in prova -- vedi lo stesso ragionamento in
`test_settings_api.py`. La rotta nuova deve passare dagli stessi
middleware di ogni altra (`internal_auth_middleware`, `csrf_middleware`): un
test che li scavalcasse non direbbe niente su cio' che accade in produzione.

Per la maggior parte dei test il CSRF resta silenzioso perche' `conftest.py`
mette `HIRIS_ALLOW_NO_CSRF=1` per l'intera suite. Ma l'invariante «questa
DELETE rifiuta le scritture cross-site» merita un test proprio, non solo la
copertura generica di `test_security.py`: la sorella `/api/memories/{id}` ha
lo stesso trattamento in `test_settings_api.py` (fixture `csrf_stretto`,
riusata qui per import -- niente di specifico alle impostazioni, stesso
riuso cross-file gia' praticato dal progetto per `client`). Senza un test
dedicato, una futura esenzione aggiunta per errore (o una registrazione
della rotta prima del middleware) lascerebbe la suite verde: vedi
`test_delete_senza_x_requested_with_e_403_e_non_disdice` piu' sotto.
"""
import os

import pytest
import pytest_asyncio

from hiris.app.action.journal import Journal
from hiris.app.chat_store import close_all_stores
from hiris.app.keeper.store import AgendaStore
from hiris.app.server import create_app

# Fixture generica (annulla la valvola `HIRIS_ALLOW_NO_CSRF` per la suite),
# senza niente di specifico alle impostazioni: stesso riuso cross-file gia'
# praticato dal progetto per `client` (vedi `test_anthropic_list.py`,
# `test_models_api.py`). Non ne scrivo una seconda identica.
from tests.test_settings_api import csrf_stretto  # noqa: F401


@pytest.fixture(autouse=True)
def reset_chat_stores():
    """Chiude le connessioni SQLite dopo ogni test (file-lock su Windows)."""
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app["agenda"] = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    # La cronaca (`GET /api/executions/{id}`, rilievo ① della review finale):
    # anche lei nasce qui a mano, come `promesse` due righe sopra, perche'
    # `on_startup.clear()` toglie il montaggio vero che la costruirebbe da
    # sola in `create_app` -> `_avvia` (server.py).
    app["journal"] = Journal(os.path.join(str(tmp_path), "azioni.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app["agenda"].close()
    app["journal"].close()


@pytest.mark.asyncio
async def test_get_promesse_torna_le_in_sospeso(client):
    archivio = client.app["agenda"]
    archivio.create({"specie": "chiedi", "frase": "x", "quando_ts": 3601.0,
                   "domanda": "e' aumentata?"}, now=1.0)

    risposta = await client.get("/api/agenda")
    assert risposta.status == 200
    corpo = await risposta.json()
    assert len(corpo["agenda"]) == 1


@pytest.mark.asyncio
async def test_get_promesse_tutte_include_le_concluse(client):
    archivio = client.app["agenda"]
    ident = archivio.create({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          now=1.0)["promessa"]["id"]
    archivio.concludi(ident, state="mantenuta", now=2.0)

    corpo = await (await client.get("/api/agenda?all=1")).json()
    assert len(corpo["agenda"]) == 1
    corpo = await (await client.get("/api/agenda")).json()
    assert corpo["agenda"] == []


@pytest.mark.asyncio
async def test_delete_disdice_e_una_gia_conclusa_da_409(client):
    archivio = client.app["agenda"]
    ident = archivio.create({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          now=1.0)["promessa"]["id"]

    primo = await client.delete(f"/api/agenda/{ident}")
    assert primo.status == 200
    # Il corpo del 200 deve portare la promessa vera, non un `{}`: e' il
    # corpo che la pagina usera' per aggiornarsi senza una seconda GET.
    corpo = await primo.json()
    assert corpo["promessa"]["id"] == ident
    assert corpo["promessa"]["stato"] == "disdetta"
    assert archivio.read(ident)["stato"] == "disdetta"

    secondo = await client.delete(f"/api/agenda/{ident}")
    assert secondo.status == 409
    assert "error" in await secondo.json()


@pytest.mark.asyncio
async def test_delete_di_un_id_inesistente_da_404(client):
    assert (await client.delete("/api/agenda/mai-esistita")).status == 404


@pytest.mark.asyncio
async def test_delete_senza_x_requested_with_e_403_e_non_disdice(client, csrf_stretto):
    """La rotta non ha un'autenticazione propria: passa dallo stesso
    `csrf_middleware` di `/api/memories/{id}`. Un 403 non deve aver toccato
    l'archivio -- la promessa resta `in_attesa`, disdicibile per davvero piu'
    tardi, non "disdetta a meta'"."""
    archivio = client.app["agenda"]
    ident = archivio.create({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          now=1.0)["promessa"]["id"]

    risposta = await client.delete(f"/api/agenda/{ident}")
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    assert archivio.read(ident)["stato"] == "in_attesa"


@pytest.mark.asyncio
async def test_delete_con_x_requested_with_disdice_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app["agenda"]
    ident = archivio.create({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          now=1.0)["promessa"]["id"]

    risposta = await client.delete(f"/api/agenda/{ident}",
                                   headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.read(ident)["stato"] == "disdetta"


@pytest.mark.asyncio
async def test_la_rotta_e_lo_strumento_danno_la_STESSA_forma(client):
    """Fondamenta n.3: una promessa vista dalla chat e dalla pagina e' la stessa.

    **Cosa questo test prova, e cosa NON prova piu' (fetta «la rinomina»,
    lotto dei campi JSON).** Prova la PROMESSA: `serializza()` e' una sola, e i
    suoi diciassette campi escono identici dalle due porte -- e' questo che la
    fondamenta n.3 protegge, ed e' rimasto intatto.

    Non prova piu' l'INVOLUCRO, e la divergenza NON e' piu' temporanea --
    corretto il 02/09, con la fetta dei nomi degli strumenti. La rotta dice
    `agenda` (il collettivo, come il percorso `/api/agenda`); lo STRUMENTO ora
    si chiama `agenda` anche lui, ma il suo involucro resta `promesse`, e non
    perche' qualcuno se ne sia dimenticato: e' una chiave del payload che il
    modello legge, cioe' la stessa categoria delle 42 chiavi di `input_schema`
    che quella fetta lascia in italiano per decisione (24 su 45 sono anche un
    nome di colonna, e il database e' fuori). La frase di prima -- «i tredici
    nomi degli strumenti sono congelati fino alla fetta successiva» -- era
    vera quel giorno ed e' scaduta: e' proprio la specie «citazione resa
    falsa» che questo ramo ha imparato a cercare.

    I due involucri sono due dict LETTERALI in due file diversi
    (`api/handlers_agenda.py` e `home_space/tools.py::_list_agenda`), mai lo
    stesso oggetto: nessuno dei due si porta dietro l'altro, ed e' questo che
    rende il confronto sul CORPO l'unica cosa che valga la pena pinzare.
    """
    from hiris.app.home_space.tools import ToolDispatcher

    archivio = client.app["agenda"]
    archivio.create({"specie": "chiedi", "frase": "x", "quando_ts": 3601.0,
                   "domanda": "?"}, now=1.0)

    da_http = (await (await client.get("/api/agenda")).json())["agenda"][0]
    d = ToolDispatcher(None, None, agenda=archivio)
    da_strumento = (await d.dispatch("agenda", {}))["promesse"][0]

    assert da_http == da_strumento
    # La lista non deve essere vuota: un confronto fra due liste vuote
    # passerebbe a vuoto e non proverebbe niente sulla forma.
    assert da_http


# ---------------------------------------------------------------------------
# GET /api/executions/{id} -- review finale, rilievo ①: la cronaca si chiede
# a parte, per identificatore. Non ricostruisce niente di suo: quel che esce
# e' esattamente cio' che `Journal.read` gia' serializza.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_esecuzione_torna_la_riga_di_cronaca(client):
    journal = client.app["journal"]
    ident = journal.log(
        actor="schedulatore", service="light.turn_on", entity=["light.studio"],
        executed=True, changed=["light.studio"], now=1_755_600_000.0)

    risposta = await client.get(f"/api/executions/{ident}")
    assert risposta.status == 200
    corpo = await risposta.json()
    # Nessun dizionario nuovo: la forma e' esattamente quella di
    # `cronaca.read(ident)`, non una sua ricostruzione da parte della rotta
    # (mutazione: se la rotta smettesse di usare `Journal.read` e
    # ricostruisse a mano un sottoinsieme dei campi, questo confronto lo
    # vedrebbe subito).
    assert corpo["execution"] == journal.read(ident)
    assert corpo["execution"]["servizio"] == "light.turn_on"
    assert corpo["execution"]["cambiato"] == ["light.studio"]


@pytest.mark.asyncio
async def test_get_esecuzione_inesistente_da_404_col_motivo_leggibile(client):
    risposta = await client.get("/api/executions/mai-esistita")
    assert risposta.status == 404
    corpo = await risposta.json()
    assert corpo["error"] == "non ho nessuna esecuzione con quell'identificatore."


@pytest.mark.asyncio
async def test_get_esecuzione_senza_cronaca_da_503(aiohttp_client):
    # App a parte, SENZA "cronaca": mutare `client.app` di un'app gia'
    # avviata e' deprecato in aiohttp (e l'ha confermato un tentativo
    # precedente di questo stesso test, con un `del client.app["journal"]`
    # dopo il montaggio). Qui la chiave manca fin dall'inizio.
    #
    # Mutazione: se la rotta leggesse `request.app["journal"]` con
    # l'indicizzazione diretta invece di `.get(...)`, questa riga
    # solleverebbe un KeyError invece del 503 onesto -- il test lo
    # vedrebbe come un 500.
    app = create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    risposta = await c.get("/api/executions/qualsiasi")
    assert risposta.status == 503
    assert "error" in await risposta.json()


@pytest.mark.asyncio
async def test_get_esecuzione_non_richiede_x_requested_with(client, csrf_stretto):
    """E' una rotta di lettura (metodo "safe"): niente csrf_middleware da
    passare, stessa esenzione di `GET /api/agenda`. Mutazione: se la rotta
    finisse dietro un controllo CSRF (o venisse registrata come POST/GET
    ambigua), questa richiesta senza header tornerebbe 403 invece di 404."""
    journal = client.app["journal"]
    ident = journal.log(actor="chat", service="a.b", entity=[],
                             executed=True, now=1.0)
    risposta = await client.get(f"/api/executions/{ident}")
    assert risposta.status == 200
