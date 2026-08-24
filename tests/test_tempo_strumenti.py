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
from hiris.app.schedulatore.turno import SOLA_LETTURA, strumenti_promessa


def test_il_catalogo_porta_tredici_strumenti():
    assert len(STRUMENTI_CONOSCENZA) == 13
    nomi = {d["name"] for d in STRUMENTI_CONOSCENZA}
    assert {"andamento", "accaduto"} <= nomi


def test_ogni_strumento_del_catalogo_ha_un_gestore():
    """Il difetto che questo test chiude: uno strumento nel catalogo arriva al
    modello, e poi si sente rispondere «non e' fra quelli disponibili» -- una
    incoerenza che il modello non puo' ne' capire ne' aggirare."""
    d = DispatcherStrumenti(None, None)
    sorgente = inspect.getsource(DispatcherStrumenti.dispatch)
    for definizione in STRUMENTI_CONOSCENZA:
        assert f'"{definizione["name"]}": self._' in sorgente


def test_i_due_lettori_entrano_nel_turno_delle_promesse():
    """`andamento` e `accaduto` LEGGONO e basta: escluderli sarebbe la scelta
    opposta a quella presa per `costruisci`, e per la ragione opposta."""
    assert "andamento" in SOLA_LETTURA and "accaduto" in SOLA_LETTURA
    nomi = {d["name"] for d in strumenti_promessa()}
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
