"""Le due rotte della pagina dell'osservatore."""
import pytest

from hiris.app.api.handlers_mind import handle_facts, handle_watching
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher
from tests._contracts import assert_stessa_firma


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


assert_stessa_firma(ObservationsStore.facts, _FintoArchivio.facts, nome="facts")
assert_stessa_firma(Watcher.watching, _FintoOsservatore.watching, nome="watching")


@pytest.mark.asyncio
async def test_osservate_dice_cosa_si_guarda_e_perche():
    r = await handle_watching(_richiesta({"watcher": _FintoOsservatore()}))
    assert r.status == 200


@pytest.mark.asyncio
async def test_osservate_porta_la_provenienza_di_ogni_voce():
    """La pagina decide se una voce si puo' togliere guardando questo campo:
    senza, non c'e' modo di distinguere pavimento da obiettivo (spec §7)."""
    r = await handle_watching(_richiesta({"watcher": _FintoOsservatore()}))
    corpo = _corpo(r)
    assert corpo["watching"][0]["provenienza"] == "pavimento"


@pytest.mark.asyncio
async def test_senza_osservatore_la_rotta_lo_DICHIARA():
    """Un elenco vuoto direbbe «non guardo niente»; l'osservatore assente e'
    un'altra cosa, ed e' la distinzione che questo prodotto difende ovunque."""
    r = await handle_watching(_richiesta({}))
    assert r.status == 503


@pytest.mark.asyncio
async def test_gli_oggetti_si_leggono():
    r = await handle_facts(_richiesta({"observations": _FintoArchivio()}))
    assert r.status == 200
    # L'INVOLUCRO, per nome. Prima questi test guardavano solo lo `status`, e
    # la sorella `handle_watching` era l'unica delle due a nominare il proprio
    # (riga sopra, `corpo["watching"]`): rinominando `facts` in `oggetti` la
    # rotta emetteva un corpo che `watcher-route.js::esito.corpo.facts`
    # non sa leggere, e tutti e quattro i cancelli restavano verdi. Trovato con
    # una batteria di mutazioni, una per involucro convertito -- non leggendo.
    assert set(_corpo(r)) == {"facts"}


@pytest.mark.asyncio
async def test_gli_oggetti_filtrano_per_giorno_dalla_query():
    archivio = _FintoArchivio()
    r = await handle_facts(
        _richiesta({"observations": archivio}, query={"day": "2026-08-24"}))
    assert r.status == 200
    assert archivio.chiesto["giorno"] == "2026-08-24"


@pytest.mark.asyncio
async def test_senza_giorno_nella_query_non_si_inventa_una_data():
    """`giorno` assente deve arrivare all'archivio come `None`, non come una
    stringa vuota o una data scelta qui: e' l'archivio a sapere cosa significa
    "nessun filtro" (`store.py::facts`)."""
    archivio = _FintoArchivio()
    r = await handle_facts(_richiesta({"observations": archivio}))
    assert r.status == 200
    assert archivio.chiesto["giorno"] is None


@pytest.mark.asyncio
async def test_senza_archivio_la_rotta_lo_DICHIARA():
    r = await handle_facts(_richiesta({}))
    assert r.status == 503


def _corpo(response):
    import json
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# La strada vera, per intero: l'evento di Home Assistant -> `Watcher` ->
# l'archivio SQLite -> l'aggregazione -> `GET /api/mind/facts`. Nessuna
# finta in mezzo: e' la prova che il nome ARRIVA alla riga che il
# proprietario legge, non che un pezzo isolato lo sappia trasportare.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_nome_viaggia_dall_evento_fino_alla_rotta_che_il_proprietario_legge(tmp_path):
    """Mutazione ESEGUITA: togliere la riga
    `friendly_name=_text_or_none(attributes.get("friendly_name"))` dalla
    chiamata a `record()` in `Watcher.watch_reading` (`mind/watcher.py`) --
    il test torna rosso su `assert corpo_oggetto["nome"] == "Termostato
    Bagno"` (`KeyError: 'nome'`): l'unico anello tolto, e il nome non
    arriva piu' in fondo.

    Il giorno e' il 24 agosto 2026 a Roma (mezzanotte locale = 22:00 UTC del
    23), la stessa convenzione di `tests/test_mind_facts.py`.
    """
    from hiris.app.mind.facts import aggregate_day

    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        osservatore = Watcher(archivio, now=lambda: 1787580000.0)

        # L'evento COSI' COME Home Assistant lo manda: `friendly_name` sta in
        # `attributes`, accanto a `device_class`, non in un campo suo.
        assert osservatore.watch_reading({
            "entity_id": "climate.bagno_1p_t_bagno_1p_t",
            "old_state": {"state": "off"},
            "new_state": {"state": "heat",
                          "attributes": {"friendly_name": "Termostato Bagno"},
                          "last_changed": "2026-08-24T13:30:00+02:00"},
        }) is True
        assert osservatore.watch_reading({
            "entity_id": "climate.bagno_1p_t_bagno_1p_t",
            "old_state": {"state": "heat"},
            "new_state": {"state": "off",
                          "attributes": {"friendly_name": "Termostato Bagno"},
                          "last_changed": "2026-08-24T15:05:00+02:00"},
        }) is True

        assert aggregate_day(store=archivio, day="2026-08-24",
                             timezone="Europe/Rome") == 1

        risposta = await handle_facts(
            _richiesta({"observations": archivio}, {"day": "2026-08-24"}))
        assert risposta.status == 200
        oggetto = _corpo(risposta)["facts"][0]

        # Il nome e' arrivato in fondo, e l'identificatore non si e' perso:
        # sono due cose diverse nella stessa riga.
        assert oggetto["corpo"]["nome"] == "Termostato Bagno"
        assert oggetto["protagonista"] == "climate.bagno_1p_t_bagno_1p_t"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_senza_nome_la_rotta_porta_l_id_e_NESSUN_nome_inventato(tmp_path):
    """L'altra meta' della regola, sulla stessa strada vera: quando Home
    Assistant non scrive `friendly_name` (nome composto vuoto, oppure uno
    stato scritto con `hass.states.async_set()`), l'oggetto arriva alla
    pagina **senza** la chiave `nome` -- non con un nome dedotto
    dall'`entity_id`, e non senza la riga.

    Mutazione ESEGUITA: scrivere in `Watcher.watch_reading`
    `friendly_name=_text_or_none(attributes.get("friendly_name")) or str(eid)`
    -- il test torna rosso su `assert "nome" not in oggetto["corpo"]`.
    """
    from hiris.app.mind.facts import aggregate_day

    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        osservatore = Watcher(archivio, now=lambda: 1787580000.0)
        assert osservatore.watch_reading({
            "entity_id": "climate.bagno_1p_t_bagno_1p_t",
            "old_state": {"state": "off"},
            "new_state": {"state": "heat", "attributes": {},
                          "last_changed": "2026-08-24T13:30:00+02:00"},
        }) is True

        aggregate_day(store=archivio, day="2026-08-24", timezone="Europe/Rome")
        risposta = await handle_facts(
            _richiesta({"observations": archivio}, {"day": "2026-08-24"}))
        oggetto = _corpo(risposta)["facts"][0]

        assert "nome" not in oggetto["corpo"]
        assert oggetto["protagonista"] == "climate.bagno_1p_t_bagno_1p_t"
        # La riga esiste comunque: non si tace un fatto perche' manca il nome.
        assert oggetto["genere"] == "funzionamento"
    finally:
        archivio.close()
