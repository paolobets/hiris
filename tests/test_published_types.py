"""Cosa questa casa PUBBLICA adesso: le funzioni pure che il censore e lo
script che lo alimenta chiamano davvero, piu' `StateTranslations` (la cache
che rende uno stato) e il registro dei servizi (i bit di capacita').

Le chiavi e i numeri di questo file non sono plausibili: sono stati **letti
dalla casa vera** l'08/09/2026 (Home Assistant `2026.9.1`, lingua `it`) --
`frontend/get_translations` con `category: "entity_component"` (801 chiavi, 53
domini, 4 valori di `state_class`) e `GET /api/services` (84 domini di
servizio, 16 accendibili, i valori combinati `cover: 3` e
`media_player: 16385`). La suite pero' gira **senza la casa**: qui dentro non
c’e' nessuna chiamata di rete, solo cio' che quella lettura ha misurato.

**R6 (revisione del tratto v3.23.0..HEAD, 08/09/2026)**: questo file provava
anche `PublishedTypes` e `StateTranslations.published()`, un wrapper con gli
stessi tre silenzi ma senza nessun chiamante di produzione -- il censore legge
l'istantaneo JSON, lo script chiama le funzioni pure sotto direttamente.
Cancellati insieme al codice che provavano (vedi `proxy/state_translations.py`
e `action/registry.py::capability_bits_of`, anch'essa cancellata per lo stesso
motivo).
"""
import asyncio

import pytest

from hiris.app.action.registry import (
    ServiceRegistry,
    capability_bits,
    single_bits,
    switchable_domains,
)
from hiris.app.proxy.state_translations import (
    SILENCE_UNREACHABLE,
    SILENCES,
    StateTranslations,
    published_device_classes,
    published_domains,
    published_state_classes,
    published_states,
)

# Le chiavi sono MISURATE, non inventate: `sensor` pubblica 62 classi e nessuna
# enumerazione di stati per classe, `binary_sensor` pubblica le classi E gli
# stati, `light` non pubblica nessuna classe. Sono i tre casi che le tre
# risposte diverse devono distinguere.
RISORSE = {
    "component.light.entity_component._.state.on": "Acceso",
    "component.light.entity_component._.state.off": "Spento",
    "component.binary_sensor.entity_component._.state.on": "Acceso",
    "component.binary_sensor.entity_component._.state.off": "Spento",
    "component.binary_sensor.entity_component.smoke.name": "Fumo",
    "component.binary_sensor.entity_component.smoke.state.on": "Rilevato",
    "component.binary_sensor.entity_component.smoke.state.off": "Non rilevato",
    "component.sensor.entity_component.energy.name": "Energia",
    "component.sensor.entity_component._.state_attributes.state_class.state.measurement":
        "Misura",
    "component.sensor.entity_component._.state_attributes.state_class.state."
    "measurement_angle": "Misura angolare",
    "component.sensor.entity_component._.state_attributes.state_class.state.total":
        "Totale",
    "component.sensor.entity_component._.state_attributes.state_class.state."
    "total_increasing": "Totale crescente",
}


class _ClienteFinto:
    """Un client di Home Assistant che risponde cio' che gli si dice, e conta
    le volte in cui gli e' stato chiesto. Nessuna rete."""

    def __init__(self, risposte) -> None:
        self.risposte = list(risposte)
        self.chiamate = 0

    async def get_translations(self, language, category="entity_component"):
        self.chiamate += 1
        if not self.risposte:
            return {"errore": "Home Assistant non ha risposto"}
        return self.risposte.pop(0)


class _RegistroFinto:
    """`/api/services` in forma di lista, come Home Assistant lo manda."""

    def __init__(self, righe) -> None:
        self.righe = righe

    async def get_services(self):
        return self.righe


def _registro(righe) -> ServiceRegistry:
    registro = ServiceRegistry()
    asyncio.run(registro.refresh(_RegistroFinto(righe)))
    return registro


# ---------------------------------------------------------------------------
# I TRE SILENZI -- e restano tre fino a chi legge
# ---------------------------------------------------------------------------

def test_le_etichette_dei_silenzi_sono_tre_e_tutte_diverse():
    """Un quarto silenzio nato di nascosto, o due che collassano nella stessa
    stringa, e' il modo in cui «perche' non lo so» torna a essere un'opinione
    di chi legge.

    Mutazione ESEGUITA: dare a `SILENCE_UNDEFINED` lo stesso testo di
    `SILENCE_ABSENT` in `proxy/state_translations.py` -- rosso su
    `len(set(SILENCES)) == 3`.
    """
    assert len(SILENCES) == 3
    assert len(set(SILENCES)) == 3


# ---------------------------------------------------------------------------
# LA PRUDENZA: un guasto non invalida la tabella buona di prima
# ---------------------------------------------------------------------------

def test_un_guasto_non_svuota_la_tabella_gia_letta():
    """A `(versione_ha, lingua)` invariate, una lettura fallita **non svuota**
    cio' che si ha. Una tabella che c'e' vale piu' di un vuoto dichiarato
    fresco -- la stessa scelta di `topology.rebuild()`.

    La sequenza e' quella vera: si legge bene la casa `2026.9.1`, Home
    Assistant si riavvia dicendosi `2026.9.2` e la lettura fallisce, poi
    torna a dirsi `2026.9.1` (un riavvio annullato, un proxy che ha risposto
    male una volta). La tabella buona dev'essere ancora li'.

    Mutazione ESEGUITA: in `StateTranslations.read`, aggiungere
    `self._resources = None` nel ramo del guasto (subito prima di
    `return {"lette": False, ...}`) -- la terza lettura torna
    `lette: False` e la prova arrossisce su `ancora["lette"] is True`.
    """
    cliente = _ClienteFinto([{"risorse": dict(RISORSE)}])
    cache = StateTranslations(cliente)
    buona = asyncio.run(cache.read(ha_version="2026.9.1", language="it"))
    assert buona["lette"] is True

    guasto = asyncio.run(cache.read(ha_version="2026.9.2", language="it"))
    assert guasto["lette"] is False

    ancora = asyncio.run(cache.read(ha_version="2026.9.1", language="it"))
    assert ancora["lette"] is True
    assert ancora["risorse"] == RISORSE
    # E non e' stata chiesta una seconda volta a Home Assistant: la coppia non
    # e' cambiata, quindi la tabella si serve dalla memoria.
    assert cliente.chiamate == 2


# ---------------------------------------------------------------------------
# LE QUATTRO MATERIE, distillate dalle stesse chiavi
# ---------------------------------------------------------------------------

def test_le_classi_si_leggono_dalle_chiavi_del_nome_non_da_quelle_di_stato():
    """`sensor` ha 62 classi e **nessuna** di esse enumera stati: sono misure.
    Una tabella costruita dalle chiavi `.state` ne perderebbe 62 su 62 senza
    dirlo.

    Mutazione ESEGUITA: in `published_device_classes`, cambiare
    `parts[4] != "name"` in `parts[4] != "state"` -- `sensor` sparisce dalle
    classi e la prova arrossisce.
    """
    classi = published_device_classes(RISORSE)
    assert classi["sensor"] == frozenset({"energy"})
    assert classi["binary_sensor"] == frozenset({"smoke"})
    assert "light" not in classi


def test_gli_stati_sono_indicizzati_per_TIPO_non_per_dominio():
    """La chiave e' quella del vocabolario dei tipi: un dominio, o una coppia.
    Il `_` di Home Assistant -- che significa «senza classe» -- diventa
    `None`, cosi' che nessun consumatore debba sapere che quel trattino basso
    non e' una classe di dispositivo.

    Mutazione ESEGUITA: in `published_states`, tenere `parts[3]` invece di
    tradurre `_` in `None` -- la chiave diventa `("light", "_")` e la prova
    arrossisce.
    """
    stati = published_states(RISORSE)
    assert stati[("light", None)] == frozenset({"on", "off"})
    assert stati[("binary_sensor", "smoke")] == frozenset({"on", "off"})
    assert ("light", "_") not in stati


def test_i_valori_di_state_class_sono_quattro_e_non_i_nostri_tre():
    """`measurement_angle` e' esattamente la voce che una lista scritta a mano
    non guadagna mai: e' nata in Home Assistant, e nessuno qui se n'era
    accorto.

    Mutazione ESEGUITA: in `published_state_classes`, confrontare `parts[5]`
    con `"unit_of_measurement"` invece che con `STATE_CLASS_ATTRIBUTE` --
    l'insieme torna vuoto e la prova arrossisce.
    """
    assert published_state_classes(RISORSE) == frozenset(
        {"measurement", "measurement_angle", "total", "total_increasing"})


def test_i_domini_sono_quelli_caricati_da_questa_casa():
    assert published_domains(RISORSE) == frozenset({"light", "binary_sensor", "sensor"})
    assert published_domains(None) == frozenset()


# ---------------------------------------------------------------------------
# IL REGISTRO DEI SERVIZI: i bit combinati si scompongono PRIMA del confronto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("combinato, atteso", [
    (3, {1, 2}),            # cover.toggle -> OPEN|CLOSE, misurato
    (16385, {1, 16384}),    # media_player.media_play_pause -> PAUSE|PLAY
    (48, {16, 32}),         # cover.toggle_tilt -> OPEN_TILT|CLOSE_TILT
    (384, {128, 256}),      # media_player.toggle -> TURN_ON|TURN_OFF
    (4, {4}),               # un bit solo resta se stesso
])
def test_i_valori_combinati_si_scompongono(combinato, atteso):
    """**La trappola misurata.** Il registro dei servizi porta valori
    COMBINATI, non singoli. Confrontarli tali e quali con una tabella di bit
    non trova niente e non fallisce: dice «questo dominio non ha capacita' che
    conosciamo» su un dominio che le ha tutte.

    Mutazione ESEGUITA: in `single_bits`, sostituire il corpo con
    `return frozenset({value})` -- rosso su ognuno dei quattro combinati.
    """
    assert single_bits(combinato) == frozenset(atteso)


def test_un_booleano_non_diventa_il_bit_uno():
    """`bool` e' una sottoclasse di `int`: la stessa guardia che
    `field_applies` e `topology.decoded_capabilities` hanno gia'.

    Mutazione ESEGUITA: togliere `and not isinstance(value, bool)` da
    `single_bits` -- `True` diventa `{1}` e la prova arrossisce.
    """
    assert single_bits(True) == frozenset()
    assert single_bits(False) == frozenset()
    assert single_bits(0) == frozenset()
    assert single_bits(-4) == frozenset()
    assert single_bits("3") == frozenset()


# `/api/services` come Home Assistant lo manda, ridotto ai casi misurati.
SERVIZI = [
    {"domain": "cover", "services": {
        "open_cover": {"target": {"entity": [{"domain": ["cover"],
                                              "supported_features": [1]}]}},
        "close_cover": {"target": {"entity": [{"domain": ["cover"],
                                               "supported_features": [2]}]}},
        # Il combinato vero: `3` = OPEN|CLOSE.
        "toggle": {"target": {"entity": [{"domain": ["cover"],
                                          "supported_features": [3]}]}},
    }},
    {"domain": "media_player", "services": {
        "media_play_pause": {"target": {"entity": [{"domain": ["media_player"],
                                                    "supported_features": [16385]}]}},
        "turn_on": {"target": {"entity": [{"domain": ["media_player"],
                                           "supported_features": [128]}]}},
        "turn_off": {"target": {"entity": [{"domain": ["media_player"],
                                            "supported_features": [256]}]}},
    }},
    # Un servizio di un'INTEGRAZIONE, che bersaglia un dominio diverso dal suo.
    {"domain": "reolink", "services": {
        "ptz_move": {"target": {"entity": [{"integration": "reolink",
                                            "domain": ["button"],
                                            "supported_features": [2]}]}},
    }},
    {"domain": "switch", "services": {"turn_on": {}, "turn_off": {}}},
    {"domain": "vacuum", "services": {"start": {}, "stop": {}}},
    # Il filtro sta su un CAMPO, non sul bersaglio: l'altra sede dei bit.
    {"domain": "light", "services": {
        "turn_on": {"target": {"entity": [{"domain": ["light"]}]},
                    "fields": {"transition": {"filter": {"supported_features": [32]}}}},
        "turn_off": {"target": {"entity": [{"domain": ["light"]}]}},
    }},
]


def test_i_bit_arrivano_scomposti_a_chi_li_confronta():
    """Il pezzo che chiude la trappola: **la scomposizione sta nella vista**,
    non in ogni chiamante. `cover` esce con `{1, 2}` e mai con `3`.

    Mutazione ESEGUITA: in `_bits_declared_by`, sostituire
    `bits |= single_bits(value)` con `bits.add(value)` -- `cover` esce
    `{1, 2, 3}` e la prova arrossisce.
    """
    registro = _registro(SERVIZI)
    per_dominio = capability_bits(registro)["valore"]
    assert per_dominio["cover"] == frozenset({1, 2})
    assert per_dominio["media_player"] == frozenset({1, 128, 256, 16384})
    assert 3 not in per_dominio["cover"]
    assert 16385 not in per_dominio["media_player"]


def test_i_bit_vanno_al_dominio_del_BERSAGLIO_non_a_quello_del_servizio():
    """`reolink.ptz_move` dichiara `domain: [button]`. Attribuirlo a `reolink`
    -- che non e' un dominio di entita' -- perderebbe l'unica capacita' che
    questa casa dichiara su `button`, in silenzio.

    Mutazione ESEGUITA: in `_capability_bits`, usare `service_domain` al posto
    di `_target_domains(detail)` -- `button` sparisce e `reolink` compare.
    """
    per_dominio = capability_bits(_registro(SERVIZI))["valore"]
    assert per_dominio["button"] == frozenset({2})
    assert "reolink" not in per_dominio


def test_anche_il_filtro_di_un_campo_porta_i_suoi_bit():
    """I bit stanno in DUE sedi -- il bersaglio del servizio e il filtro di un
    parametro -- e leggerne una sola perde `light` per intero.

    Mutazione ESEGUITA: togliere da `_bits_declared_by` il blocco che legge
    `fields` -- `light` sparisce dai domini con bit.
    """
    per_dominio = capability_bits(_registro(SERVIZI))["valore"]
    assert per_dominio["light"] == frozenset({32})


def test_un_registro_mai_letto_non_e_un_registro_senza_bit():
    """Lo stesso contratto della lettura delle traduzioni, sull'altra fonte:
    un registro assente e uno mai letto rispondono «non ho potuto chiedere»,
    non un dizionario vuoto -- sono due fatti diversi da un registro letto e
    senza bit (`{}` e' un esito lecito di `known`, misurato altrove).

    (R6, revisione del tratto v3.23.0..HEAD, 08/09/2026: questa prova
    copriva anche `capability_bits_of`, cancellata perche' senza chiamante di
    produzione -- vedi `registry.py` sopra `switchable_domains`. Il pezzo che
    resta, sul solo `capability_bits`, e' verificabile: nessun altro test
    tocca i suoi rami `unreachable`.)

    Mutazione ESEGUITA: in `capability_bits`, sostituire il primo `if
    registry is None` con `if False` -- `capability_bits(None)` solleva
    `AttributeError` invece di rispondere `unreachable`, e la prova
    arrossisce.
    """
    mai_letto = ServiceRegistry()
    assert capability_bits(mai_letto)["silenzio"] == SILENCE_UNREACHABLE
    assert capability_bits(None)["silenzio"] == SILENCE_UNREACHABLE


def test_i_domini_accendibili_si_derivano_e_non_si_scrivono():
    """`mind/facts.py:14-27` afferma che Home Assistant «non dichiara da
    nessuna parte quale dominio funziona come un interruttore». **Lo
    dichiara**: `turn_on` e `turn_off`, oppure `toggle`.

    E la derivazione NON coincide col nostro giudizio, in entrambi i versi:
    prende `switch` e `cover` (che ha `toggle`), e **perde `vacuum`**, che
    Home Assistant comanda con `start`/`stop`. E' il motivo per cui questa
    lista SORVEGLIA il giudizio invece di sostituirlo.

    Mutazione ESEGUITA: in `switchable_domains`, richiedere `turn_on` e
    `turn_off` E ANCHE `toggle` (`<=` su tutti e tre) -- `cover` e `switch`
    escono e la prova arrossisce.
    """
    accendibili = switchable_domains(_registro(SERVIZI))["valore"]
    assert "switch" in accendibili
    assert "cover" in accendibili          # ha `toggle`
    assert "media_player" in accendibili   # ha `turn_on` e `turn_off`
    assert "vacuum" not in accendibili     # HA lo comanda con start/stop
    assert switchable_domains(ServiceRegistry())["silenzio"] == SILENCE_UNREACHABLE
