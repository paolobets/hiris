"""Come si rende uno stato di Home Assistant, e da dove viene la tabella.

I quattro gradini sono la trascrizione di `async_translate_state`
(`homeassistant/helpers/translation.py:459-491`, tag `2026.9.1`): ognuno ha
qui la sua prova, e ognuna dichiara la mutazione che l'ha vista rossa. Le
chiavi usate nelle prove non sono inventate: sono state LETTE dalla casa vera
il 07/09/2026 (`frontend/get_translations`, `language: "it"`,
`category: "entity_component"`, 801 chiavi).
"""
import pytest

from hiris.app.proxy.state_translations import StateTranslations, state_translation

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
# I quattro gradini, uno per uno, ognuno che cade sul successivo
# ---------------------------------------------------------------------------

def test_primo_gradino_la_chiave_dell_integrazione_vince_su_tutte():
    """`component.{platform}.entity.{domain}.{translation_key}.state.{state}`
    (`translation.py:472-478`). E' il gradino piu' specifico: quando risponde,
    nessun altro viene interrogato.

    Mutazione ESEGUITA: spostare il blocco del primo gradino DOPO quello del
    `device_class` in `state_translation` -- il test torna rosso su
    `assert reso == "Rilevato dall'integrazione"`, perche' risponde il
    gradino della classe («Rilevato dalla classe»).
    """
    reso = state_translation(
        "on", domain="binary_sensor", device_class="motion", platform="reolink",
        translation_key="animal",
        component_resources={
            "component.binary_sensor.entity_component.motion.state.on":
                "Rilevato dalla classe",
        },
        entity_resources={
            "component.reolink.entity.binary_sensor.animal.state.on":
                "Rilevato dall'integrazione",
        })
    assert reso == "Rilevato dall'integrazione"


def test_senza_la_chiave_dell_integrazione_si_cade_sul_device_class():
    """Il primo gradino non trova nulla (o `entity_resources` non c'e'
    affatto, che e' il caso di oggi): risponde il secondo,
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

class _FintoClient:
    """Il solo metodo che la cache usa, con lo stesso contratto del vero
    (`HAClient.get_translations`: `{"risorse": ...}` oppure `{"errore": ...}`)."""

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
    `assert client.chiamate == [("it", "entity_component")]`, che ne conta tre.
    """
    client = _FintoClient([{"risorse": RISORSE_COMPONENTE}])
    cache = StateTranslations(client)
    for _ in range(3):
        esito = await cache.read(ha_version="2026.9.1", language="it")
        assert esito["lette"] is True
        assert esito["risorse"] == RISORSE_COMPONENTE
    assert client.chiamate == [("it", "entity_component")]


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
    client = _FintoClient([{"risorse": RISORSE_COMPONENTE}, {"risorse": inglese}])
    cache = StateTranslations(client)
    primo = await cache.read(ha_version="2026.9.1", language="it")
    secondo = await cache.read(ha_version="2026.9.1", language="en")
    assert primo["risorse"]["component.climate.entity_component._.state.heat"] == "Riscaldamento"
    assert secondo["risorse"]["component.climate.entity_component._.state.heat"] == "Heating"
    assert client.chiamate == [("it", "entity_component"), ("en", "entity_component")]


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
    client = _FintoClient([{"risorse": RISORSE_COMPONENTE}, {"risorse": nuova}])
    cache = StateTranslations(client)
    await cache.read(ha_version="2026.9.1", language="it")
    dopo = await cache.read(ha_version="2026.10.0", language="it")
    assert dopo["risorse"]["component.climate.entity_component._.state.heat"] \
        == "Riscaldamento (nuovo)"
    assert len(client.chiamate) == 2


@pytest.mark.asyncio
async def test_senza_la_lingua_della_casa_non_si_chiede_niente_e_lo_si_DICHIARA():
    """`frontend/get_translations` vuole la lingua come parametro obbligatorio
    (`frontend/__init__.py:1007-1015`). Sceglierne una noi (`"en"` di ripiego)
    renderebbe la pagina in una lingua che il proprietario non ha chiesto, e
    lo farebbe in silenzio.

    Mutazione ESEGUITA: `language = language or "en"` in cima a `read` -- il
    test torna rosso su `assert client.chiamate == []`.
    """
    client = _FintoClient([{"risorse": RISORSE_COMPONENTE}])
    cache = StateTranslations(client)
    esito = await cache.read(ha_version="2026.9.1", language=None)
    assert esito["lette"] is False
    assert "lingua" in esito["motivo"]
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_una_lettura_fallita_porta_il_MOTIVO_di_home_assistant():
    """Il motivo lo produce chi lo conosce e viaggia etichettato: chi legge
    non deve dedurlo da un dizionario vuoto.

    Mutazione ESEGUITA: `return {"lette": False}` senza `motivo` nel ramo di
    guasto -- il test torna rosso su
    `assert esito["motivo"] == "unknown_command"` (`KeyError: 'motivo'`).
    """
    client = _FintoClient([{"errore": "unknown_command"}])
    cache = StateTranslations(client)
    esito = await cache.read(ha_version="2026.9.1", language="it")
    assert esito["lette"] is False
    assert esito["motivo"] == "unknown_command"
    assert "risorse" not in esito


@pytest.mark.asyncio
async def test_una_lettura_fallita_non_diventa_mai_una_tabella_VUOTA():
    """Una tabella vuota direbbe «questa casa non traduce niente», che e'
    un'altra cosa dal non aver potuto chiedere. E' la stessa distinzione che
    `read_registries` difende fra un registro vuoto e un registro caduto."""
    client = _FintoClient([{"errore": "Home Assistant non ha risposto"}])
    esito = await StateTranslations(client).read(ha_version="2026.9.1", language="it")
    assert esito.get("risorse") is None
    assert esito["lette"] is False


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
