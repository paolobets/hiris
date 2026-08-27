"""Le due rotte -- e la prova che dalla porta HTTP esce la STESSA promessa.

Fixture `client`: l'app VERA (`create_app`), non un'app costruita a mano con
le sole due rotte in prova -- vedi lo stesso ragionamento in
`test_impostazioni_api.py`. La rotta nuova deve passare dagli stessi
middleware di ogni altra (`internal_auth_middleware`, `csrf_middleware`): un
test che li scavalcasse non direbbe niente su cio' che accade in produzione.

Per la maggior parte dei test il CSRF resta silenzioso perche' `conftest.py`
mette `HIRIS_ALLOW_NO_CSRF=1` per l'intera suite. Ma l'invariante «questa
DELETE rifiuta le scritture cross-site» merita un test proprio, non solo la
copertura generica di `test_security.py`: la sorella `/api/memoria/{id}` ha
lo stesso trattamento in `test_impostazioni_api.py` (fixture `csrf_stretto`,
riusata qui per import -- niente di specifico alle impostazioni, stesso
riuso cross-file gia' praticato dal progetto per `client`). Senza un test
dedicato, una futura esenzione aggiunta per errore (o una registrazione
della rotta prima del middleware) lascerebbe la suite verde: vedi
`test_delete_senza_x_requested_with_e_403_e_non_disdice` piu' sotto.
"""
import os

import pytest
import pytest_asyncio

from hiris.app.azione.cronaca import Cronaca
from hiris.app.chat_store import close_all_stores
from hiris.app.schedulatore.archivio import ArchivioPromesse
from hiris.app.server import create_app

# Fixture generica (annulla la valvola `HIRIS_ALLOW_NO_CSRF` per la suite),
# senza niente di specifico alle impostazioni: stesso riuso cross-file gia'
# praticato dal progetto per `client` (vedi `test_elenco_anthropic.py`,
# `test_models_api.py`). Non ne scrivo una seconda identica.
from tests.test_impostazioni_api import csrf_stretto  # noqa: F401


@pytest.fixture(autouse=True)
def reset_chat_stores():
    """Chiude le connessioni SQLite dopo ogni test (file-lock su Windows)."""
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app["promesse"] = ArchivioPromesse(os.path.join(str(tmp_path), "promesse.db"))
    # La cronaca (`GET /api/esecuzioni/{id}`, rilievo ① della review finale):
    # anche lei nasce qui a mano, come `promesse` due righe sopra, perche'
    # `on_startup.clear()` toglie il montaggio vero che la costruirebbe da
    # sola in `create_app` -> `_avvia` (server.py).
    app["cronaca"] = Cronaca(os.path.join(str(tmp_path), "azioni.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app["promesse"].close()
    app["cronaca"].close()


@pytest.mark.asyncio
async def test_get_promesse_torna_le_in_sospeso(client):
    archivio = client.app["promesse"]
    archivio.crea({"specie": "chiedi", "frase": "x", "quando_ts": 3601.0,
                   "domanda": "e' aumentata?"}, adesso=1.0)

    risposta = await client.get("/api/promesse")
    assert risposta.status == 200
    corpo = await risposta.json()
    assert len(corpo["promesse"]) == 1


@pytest.mark.asyncio
async def test_get_promesse_tutte_include_le_concluse(client):
    archivio = client.app["promesse"]
    ident = archivio.crea({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          adesso=1.0)["promessa"]["id"]
    archivio.concludi(ident, stato="mantenuta", adesso=2.0)

    corpo = await (await client.get("/api/promesse?tutte=1")).json()
    assert len(corpo["promesse"]) == 1
    corpo = await (await client.get("/api/promesse")).json()
    assert corpo["promesse"] == []


@pytest.mark.asyncio
async def test_delete_disdice_e_una_gia_conclusa_da_409(client):
    archivio = client.app["promesse"]
    ident = archivio.crea({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          adesso=1.0)["promessa"]["id"]

    primo = await client.delete(f"/api/promesse/{ident}")
    assert primo.status == 200
    # Il corpo del 200 deve portare la promessa vera, non un `{}`: e' il
    # corpo che la pagina usera' per aggiornarsi senza una seconda GET.
    corpo = await primo.json()
    assert corpo["promessa"]["id"] == ident
    assert corpo["promessa"]["stato"] == "disdetta"
    assert archivio.leggi(ident)["stato"] == "disdetta"

    secondo = await client.delete(f"/api/promesse/{ident}")
    assert secondo.status == 409
    assert "errore" in await secondo.json()


@pytest.mark.asyncio
async def test_delete_di_un_id_inesistente_da_404(client):
    assert (await client.delete("/api/promesse/mai-esistita")).status == 404


@pytest.mark.asyncio
async def test_delete_senza_x_requested_with_e_403_e_non_disdice(client, csrf_stretto):
    """La rotta non ha un'autenticazione propria: passa dallo stesso
    `csrf_middleware` di `/api/memoria/{id}`. Un 403 non deve aver toccato
    l'archivio -- la promessa resta `in_attesa`, disdicibile per davvero piu'
    tardi, non "disdetta a meta'"."""
    archivio = client.app["promesse"]
    ident = archivio.crea({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          adesso=1.0)["promessa"]["id"]

    risposta = await client.delete(f"/api/promesse/{ident}")
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    assert archivio.leggi(ident)["stato"] == "in_attesa"


@pytest.mark.asyncio
async def test_delete_con_x_requested_with_disdice_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app["promesse"]
    ident = archivio.crea({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          adesso=1.0)["promessa"]["id"]

    risposta = await client.delete(f"/api/promesse/{ident}",
                                   headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.leggi(ident)["stato"] == "disdetta"


@pytest.mark.asyncio
async def test_la_rotta_e_lo_strumento_danno_la_STESSA_forma(client):
    """Fondamenta n.3: una promessa vista dalla chat e dalla pagina e' la stessa."""
    from hiris.app.casa.strumenti import DispatcherStrumenti

    archivio = client.app["promesse"]
    archivio.crea({"specie": "chiedi", "frase": "x", "quando_ts": 3601.0,
                   "domanda": "?"}, adesso=1.0)

    da_http = (await (await client.get("/api/promesse")).json())["promesse"][0]
    d = DispatcherStrumenti(None, None, promesse=archivio)
    da_strumento = (await d.dispatch("promesse", {}))["promesse"][0]

    assert da_http == da_strumento
    # La lista non deve essere vuota: un confronto fra due liste vuote
    # passerebbe a vuoto e non proverebbe niente sulla forma.
    assert da_http


# ---------------------------------------------------------------------------
# GET /api/esecuzioni/{id} -- review finale, rilievo ①: la cronaca si chiede
# a parte, per identificatore. Non ricostruisce niente di suo: quel che esce
# e' esattamente cio' che `Cronaca.leggi` gia' serializza.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_esecuzione_torna_la_riga_di_cronaca(client):
    cronaca = client.app["cronaca"]
    ident = cronaca.registra(
        origine="schedulatore", servizio="light.turn_on", entita=["light.studio"],
        eseguito=True, cambiato=["light.studio"], adesso=1_755_600_000.0)

    risposta = await client.get(f"/api/esecuzioni/{ident}")
    assert risposta.status == 200
    corpo = await risposta.json()
    # Nessun dizionario nuovo: la forma e' esattamente quella di
    # `cronaca.leggi(ident)`, non una sua ricostruzione da parte della rotta
    # (mutazione: se la rotta smettesse di usare `Cronaca.leggi` e
    # ricostruisse a mano un sottoinsieme dei campi, questo confronto lo
    # vedrebbe subito).
    assert corpo["esecuzione"] == cronaca.leggi(ident)
    assert corpo["esecuzione"]["servizio"] == "light.turn_on"
    assert corpo["esecuzione"]["cambiato"] == ["light.studio"]


@pytest.mark.asyncio
async def test_get_esecuzione_inesistente_da_404_col_motivo_leggibile(client):
    risposta = await client.get("/api/esecuzioni/mai-esistita")
    assert risposta.status == 404
    corpo = await risposta.json()
    assert corpo["errore"] == "non ho nessuna esecuzione con quell'identificatore."


@pytest.mark.asyncio
async def test_get_esecuzione_senza_cronaca_da_503(aiohttp_client):
    # App a parte, SENZA "cronaca": mutare `client.app` di un'app gia'
    # avviata e' deprecato in aiohttp (e l'ha confermato un tentativo
    # precedente di questo stesso test, con un `del client.app["cronaca"]`
    # dopo il montaggio). Qui la chiave manca fin dall'inizio.
    #
    # Mutazione: se la rotta leggesse `request.app["cronaca"]` con
    # l'indicizzazione diretta invece di `.get(...)`, questa riga
    # solleverebbe un KeyError invece del 503 onesto -- il test lo
    # vedrebbe come un 500.
    app = create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    risposta = await c.get("/api/esecuzioni/qualsiasi")
    assert risposta.status == 503
    assert "errore" in await risposta.json()


@pytest.mark.asyncio
async def test_get_esecuzione_non_richiede_x_requested_with(client, csrf_stretto):
    """E' una rotta di lettura (metodo "safe"): niente csrf_middleware da
    passare, stessa esenzione di `GET /api/promesse`. Mutazione: se la rotta
    finisse dietro un controllo CSRF (o venisse registrata come POST/GET
    ambigua), questa richiesta senza header tornerebbe 403 invece di 404."""
    cronaca = client.app["cronaca"]
    ident = cronaca.registra(origine="chat", servizio="a.b", entita=[],
                             eseguito=True, adesso=1.0)
    risposta = await client.get(f"/api/esecuzioni/{ident}")
    assert risposta.status == 200
