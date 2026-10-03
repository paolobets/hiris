"""Come si rende uno stato di Home Assistant, e da dove viene la tabella.

I gradini sono la trascrizione di `async_translate_state` (dal secondo in poi)
(`homeassistant/helpers/translation.py:459-491`, tag `2026.9.1`): ognuno ha
qui la sua prova, e ognuna dichiara la mutazione che l'ha vista rossa. Le
chiavi usate nelle prove non sono inventate: sono state LETTE dalla casa vera
il 07/09/2026 (`frontend/get_translations`, `language: "it"`,
`category: "entity_component"`, 801 chiavi).
"""
import sys
from pathlib import Path

import pytest

from hiris.app.proxy.state_translations import StateTranslations, state_translation
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

# Le chiavi e i testi sono quelli MISURATI sulla casa, non plausibili.
RISORSE_COMPONENTE = {
    "component.climate.entity_component._.state.heat": "Riscaldamento",
    "component.person.entity_component._.state.not_home": "Fuori casa",
    "component.alarm_control_panel.entity_component._.state.triggered": "Innescato",
    "component.alarm_control_panel.entity_component._.state.disarmed": "Disattivo",
    "component.binary_sensor.entity_component._.state.on": "Acceso",
    "component.binary_sensor.entity_component.smoke.state.on": "Rilevato",
}


# ---------------------------------------------------------------------------
# I gradini trascritti (il secondo, il terzo e il quarto di Home Assistant),
# ognuno che cade sul successivo
# ---------------------------------------------------------------------------

def test_il_device_class_risponde_per_primo():
    """Il primo gradino di Home Assistant (la chiave propria dell'integrazione)
    qui non e' trascritto -- nessuno ne scarica le risorse: risponde il secondo,
    `component.{domain}.entity_component.{device_class}.state.{state}`
    (`translation.py:480-486`).

    Il valore misurato sulla casa e' esattamente questo: un rilevatore di
    fumo scattato si legge «Rilevato», non «Acceso».

    Mutazione ESEGUITA: togliere il blocco `if device_class:` da
    `state_translation` -- il test torna rosso su
    `assert reso == "Rilevato"` (ottiene `'Acceso'`, il gradino dopo).
    """
    reso = state_translation("on", domain="binary_sensor", device_class="smoke",
                             component_resources=RISORSE_COMPONENTE)
    assert reso == "Rilevato"


def test_senza_device_class_si_cade_sul_gradino_del_dominio():
    """`component.{domain}.entity_component._.state.{state}`
    (`translation.py:487-489`) -- l'underscore, non la classe. E' il gradino
    che copre i quattro stati inglesi misurati sulla pagina dell'osservatore
    (`not_home`, `heat`, `triggered`, `disarmed`): 4 su 4.

    Mutazione ESEGUITA: scrivere `entity_component.{device_class}` al posto di
    `entity_component._` nella chiave del terzo gradino -- il test torna rosso
    su `assert reso == "Riscaldamento"` (ottiene `None`).
    """
    reso = state_translation("heat", domain="climate",
                             component_resources=RISORSE_COMPONENTE)
    assert reso == "Riscaldamento"


def test_una_classe_senza_chiave_propria_non_impedisce_il_gradino_del_dominio():
    """Il secondo gradino che non risponde non e' un muro: si scivola sul
    terzo, che e' quello che HA fa (`translation.py:486` prosegue, non torna).

    Mutazione ESEGUITA: `return component_resources.get(key)` al posto di
    `if key in component_resources: return ...` nel blocco del `device_class`
    -- il test torna rosso su `assert reso == "Acceso"` (ottiene `None`: la
    classe sconosciuta interrompe la catena).
    """
    reso = state_translation("on", domain="binary_sensor",
                             device_class="una_classe_che_non_esiste",
                             component_resources=RISORSE_COMPONENTE)
    assert reso == "Acceso"


def test_quarto_gradino_uno_stato_senza_traduzione_lo_DICHIARA():
    """**Scostamento dichiarato dal sorgente di HA.** `translation.py:491` fa
    `return state`; qui si torna `None`.

    HA rende per una pagina, e per lui «il grezzo» e' la risposta finale. Chi
    chiama da qui deve invece poter DIRE al proprietario che quello stato
    traduzione non ne ha -- e distinguerlo da «non ho potuto leggere le
    traduzioni», che e' un altro fatto. Con `return state` i due casi
    tornerebbero la stessa stringa e la differenza andrebbe indovinata a
    valle. Il grezzo resta cio' che il lettore vede: lo decide il confine
    dell'API, non questa funzione.

    Gli stati di questa prova sono VERI, letti sulla casa il 07/09/2026 fra i
    73 valori testuali distinti: HA stesso li mostra grezzi.

    Mutazione ESEGUITA: `return state` come ultima riga di
    `state_translation` -- il test torna rosso su
    `assert state_translation(...) is None`.
    """
    assert state_translation("digitalfirst", domain="select",
                             component_resources=RISORSE_COMPONENTE) is None
    assert state_translation("Not Charging", domain="sensor",
                             component_resources=RISORSE_COMPONENTE) is None


def test_senza_nessuna_risorsa_non_si_inventa_una_resa():
    """Tabella vuota: nessun gradino puo' rispondere, e la funzione lo dice
    invece di rimandare indietro il grezzo travestito da traduzione."""
    assert state_translation("heat", domain="climate", component_resources={}) is None


# ---------------------------------------------------------------------------
# Le due voci che Home Assistant non traduce mai qui: nessuna resa dedicata
# ---------------------------------------------------------------------------

def test_unavailable_e_unknown_non_producono_una_resa_qui():
    """Revisione del tratto v3.22.2..HEAD, rilievo R5: fino al 07/09/2026
    `state_translation` portava due etichette proprie per questi due stati
    (`_OUR_LABELS`, commit `b68bda11`) -- un ramo morto rispetto al chiamante
    di allora (`api/handlers_mind.py::_with_rendered_states`, dietro
    `/api/mind/facts`), che legge solo oggetti che `mind/facts.py::
    aggregate_day` ha gia' filtrato: li' quei due stati non aprono ne'
    chiudono un episodio e sono scartati prima che un `corpo.stato` esista
    (vedi `tests/test_mind_facts.py`, punto 2). Rimosso insieme alla prova
    che costruiva a mano un corpo che l'archivio non produce mai
    (`tests/test_mind_api.py`).

    **Non e' piu' l'unico chiamante** (corretto 09/09/2026): `rendered_state`
    porta questi due stati anche dallo stato VIVO di un'entita' (nucleo,
    `view`/`search`, via `topology.readable_state`), non filtrato da
    `aggregate_day`. Non serve comunque un'etichetta dedicata: senza risorse
    e senza un gradino che risponda, questi due stati sono "senza traduzione"
    come qualunque altro, e la funzione lo dichiara con `None` -- chi chiama
    lo traduce nel silenzio «ho chiesto e non c'e'», non in un'etichetta
    inventata qui dentro."""
    assert state_translation("unavailable", domain="climate",
                             component_resources={}) is None
    assert state_translation("unknown", domain="climate",
                             component_resources={}) is None


def test_uno_stato_vuoto_o_non_testuale_non_produce_una_resa():
    """Un corpo malformato non deve produrre una chiave: `None` e' l'assenza
    di una resa, non una resa vuota."""
    assert state_translation(None, domain="climate",
                             component_resources=RISORSE_COMPONENTE) is None
    assert state_translation("", domain="climate",
                             component_resources=RISORSE_COMPONENTE) is None
    assert state_translation("heat", domain=None,
                             component_resources=RISORSE_COMPONENTE) is None


# ---------------------------------------------------------------------------
# La cache: quando legge, quando rilegge, e cosa dice quando non ci riesce
# ---------------------------------------------------------------------------

#: Il comando e la sua domanda, come il client vero li manda
#: (`HAClient.get_translations`): la categoria e' quella della cache.
TRANSLATIONS_COMMAND = "frontend/get_translations"
ASKED_IN_ITALIAN = (TRANSLATIONS_COMMAND, {"language": "it", "category": "entity_component"})


def _translations_house(resources=RISORSE_COMPONENTE, **injected) -> CasaFinta:
    """Home Assistant che traduce in italiano, sotto il client VERO
    (`CasaFinta`, D8 della Tappa 2): `frontend/get_translations` risponde
    `{"resources": ...}` -- la forma di `websocket_get_translations`
    (`homeassistant/components/frontend/__init__.py:1007-1030`, tag
    `2026.9.4`, letto il 03/10/2026). `injected` passa `answers`, `refuse`,
    `silence` a `CasaFinta` cosi' come sono."""
    inputs = synthetic_inputs()
    inputs["translations"] = {"language": "it", "category": "entity_component",
                              "report": {"risorse": dict(resources)}}
    return CasaFinta(inputs, **injected)


class _FintoClient:
    """Il solo metodo che la cache usa, con lo stesso contratto del vero
    (`HAClient.get_translations`: `{"risorse": ...}` oppure `{"errore": ...}`).

    **Resta una finta a mano, per una prova sola, e non `CasaFinta`** (Tappa
    2, Task 12): `test_dopo_un_guasto_si_ritenta_alla_lettura_successiva`
    vuole una casa che alla STESSA domanda prima tace e poi risponde.
    `CasaFinta` decide silenzi e rifiuti alla nascita (`silence=`,
    `refuse=`), e una risposta iniettata (`answers=`) puo' solo riuscire:
    la sequenza «prima tace, poi risponde» non si esprime."""

    def __init__(self, esiti):
        self.esiti = list(esiti)
        self.chiamate = []

    async def get_translations(self, language, category="entity_component"):
        self.chiamate.append((language, category))
        return self.esiti.pop(0) if len(self.esiti) > 1 else self.esiti[0]


@pytest.mark.asyncio
async def test_la_tabella_si_legge_una_volta_sola_finche_la_casa_non_cambia():
    """801 chiavi a ogni apertura della pagina sarebbero una lettura di rete
    per pagina. La coppia `(versione_ha, lingua)` e' la stessa: non si
    richiede niente.

    Mutazione ESEGUITA: togliere il controllo
    `if self._resources is not None and self._key == key` da dentro il lock di
    `read` (l'unico che c'e') -- il test torna rosso su
    `assert house.calls == [ASKED_IN_ITALIAN]`, che ne conta tre.
    """
    house = _translations_house()
    cache = StateTranslations(house)
    for _ in range(3):
        esito = await cache.read(ha_version="2026.9.1", language="it")
        assert esito["lette"] is True
        assert esito["risorse"] == RISORSE_COMPONENTE
    assert house.calls == [ASKED_IN_ITALIAN]


@pytest.mark.asyncio
async def test_la_tabella_si_RILEGGE_quando_la_casa_cambia_lingua():
    """La lingua e' una preferenza mutabile della casa (`hass.config.language`):
    e' esattamente la ragione per cui lo stato si rende alla lettura invece di
    congelarlo in archivio. Se la cache non se ne accorgesse, la resa
    resterebbe congelata lo stesso -- il difetto rientrerebbe dalla finestra.

    Mutazione ESEGUITA: `key = (ha_version,)` -- la chiave della cache
    dimentica la lingua -- il test torna rosso su
    `assert secondo["risorse"][...] == "Heating"`: la cache ritorna la
    tabella italiana a una casa che ha cambiato lingua.
    """
    inglese = {"component.climate.entity_component._.state.heat": "Heating"}
    # La casa risponde nella lingua CHIESTA: la tabella la sceglie il
    # comando, non l'ordine delle domande.
    by_language = {"it": RISORSE_COMPONENTE, "en": inglese}
    house = _translations_house(answers={TRANSLATIONS_COMMAND: lambda extra: {
        "resources": dict(by_language[extra["language"]])}})
    cache = StateTranslations(house)
    primo = await cache.read(ha_version="2026.9.1", language="it")
    secondo = await cache.read(ha_version="2026.9.1", language="en")
    assert primo["risorse"]["component.climate.entity_component._.state.heat"] == "Riscaldamento"
    assert secondo["risorse"]["component.climate.entity_component._.state.heat"] == "Heating"
    assert house.calls == [ASKED_IN_ITALIAN,
                           (TRANSLATIONS_COMMAND, {"language": "en",
                                                   "category": "entity_component"})]


@pytest.mark.asyncio
async def test_la_tabella_si_RILEGGE_quando_la_casa_cambia_versione_di_HA():
    """Le chiavi di `entity_component` sono quelle dei domini caricati a
    quella versione: un aggiornamento di Home Assistant puo' aggiungerne e
    toglierne. La versione fa parte della chiave della cache.

    Mutazione ESEGUITA: `key = (language,)` -- la chiave dimentica la versione
    -- il test torna rosso su `assert dopo["risorse"][...] == "Riscaldamento
    (nuovo)"` (ottiene `'Riscaldamento'`, la tabella della versione vecchia).
    """
    nuova = dict(RISORSE_COMPONENTE)
    nuova["component.climate.entity_component._.state.heat"] = "Riscaldamento (nuovo)"
    # La versione di Home Assistant non viaggia nel comando: e' la casa ad
    # essersi aggiornata fra una domanda e l'altra, e la seconda risposta e'
    # quella della versione nuova.
    tables = iter([RISORSE_COMPONENTE, nuova])
    house = _translations_house(answers={TRANSLATIONS_COMMAND: lambda extra: {
        "resources": dict(next(tables))}})
    cache = StateTranslations(house)
    await cache.read(ha_version="2026.9.1", language="it")
    dopo = await cache.read(ha_version="2026.10.0", language="it")
    assert dopo["risorse"]["component.climate.entity_component._.state.heat"] \
        == "Riscaldamento (nuovo)"
    assert house.calls == [ASKED_IN_ITALIAN, ASKED_IN_ITALIAN]


@pytest.mark.asyncio
async def test_senza_la_lingua_della_casa_non_si_chiede_niente_e_lo_si_DICHIARA():
    """`frontend/get_translations` vuole la lingua come parametro obbligatorio
    (`frontend/__init__.py:1007-1015`). Sceglierne una noi (`"en"` di ripiego)
    renderebbe la pagina in una lingua che il proprietario non ha chiesto, e
    lo farebbe in silenzio.

    Mutazione ESEGUITA: `language = language or "en"` in cima a `read` -- il
    test torna rosso su `assert house.calls == []`.
    """
    house = _translations_house()
    cache = StateTranslations(house)
    esito = await cache.read(ha_version="2026.9.1", language=None)
    assert esito["lette"] is False
    assert "lingua" in esito["motivo"]
    assert house.calls == []


@pytest.mark.asyncio
async def test_una_lettura_fallita_porta_il_MOTIVO_di_home_assistant():
    """Il motivo lo produce chi lo conosce e viaggia etichettato: chi legge
    non deve dedurlo da un dizionario vuoto.

    Il rifiuto e' quello vero di Home Assistant per un comando che non
    conosce: `unknown_command` / «Unknown command.»
    (`websocket_api/connection.py:236-240`, tag `2026.9.4`). Il motivo che
    il client porta e' il `message` di Home Assistant (`_ws_occurrence`);
    il codice viaggia a parte, in `codice`. Fino al Task 12 la finta
    rispondeva `{"errore": "unknown_command"}` -- il codice al posto del
    messaggio, una busta che il client non produce.

    Mutazione ESEGUITA: `return {"lette": False}` senza `motivo` nel ramo di
    guasto -- il test torna rosso su
    `assert esito["motivo"] == "Unknown command."` (`KeyError: 'motivo'`).
    """
    house = _translations_house(refuse={TRANSLATIONS_COMMAND: {
        "code": "unknown_command", "message": "Unknown command."}})
    cache = StateTranslations(house)
    esito = await cache.read(ha_version="2026.9.1", language="it")
    assert esito["lette"] is False
    assert esito["motivo"] == "Unknown command."
    assert "risorse" not in esito


@pytest.mark.asyncio
async def test_una_lettura_fallita_non_diventa_mai_una_tabella_VUOTA():
    """Una tabella vuota direbbe «questa casa non traduce niente», che e'
    un'altra cosa dal non aver potuto chiedere. E' la stessa distinzione che
    `read_registries` difende fra un registro vuoto e un registro caduto."""
    house = _translations_house(silence={TRANSLATIONS_COMMAND})
    esito = await StateTranslations(house).read(ha_version="2026.9.1", language="it")
    assert esito.get("risorse") is None
    assert esito["lette"] is False
    assert esito["motivo"] == "Home Assistant non ha risposto"


@pytest.mark.asyncio
async def test_dopo_un_guasto_si_ritenta_alla_lettura_successiva():
    """Un blip di rete non deve spegnere le traduzioni per tutta la vita del
    processo: la coppia non e' stata memorizzata, quindi la prossima lettura
    riprova."""
    client = _FintoClient([{"errore": "rete giu'"}, {"risorse": RISORSE_COMPONENTE}])
    cache = StateTranslations(client)
    assert (await cache.read(ha_version="2026.9.1", language="it"))["lette"] is False
    assert (await cache.read(ha_version="2026.9.1", language="it"))["lette"] is True
    assert len(client.chiamate) == 2
