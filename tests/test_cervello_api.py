"""Le due rotte della pagina dell'osservatore."""
import pytest

from hiris.app.api.handlers_cervello import handle_oggetti, handle_osservate


class _FintoArchivio:
    def __init__(self):
        self.chiesto = None

    def facts(self, *, day=None, limit=200):
        self.chiesto = {"giorno": day, "limite": limit}
        return [{"id": 1, "giorno": "2026-08-24", "genere": "funzionamento",
                 "protagonista": "climate.camera_t", "inizio_ts": 1.0,
                 "fine_ts": 2.0, "corpo": {"comprimari": []}}]


class _FintoOsservatore:
    def watching(self):
        return [{"soggetto": "climate.camera_t", "gamba": "comfort",
                 "provenienza": "pavimento"}]


def _richiesta(app, query=None):
    class _R:
        def __init__(self):
            self.app = app
            self.query = query or {}
    return _R()


@pytest.mark.asyncio
async def test_osservate_dice_cosa_si_guarda_e_perche():
    r = await handle_osservate(_richiesta({"osservatore": _FintoOsservatore()}))
    assert r.status == 200


@pytest.mark.asyncio
async def test_osservate_porta_la_provenienza_di_ogni_voce():
    """La pagina decide se una voce si puo' togliere guardando questo campo:
    senza, non c'e' modo di distinguere pavimento da obiettivo (spec §7)."""
    r = await handle_osservate(_richiesta({"osservatore": _FintoOsservatore()}))
    corpo = _corpo(r)
    assert corpo["osservate"][0]["provenienza"] == "pavimento"


@pytest.mark.asyncio
async def test_senza_osservatore_la_rotta_lo_DICHIARA():
    """Un elenco vuoto direbbe «non guardo niente»; l'osservatore assente e'
    un'altra cosa, ed e' la distinzione che questo prodotto difende ovunque."""
    r = await handle_osservate(_richiesta({}))
    assert r.status == 503


@pytest.mark.asyncio
async def test_gli_oggetti_si_leggono():
    r = await handle_oggetti(_richiesta({"osservazioni": _FintoArchivio()}))
    assert r.status == 200


@pytest.mark.asyncio
async def test_gli_oggetti_filtrano_per_giorno_dalla_query():
    archivio = _FintoArchivio()
    r = await handle_oggetti(
        _richiesta({"osservazioni": archivio}, query={"giorno": "2026-08-24"}))
    assert r.status == 200
    assert archivio.chiesto["giorno"] == "2026-08-24"


@pytest.mark.asyncio
async def test_senza_giorno_nella_query_non_si_inventa_una_data():
    """`giorno` assente deve arrivare all'archivio come `None`, non come una
    stringa vuota o una data scelta qui: e' l'archivio a sapere cosa significa
    "nessun filtro" (`archivio.py::facts`)."""
    archivio = _FintoArchivio()
    r = await handle_oggetti(_richiesta({"osservazioni": archivio}))
    assert r.status == 200
    assert archivio.chiesto["giorno"] is None


@pytest.mark.asyncio
async def test_senza_archivio_la_rotta_lo_DICHIARA():
    r = await handle_oggetti(_richiesta({}))
    assert r.status == 503


def _corpo(response):
    import json
    return json.loads(response.body)
