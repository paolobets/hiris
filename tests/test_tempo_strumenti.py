"""I due strumenti del tempo arrivano davvero al modello.

Meta' di questo file non prova il comportamento ma il CABLAGGIO -- ed e'
deliberato: la fetta «costruire» ha scoperto che uno strumento perfetto e non
cablato e' esattamente cio' che il prodotto non puo' distinguere da uno
strumento assente.
"""
import inspect

import pytest

from hiris.app.api import handlers_chat
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherStrumenti
from hiris.app.schedulatore.turno import SOLA_LETTURA, tools_promise


def test_il_catalogo_porta_tredici_strumenti():
    assert len(STRUMENTI_CONOSCENZA) == 13
    nomi = {d["name"] for d in STRUMENTI_CONOSCENZA}
    assert {"andamento", "accaduto"} <= nomi


# La convenzione di nomenclatura `nome -> self._nome` regge su dodici dei
# tredici strumenti: `promesse` e' servito da `_promesse_elenco`, non da
# `_promesse` (quell'attributo e' gia' l'archivio, vedi il commento nel
# `__init__` del dispatcher). L'eccezione e' dichiarata QUI, non nascosta
# saltando la verifica per quel nome.
_GESTORE_ATTESO = {"promesse": "_promesse_elenco"}


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
    for definizione in STRUMENTI_CONOSCENZA:
        nome = definizione["name"]
        attributo = _GESTORE_ATTESO.get(nome, f"_{nome}")
        d = DispatcherStrumenti(object(), object(), ha=object(), porta=object(),
                                 promesse=object(), officina=object())
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
    assert "andamento" in SOLA_LETTURA and "accaduto" in SOLA_LETTURA
    nomi = {d["name"] for d in tools_promise()}
    assert {"andamento", "accaduto"} <= nomi


def test_il_dispatcher_riceve_la_cronaca_dall_app():
    """Senza questa riga `accaduto` risponderebbe sempre senza attribuzione:
    un dato che c'e' e che nessuno puo' chiedere -- la fondamenta 4 al
    contrario, lo stesso difetto gia' pagato da `legami`."""
    sorgente = inspect.getsource(handlers_chat.costruisci_dispatcher_strumenti)
    assert 'cronaca=app.get("cronaca")' in sorgente


@pytest.mark.asyncio
async def test_senza_canale_ha_i_due_strumenti_dichiarano_invece_di_sollevare():
    d = DispatcherStrumenti(None, None)
    for nome in ("andamento", "accaduto"):
        esito = await d.dispatch(nome, {"entita": "sensor.x", "ore": 24})
        assert "errore" in esito


@pytest.mark.asyncio
async def test_andamento_pretende_un_entita():
    d = DispatcherStrumenti(None, None, ha=object())
    esito = await d.dispatch("andamento", {"ore": 24})
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

    async def _finto_andamento(**kwargs):
        visti.update(kwargs)
        return {"entita": kwargs["entita"], "grana": "dettaglio", "punti": []}

    import hiris.app.casa.strumenti as modulo
    originale = modulo.tempo.andamento
    modulo.tempo.andamento = _finto_andamento
    try:
        d = DispatcherStrumenti(None, None, cache=_Cache(), ha=object())
        await d.dispatch("andamento", {"entita": "sensor.camera", "ore": 6})
    finally:
        modulo.tempo.andamento = originale
    assert visti["unita"] == "°C"
    assert visti["ha_statistiche"] is True


@pytest.mark.asyncio
async def test_accaduto_passa_la_cronaca_del_dispatcher_a_tempo_accaduto():
    """Il gemello del test sopra, per `accaduto`. Senza questo test la prova
    mentale che conta e' negativa: se `cronaca=self._cronaca` diventasse
    `cronaca=None` nel gestore, NESSUN test della suite arrossirebbe -- ne'
    questi sette, ne' `test_tempo_accaduto.py`, che prova `tempo.accaduto` e
    non il dispatcher. L'effetto sarebbe silenzioso: la risposta continua ad
    arrivare, solo senza mai dire «l'ho fatto io» -- l'attribuzione sparisce
    e nessuno se ne accorge."""
    visti = {}
    cronaca_vera = object()  # un oggetto RICONOSCIBILE: deve arrivare esso
                              # stesso, non un sostituto costruito qui.

    async def _finto_accaduto(**kwargs):
        visti.update(kwargs)
        return {"voci": [], "troncato": False, "ore": kwargs["ore"], "nota": None}

    import hiris.app.casa.strumenti as modulo
    originale = modulo.tempo.accaduto
    modulo.tempo.accaduto = _finto_accaduto
    try:
        d = DispatcherStrumenti(None, None, ha=object(), cronaca=cronaca_vera)
        await d.dispatch("accaduto", {"ore": 6})
    finally:
        modulo.tempo.accaduto = originale
    assert visti["cronaca"] is cronaca_vera


@pytest.mark.asyncio
async def test_measurement_angle_resta_sul_dettaglio_oltre_la_soglia():
    """F4 (onda finale): `measurement_angle` e' un `state_class` vero e
    proprio ma NON produce statistiche (spec S1). Il cablaggio ingenuo
    (`bool(state_class)`) manderebbe una banderuola oltre le 24 ore sul ramo
    statistiche, cioe' su un elenco vuoto che direbbe «non e' mai cambiata»
    -- mentre il dettaglio, la superficie giusta per lei, esiste. Qui
    `tempo.andamento` gira DAVVERO (non e' fintato): se il cablaggio tornasse
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

        async def storico(self, entita, da_iso, a_iso):
            self.chiamate.append("storico")
            return {"serie": {entita[0]: [
                {"quando": "2026-08-24T08:00:00+02:00", "valore": "180"}]},
                "troncato": False}

        async def statistiche(self, identificatori, periodo, giorni):
            self.chiamate.append("statistiche")
            return {"serie": {}}

    ha = _HA()
    d = DispatcherStrumenti(None, None, cache=_Cache(), ha=ha)
    esito = await d.dispatch(
        "andamento", {"entita": "sensor.vento_direzione", "ore": 48})
    assert esito["grana"] == "dettaglio"
    assert ha.chiamate == ["storico"]
