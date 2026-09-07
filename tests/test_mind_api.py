"""Le due rotte della pagina dell'osservatore."""
import pytest

from hiris.app.api.handlers_mind import handle_facts, handle_watching
from hiris.app.home_space.ha_vocabulary import UNAVAILABLE_LABEL
from hiris.app.home_space.store import HomeSpaceStore
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.state_translations import StateTranslations
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
    # Dal 07/09/2026 (fetta «lo stato») l'involucro ha una SECONDA chiave,
    # `traduzioni`, e non e' un di piu': dice se le traduzioni degli stati si
    # sono potute leggere. L'insieme si asserisce ESATTO apposta -- una terza
    # chiave aggiunta senza pensarci la fa vedere qui, che e' il motivo per
    # cui questa forma e' scritta per nome invece che con un `in`.
    assert set(_corpo(r)) == {"facts", "traduzioni"}


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


# ---------------------------------------------------------------------------
# Lo stato reso (fetta «lo stato», 07/09/2026). Il grezzo resta nell'archivio,
# la resa nasce QUI, al confine -- e i due silenzi («non ho potuto leggere le
# traduzioni» e «questo stato non ha traduzione») non producono la stessa
# risposta.
# ---------------------------------------------------------------------------

# Le chiavi sono quelle MISURATE sulla casa vera il 07/09/2026
# (`frontend/get_translations`, `language: "it"`, `category:
# "entity_component"`), non plausibili.
_RISORSE = {
    "component.climate.entity_component._.state.heat": "Riscaldamento",
    "component.person.entity_component._.state.not_home": "Fuori casa",
    "component.binary_sensor.entity_component.smoke.state.on": "Rilevato",
    "component.binary_sensor.entity_component._.state.on": "Acceso",
}


class _FinteTraduzioni:
    """La cache, con lo stesso contratto della vera: un esito ETICHETTATO."""

    def __init__(self, esito):
        self.esito = esito
        self.chiesto = None

    async def read(self, *, ha_version, language):
        self.chiesto = {"versione_ha": ha_version, "lingua": language}
        return self.esito


class _FintaAnagrafe:
    def __init__(self, frame):
        self._frame = frame

    def reference_frame(self):
        return self._frame


class _ClientCheNonRisponde:
    async def get_translations(self, language, category="entity_component"):
        raise AssertionError("senza lingua non si deve chiedere niente a Home Assistant")


class _ArchivioConOggetto:
    def __init__(self, corpo, protagonista="climate.bagno_1p_t"):
        self._corpo = corpo
        self._protagonista = protagonista

    def facts(self, *, day=None, limit=200):
        return [{"id": 1, "giorno": "2026-08-24", "genere": "funzionamento",
                 "protagonista": self._protagonista, "inizio_ts": 1.0,
                 "fine_ts": 2.0, "corpo": dict(self._corpo)}]


assert_stessa_firma(StateTranslations.read, _FinteTraduzioni.read, nome="read")
assert_stessa_firma(HomeSpaceStore.reference_frame, _FintaAnagrafe.reference_frame,
                    nome="reference_frame")
assert_stessa_firma(ObservationsStore.facts, _ArchivioConOggetto.facts, nome="facts")


def _app_for_facts(corpo, esito, protagonista="climate.bagno_1p_t", frame=None):
    return {"observations": _ArchivioConOggetto(corpo, protagonista),
            "state_translations": _FinteTraduzioni(esito),
            "home_space_store": _FintaAnagrafe(
                frame if frame is not None else {"versione_ha": "2026.9.1", "lingua": "it"})}


_LETTE = {"lette": True, "lingua": "it", "risorse": _RISORSE}


@pytest.mark.asyncio
async def test_lo_stato_reso_sta_ACCANTO_al_grezzo_mai_sopra():
    """La stessa disciplina di `nome`/`nome_dedotto` (`memory/resolver.py`):
    il grezzo e' il fatto (`facts.py` ci ragiona sopra), la resa e' una chiave
    in piu'.

    Mutazione ESEGUITA: in `_with_rendered_states` scrivere
    `{**body, "stato": translated}` al posto di `"stato_reso"` -- il test
    torna rosso su `assert corpo["stato"] == "heat"`
    (`assert 'Riscaldamento' == 'heat'`).
    """
    r = await handle_facts(_richiesta(_app_for_facts({"stato": "heat"}, _LETTE)))
    corpo = _corpo(r)["facts"][0]["corpo"]
    assert corpo["stato"] == "heat"
    assert corpo["stato_reso"] == "Riscaldamento"


@pytest.mark.asyncio
async def test_uno_stato_SENZA_traduzione_esce_grezzo_e_la_riga_non_mente():
    """`generating_consuming_from_network` e' uno dei 73 valori testuali
    misurati sulla casa: HA stesso lo mostra grezzo. La chiave della resa
    TACE -- non copia il grezzo, che direbbe «tradotto» di uno stato che
    tradotto non e'.

    Mutazione ESEGUITA: `"stato_reso": translated or body.get("stato")` in
    `_with_rendered_states` (piu' il ramo che salta i `None`) -- il test torna
    rosso su `assert "stato_reso" not in corpo`.
    """
    r = await handle_facts(_richiesta(
        _app_for_facts({"stato": "generating_consuming_from_network"}, _LETTE)))
    corpo = _corpo(r)["facts"][0]["corpo"]
    assert corpo["stato"] == "generating_consuming_from_network"
    assert "stato_reso" not in corpo
    # E la rotta dichiara di AVER letto: e' l'altra meta' della distinzione.
    assert _corpo(r)["traduzioni"]["lette"] is True


@pytest.mark.asyncio
async def test_traduzioni_NON_LETTE_e_stato_SENZA_traduzione_non_dicono_la_stessa_cosa():
    """Il difetto piu' ricorrente di questa codebase: due fatti diversi
    appiattiti su una risposta sola. Qui le due risposte differiscono, e la
    differenza sta dove la produce chi la conosce -- non in un confronto di
    stringhe a valle.

    Mutazione ESEGUITA: in `handle_facts` tornare `{"facts": facts}` senza la
    chiave `traduzioni` -- il test torna rosso su
    `assert unread["traduzioni"]["lette"] is False` (`KeyError:
    'traduzioni'`).
    """
    untranslated = _corpo(await handle_facts(_richiesta(
        _app_for_facts({"stato": "digitalfirst"}, _LETTE))))
    unread = _corpo(await handle_facts(_richiesta(_app_for_facts(
        {"stato": "heat"}, {"lette": False, "motivo": "Home Assistant non ha risposto"}))))

    # Stesso esito visibile sulla riga (nessuna resa), due VERITA' diverse.
    assert "stato_reso" not in untranslated["facts"][0]["corpo"]
    assert "stato_reso" not in unread["facts"][0]["corpo"]
    assert untranslated["traduzioni"] == {"lette": True, "lingua": "it"}
    assert unread["traduzioni"]["lette"] is False
    assert unread["traduzioni"]["motivo"] == "Home Assistant non ha risposto"


@pytest.mark.asyncio
async def test_la_tabella_delle_traduzioni_NON_viaggia_nella_risposta():
    """801 chiavi, 65 KB, a ogni lettura della pagina. Nella risposta va
    l'ESITO, non la tabella: la tabella resta in cache dentro l'add-on.

    Mutazione ESEGUITA: `declared = report` in `handle_facts` -- il test
    torna rosso su `assert "risorse" not in _corpo(r)["traduzioni"]`.
    """
    r = await handle_facts(_richiesta(_app_for_facts({"stato": "heat"}, _LETTE)))
    assert "risorse" not in _corpo(r)["traduzioni"]


@pytest.mark.asyncio
async def test_unavailable_prende_l_etichetta_nostra_anche_a_traduzioni_non_lette():
    """Le nostre due etichette non vengono da Home Assistant
    (`helpers/translation.py:469-470`): non c'e' ragione che un guasto di rete
    le porti via. Un buco al loro posto sarebbe la cosa peggiore -- lo stato
    che dice «non lo so» reso come un vuoto.

    Mutazione ESEGUITA: in `_with_rendered_states`, saltare la resa quando la
    tabella manca (`if not isinstance(resources, dict): return facts`) -- il
    test torna rosso su `assert corpo["stato_reso"] == UNAVAILABLE_LABEL`
    (`KeyError: 'stato_reso'`).
    """
    r = await handle_facts(_richiesta(_app_for_facts(
        {"stato": "unavailable"}, {"lette": False, "motivo": "rete giu'"})))
    corpo = _corpo(r)["facts"][0]["corpo"]
    assert corpo["stato"] == "unavailable"
    assert corpo["stato_reso"] == UNAVAILABLE_LABEL


@pytest.mark.asyncio
async def test_una_condizione_di_sistema_non_passa_dal_vocabolario_degli_stati():
    """Il `corpo.stato` di un guasto (`aperto`, `setup_retry`) non e' uno
    stato di Home Assistant, e `automazione:automation.x` spaccato sul punto
    darebbe il dominio «automazione:automation», che non esiste su nessuna
    casa. Lo stesso confine, con le stesse quattro parole, e' gia' in
    `facts.py::genre_for`.

    Mutazione ESEGUITA: togliere il controllo su `_NOT_ENTITY_PREFIXES` da
    `_with_rendered_states` -- il test torna rosso su
    `assert "stato_reso" not in corpo`.
    """
    # Il soggetto e' un `automazione:` APPOSTA: e' l'unico dei quattro
    # prefissi che porta un punto dentro di se' (`automazione:automation.x`),
    # quindi l'unico che un controllo sul solo punto lascerebbe passare. Con
    # `integrazione:...` (nessun punto) questa prova resterebbe verde anche
    # senza il controllo sui prefissi: non potrebbe fallire.
    risorse = dict(_RISORSE)
    risorse["component.automazione:automation.entity_component._.state.error"] = "MAI"
    r = await handle_facts(_richiesta(_app_for_facts(
        {"stato": "error", "titolo": "Tapparelle la sera"},
        {"lette": True, "lingua": "it", "risorse": risorse},
        protagonista="automazione:automation.tapparelle_sera")))
    corpo = _corpo(r)["facts"][0]["corpo"]
    assert corpo["stato"] == "error"
    assert "stato_reso" not in corpo


@pytest.mark.asyncio
async def test_lingua_e_versione_arrivano_dall_anagrafe_non_da_una_seconda_lettura():
    """`versione_ha` e `lingua` sono le due cose che HIRIS distilla GIA' da
    `Config.as_dict()` (`home_space.topology.reference_frame`). Chiederle di
    nuovo a Home Assistant a ogni pagina sarebbe una seconda idea della stessa
    cosa, e una lettura di rete per pagina.

    Mutazione ESEGUITA: `cache.read(ha_version=None, language=None)` in
    `_translations_report` -- il test torna rosso su
    `assert ... == {"versione_ha": "2026.9.1", "lingua": "it"}`.
    """
    app = _app_for_facts({"stato": "heat"}, _LETTE)
    await handle_facts(_richiesta(app))
    assert app["state_translations"].chiesto == {"versione_ha": "2026.9.1", "lingua": "it"}


@pytest.mark.asyncio
async def test_senza_la_cache_delle_traduzioni_la_rotta_risponde_lo_stesso_e_lo_DICE():
    """Gli episodi sono il fatto; la resa e' un di piu'. Una rotta che
    fallisse per una traduzione mancante toglierebbe al proprietario cio' che
    e' venuto a leggere."""
    r = await handle_facts(_richiesta({"observations": _ArchivioConOggetto({"stato": "heat"})}))
    assert r.status == 200
    assert _corpo(r)["facts"][0]["corpo"]["stato"] == "heat"
    assert _corpo(r)["traduzioni"]["lette"] is False
    assert _corpo(r)["traduzioni"]["motivo"]


@pytest.mark.asyncio
async def test_senza_il_sistema_di_riferimento_non_si_indovina_una_lingua():
    """L'anagrafe non ha ancora letto la casa: la lingua non si sa, e non si
    sceglie noi. La pagina lo dice invece di rendere in una lingua che il
    proprietario non ha chiesto. Qui la cache e' quella VERA, con un client
    che solleva se qualcuno prova a chiedere."""
    app = _app_for_facts({"stato": "heat"}, _LETTE, frame={})
    app["state_translations"] = StateTranslations(_ClientCheNonRisponde())
    r = await handle_facts(_richiesta(app))
    assert _corpo(r)["traduzioni"]["lette"] is False
    assert "lingua" in _corpo(r)["traduzioni"]["motivo"]


# ---------------------------------------------------------------------------
# La strada vera, per intero, per lo STATO: l'evento di Home Assistant ->
# `Watcher` -> l'archivio SQLite -> `aggregate_day` -> `GET /api/mind/facts`
# -> il JSON che il frontend legge. Nessuna finta in mezzo tranne la tabella
# delle traduzioni, che e' l'unica cosa che vive fuori da HIRIS.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lo_stato_percorre_la_strada_vera_dall_evento_al_json(tmp_path):
    """`heat` entra come evento di Home Assistant, attraversa l'archivio vero
    e l'aggregazione vera, ed esce dal JSON come «Riscaldamento» -- col grezzo
    ancora accanto.

    Mutazione ESEGUITA: togliere la resa da `handle_facts`
    (`facts = store.facts(day=day)`) -- il test torna rosso su
    `assert corpo["stato_reso"] == "Riscaldamento"` (`KeyError: 'stato_reso'`).
    """
    from hiris.app.mind.facts import aggregate_day

    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        osservatore = Watcher(archivio, now=lambda: 1787580000.0)
        assert osservatore.watch_reading({
            "entity_id": "climate.bagno_1p_t_bagno_1p_t",
            "old_state": {"state": "off"},
            "new_state": {"state": "heat",
                          "attributes": {"friendly_name": "Termostato Bagno"},
                          "last_changed": "2026-08-24T13:30:00+02:00"},
        }) is True
        assert aggregate_day(store=archivio, day="2026-08-24",
                             timezone="Europe/Rome") == 1

        app = {"observations": archivio,
               "state_translations": _FinteTraduzioni(_LETTE),
               "home_space_store": _FintaAnagrafe(
                   {"versione_ha": "2026.9.1", "lingua": "it"})}
        risposta = await handle_facts(_richiesta(app, {"day": "2026-08-24"}))
        corpo = _corpo(risposta)["facts"][0]["corpo"]

        assert corpo["stato"] == "heat"
        assert corpo["stato_reso"] == "Riscaldamento"
        # Il nome della fetta precedente non si e' perso per strada.
        assert corpo["nome"] == "Termostato Bagno"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_sulla_strada_vera_la_CLASSE_sceglie_la_resa_giusta(tmp_path):
    """Il secondo gradino, dall'evento al JSON. Un rilevatore di fumo scattato
    si legge «Rilevato» perche' l'evento portava `device_class: smoke` e la
    classe e' arrivata fino al corpo dell'oggetto; senza di lei l'unico
    gradino raggiungibile direbbe «Acceso» (misurato dal vivo il 07/09/2026).

    Mutazione ESEGUITA: togliere `"classe": r.get("device_class")`
    dall'apertura del ramo `sicurezza` in `mind/facts.py` -- il test torna
    rosso su `assert oggetto["corpo"]["classe"] == "smoke"` (`KeyError`).
    """
    from hiris.app.mind.facts import aggregate_day

    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        osservatore = Watcher(archivio, now=lambda: 1787580000.0)
        assert osservatore.watch_reading({
            "entity_id": "binary_sensor.fumo_cucina",
            "old_state": {"state": "off"},
            "new_state": {"state": "on",
                          "attributes": {"device_class": "smoke",
                                         "friendly_name": "Fumo Cucina"},
                          "last_changed": "2026-08-24T13:30:00+02:00"},
        }) is True
        assert aggregate_day(store=archivio, day="2026-08-24",
                             timezone="Europe/Rome") == 1

        app = {"observations": archivio,
               "state_translations": _FinteTraduzioni(_LETTE),
               "home_space_store": _FintaAnagrafe(
                   {"versione_ha": "2026.9.1", "lingua": "it"})}
        risposta = await handle_facts(_richiesta(app, {"day": "2026-08-24"}))
        oggetto = _corpo(risposta)["facts"][0]
        assert oggetto["genere"] == "sicurezza"
        assert oggetto["corpo"]["classe"] == "smoke"
        assert oggetto["corpo"]["stato_reso"] == "Rilevato"
    finally:
        archivio.close()
