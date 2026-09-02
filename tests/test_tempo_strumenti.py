"""I due strumenti del tempo arrivano davvero al modello.

Meta' di questo file non prova il comportamento ma il CABLAGGIO -- ed e'
deliberato: la fetta «costruire» ha scoperto che uno strumento perfetto e non
cablato e' esattamente cio' che il prodotto non puo' distinguere da uno
strumento assente.
"""
import inspect

import pytest

from hiris.app.api import handlers_chat
from hiris.app.casa.strumenti import KNOWLEDGE_TOOLS, ToolDispatcher
from hiris.app.proxy.ha_client import HAClient
from hiris.app.schedulatore.turno import SOLA_LETTURA, promise_tools
from tests._contratti import assert_stessa_firma


def test_il_catalogo_porta_tredici_strumenti():
    assert len(KNOWLEDGE_TOOLS) == 13
    nomi = {d["name"] for d in KNOWLEDGE_TOOLS}
    assert {"trend", "logbook"} <= nomi


# La convenzione di nomenclatura `nome -> self._nome` regge su dodici dei
# tredici strumenti: `promesse` e' servito da `_promesse_elenco`, non da
# `_promesse` (quell'attributo e' gia' l'archivio, vedi il commento nel
# `__init__` del dispatcher). L'eccezione e' dichiarata QUI, non nascosta
# saltando la verifica per quel nome.
_GESTORE_ATTESO = {
    "search": "_search", "view": "_view", "related": "_related",
    "remember": "_remember", "fetch": "_recall", "execute": "_execute",
    "promise": "_promise", "agenda": "_list_agenda", "cancel": "_cancel",
    "propose": "_propose", "confirm": "_confirm", "trend": "_trend",
    "logbook": "_happened",
}


@pytest.mark.asyncio
async def test_ogni_strumento_del_catalogo_ha_il_proprio_gestore():
    """Il difetto che questo test chiude: uno strumento nel catalogo arriva al
    modello, e poi si sente rispondere «non e' fra quelli disponibili» (nessun
    gestore per quel nome) OPPURE -- refuso di copia-incolla fra due nomi
    adiacenti, es. `"accaduto": self._andamento` -- viene servito dal gestore
    di un ALTRO strumento senza che nessuno se ne accorga: in entrambi i casi
    il modello non puo' ne' capire ne' aggirare l'incoerenza.

    Una ricerca di sottostringa (`f'"{nome}": self._' in sorgente`) non
    coglie il secondo caso: la sottostringa c'e' comunque. Qui si chiama
    DAVVERO `dispatch(nome, ...)`, con il gestore atteso rimpiazzato da un
    finto che restituisce un marcatore UNICO per quel nome: se la risposta non
    e' quel marcatore, o `dispatch` ha chiamato un gestore diverso, o non ne
    ha chiamato nessuno."""
    for definizione in KNOWLEDGE_TOOLS:
        nome = definizione["name"]
        attributo = _GESTORE_ATTESO.get(nome, f"_{nome}")
        d = ToolDispatcher(object(), object(), ha=object(), actuator=object(),
                                 agenda=object(), workshop=object())
        assert hasattr(d, attributo), (
            f"«{nome}» dovrebbe essere servito da `self.{attributo}`, che non "
            "esiste sul dispatcher")
        marcatore = {"marcato": nome}
        setattr(d, attributo, lambda argomenti, _m=marcatore: _m)
        esito = await d.dispatch(nome, {})
        assert esito == marcatore, (
            f"«{nome}» non ha chiamato `self.{attributo}`: il dispatcher lo "
            "lega a un gestore diverso da quello atteso")


def test_i_due_lettori_entrano_nel_turno_delle_promesse():
    """`andamento` e `accaduto` LEGGONO e basta: escluderli sarebbe la scelta
    opposta a quella presa per `costruisci`, e per la ragione opposta."""
    assert "trend" in SOLA_LETTURA and "logbook" in SOLA_LETTURA
    nomi = {d["name"] for d in promise_tools()}
    assert {"trend", "logbook"} <= nomi


def test_il_dispatcher_riceve_la_cronaca_dall_app():
    """Senza questa riga `accaduto` risponderebbe sempre senza attribuzione:
    un dato che c'e' e che nessuno puo' chiedere -- la fondamenta 4 al
    contrario, lo stesso difetto gia' pagato da `legami`."""
    sorgente = inspect.getsource(handlers_chat.create_tool_dispatcher)
    assert 'journal=app.get("cronaca")' in sorgente


@pytest.mark.asyncio
async def test_senza_canale_ha_i_due_strumenti_dichiarano_invece_di_sollevare():
    d = ToolDispatcher(None, None)
    for nome in ("trend", "logbook"):
        esito = await d.dispatch(nome, {"entita": "sensor.x", "ore": 24})
        assert "errore" in esito


@pytest.mark.asyncio
async def test_andamento_pretende_un_entita():
    d = ToolDispatcher(None, None, ha=object())
    esito = await d.dispatch("trend", {"ore": 24})
    assert "errore" in esito and "entita" in esito["errore"]


@pytest.mark.asyncio
async def test_andamento_passa_unita_e_state_class_letti_dallo_specchio():
    """La scelta della superficie dipende da `state_class`, e l'unita' e' cio'
    che rende leggibile un numero (fondamenta 1). Entrambi vivono gia' nello
    specchio: chiederli al modello sarebbe chiedergli di sapere cose che
    abbiamo noi."""
    visti = {}

    class _Cache:
        loaded = True

        def all_states(self):
            return [{"id": "sensor.camera", "state": "21.0", "unit": "°C",
                     "name": "Camera", "device_class": "temperature",
                     "state_class": "measurement", "domain": "sensor"}]

    async def _finto_trend(**kwargs):
        visti.update(kwargs)
        return {"entita": kwargs["entity"], "grana": "dettaglio", "punti": []}

    import hiris.app.casa.strumenti as modulo
    originale = modulo.tempo.trend
    modulo.tempo.trend = _finto_trend
    try:
        d = ToolDispatcher(None, None, cache=_Cache(), ha=object())
        await d.dispatch("trend", {"entita": "sensor.camera", "ore": 6})
    finally:
        modulo.tempo.trend = originale
    assert visti["unit"] == "°C"
    assert visti["has_statistics"] is True


@pytest.mark.asyncio
async def test_accaduto_passa_la_cronaca_del_dispatcher_a_tempo_accaduto():
    """Il gemello del test sopra, per `accaduto`. Senza questo test la prova
    mentale che conta e' negativa: se `journal=self._cronaca` diventasse
    `journal=None` nel gestore, NESSUN test della suite arrossirebbe -- ne'
    questi sette, ne' `test_tempo_accaduto.py`, che prova `tempo.logbook` e
    non il dispatcher. L'effetto sarebbe silenzioso: la risposta continua ad
    arrivare, solo senza mai dire «l'ho fatto io» -- l'attribuzione sparisce
    e nessuno se ne accorge."""
    visti = {}
    cronaca_vera = object()  # un oggetto RICONOSCIBILE: deve arrivare esso
                              # stesso, non un sostituto costruito qui.

    async def _finto_logbook(**kwargs):
        visti.update(kwargs)
        return {"voci": [], "troncato": False, "ore": kwargs["hours"], "nota": None}

    import hiris.app.casa.strumenti as modulo
    originale = modulo.tempo.logbook
    modulo.tempo.logbook = _finto_logbook
    try:
        d = ToolDispatcher(None, None, ha=object(), journal=cronaca_vera)
        await d.dispatch("logbook", {"ore": 6})
    finally:
        modulo.tempo.logbook = originale
    assert visti["journal"] is cronaca_vera


@pytest.mark.asyncio
async def test_measurement_angle_resta_sul_dettaglio_oltre_la_soglia():
    """F4 (onda finale): `measurement_angle` e' un `state_class` vero e
    proprio ma NON produce statistiche (spec S1). Il cablaggio ingenuo
    (`bool(state_class)`) manderebbe una banderuola oltre le 24 ore sul ramo
    statistiche, cioe' su un elenco vuoto che direbbe «non e' mai cambiata»
    -- mentre il dettaglio, la superficie giusta per lei, esiste. Qui
    `tempo.trend` gira DAVVERO (non e' fintato): se il cablaggio tornasse
    a `bool(...)`, `grana` sarebbe «oraria» e la finta HA registrerebbe
    «statistiche», non «storico»."""
    class _Cache:
        loaded = True

        def all_states(self):
            return [{"id": "sensor.vento_direzione", "state": "180", "unit": "°",
                     "name": "Direzione vento", "device_class": None,
                     "state_class": "measurement_angle", "domain": "sensor"}]

    class _HA:
        def __init__(self):
            self.chiamate = []

        async def history(self, entities, from_iso, to_iso):
            self.chiamate.append("storico")
            return {"serie": {entities[0]: [
                {"quando": "2026-08-24T08:00:00+02:00", "valore": "180"}]},
                "troncato": False}

        async def statistics(self, identifiers, period, days):
            self.chiamate.append("statistiche")
            return {"serie": {}}

    # `HAClient` non e' convertito da questa fetta: se `.storico`/
    # `.statistiche` cambiassero firma (o una finta futura li seguisse a
    # ruota rinominandosi come il chiamante, gia' successo una volta in
    # questa fetta -- review Task 8), questa riga cade prima che la
    # produzione veda un `AttributeError`.
    assert_stessa_firma(HAClient.history, _HA.history, nome="storico")
    assert_stessa_firma(HAClient.statistics, _HA.statistics, nome="statistiche")

    ha = _HA()
    d = ToolDispatcher(None, None, cache=_Cache(), ha=ha)
    esito = await d.dispatch(
        "trend", {"entita": "sensor.vento_direzione", "ore": 48})
    assert esito["grana"] == "dettaglio"
    assert ha.chiamate == ["storico"]
