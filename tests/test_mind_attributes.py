"""Gli attributi: il fatto vive spesso fuori dallo stato (spec §5.4).

**L'esempio fondativo del cervello non era rispondibile**, e la spec dice
perche': *«lo stato di un termostato e' `heat` e resta `heat`; `hvac_action`
dice `idle`/`heating`»*. Il grezzo non conservava nessuno di quegli attributi.

**Non ne servono tre.** La spec ne cita anche `current_temperature`, che pero'
e' una grandezza CONTINUA: tenerla fra i voluti riaprirebbe il flusso di righe
che il filtro `da == a` ha chiuso. «La casa e' calda alle 16:30» lo dice
`hvac_action` passando a `idle` -- un cambio per episodio, non uno per decimo
di grado (Fable 5.1 e la revisione del 13/09/2026).

Il grezzo ne teneva **tre, scelti a mano** (`device_class`, `state_class`,
`source_type`). **Quali valgano la pena dipende dal dispositivo**, e lo dice il
sapere -- non una lista nel codice.
"""
import json

import pytest

from hiris.app.mind.knowledge import KnowledgeStore, attributes_wanted_for
from hiris.app.mind.seed import attribute_seed
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher


@pytest.fixture
def sapere(tmp_path):
    s = KnowledgeStore(str(tmp_path / "sapere.db"))
    s.seed(attribute_seed(1789000000.0))
    yield s
    s.close()


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(str(tmp_path / "osservazioni.db"))
    a.decide_scope("climate.soggiorno", inside=True,
                   reason="il termostato del soggiorno pesa sul comfort",
                   author="prova")
    yield a
    a.close()


#: L'ultimo cambio di STATO del termostato: giorni prima.
QUANDO_CAMBIO_STATO = "2026-09-06T08:00:00+00:00"
#: Il momento in cui l'attributo si e' mosso: oggi.
QUANDO_CAMBIO_ATTRIBUTO = "2026-09-12T16:30:00+00:00"


def _evento(*, vecchio_stato, nuovo_stato, attributi, vecchi_attributi=None):
    """Un evento `state_changed` **come Home Assistant lo manda davvero**.

    La differenza che conta, e che la prima stesura di questa fabbrica
    sbagliava: per un evento di **solo attributo** `last_changed` NON si
    muove -- resta quello dell'ultimo cambio di stato, giorni prima -- mentre
    `last_updated` si'. Inventare un `last_changed` fresco anche li'
    costruiva un evento che Home Assistant non manda mai, e nascondeva il
    difetto che la revisione indipendente ha trovato il 13/09/2026.
    """
    solo_attributo = vecchio_stato == nuovo_stato
    return {"entity_id": "climate.soggiorno",
            "old_state": {"state": vecchio_stato,
                          "attributes": vecchi_attributi if vecchi_attributi is not None
                          else dict(attributi)},
            "new_state": {"state": nuovo_stato, "attributes": dict(attributi),
                          "last_changed": (QUANDO_CAMBIO_STATO if solo_attributo
                                           else QUANDO_CAMBIO_ATTRIBUTO),
                          "last_updated": QUANDO_CAMBIO_ATTRIBUTO}}


# -- quali attributi valgono la pena ---------------------------------------

def test_il_sapere_dice_quali_attributi_tenere_PER_TIPO(sapere):
    """Non una lista nel codice: una riga del sapere, col soggetto che dice
    per quale tipo vale e la provenienza che dice chi l'ha deciso."""
    voluti = attributes_wanted_for(sapere, domain="climate", device_class=None)

    assert "hvac_action" in voluti
    # **`current_temperature` NON c'e'**, ed e' una scelta, non una
    # dimenticanza: e' una grandezza continua, e tenerla fra i voluti
    # riaprirebbe il flusso di righe che il filtro `da == a` ha chiuso. La
    # domanda fondativa la risponde `hvac_action`, che passa a `idle` QUANDO
    # la casa e' arrivata in temperatura -- un cambio per episodio, non uno
    # per decimo di grado (revisione indipendente, 13/09/2026).
    assert "current_temperature" not in voluti


def test_un_tipo_di_cui_nessuno_ha_deciso_niente_non_tiene_ATTRIBUTI(sapere):
    """Il silenzio non e' «tienili tutti»: tenerli tutti rimetterebbe nel
    grezzo le **6.503** righe al giorno che il filtro `da == a` ha tolto --
    di cui 6.446 dei soli otto termostati (misurato il 10/09/2026; il numero
    di questa frase era sbagliato fino al 13/09)."""
    assert attributes_wanted_for(sapere, domain="light", device_class=None) == ()


def test_la_riga_degli_attributi_e_un_GIUDIZIO_NOSTRO_senza_verifica(sapere):
    """Nessuna API di Home Assistant dice quali attributi contino per capire
    una casa: e' un giudizio, quindi `provenienza` e' `nostro` e `verifica`
    e' vuota -- la regola che `Fact` fa rispettare al costruttore."""
    riga = sapere.get("tipo", "climate", "attributi")

    assert riga.provenance == "nostro"
    assert riga.verification is None


# -- cosa il grezzo conserva -----------------------------------------------

def test_gli_attributi_VOLUTI_finiscono_nel_grezzo(archivio, sapere):
    """Il fatto vive nell'attributo: se non lo scriviamo, l'esempio fondativo
    resta non rispondibile per sempre -- il grezzo e' l'unica cosa che si
    puo' rileggere.

    Mutazione ESEGUITA: non passare `attributes` a `record` -- rossa.
    """
    osservatore = Watcher(archivio, knowledge=sapere)

    osservatore.watch_reading(_evento(
        vecchio_stato="off", nuovo_stato="heat",
        attributi={"hvac_action": "heating", "temperature": 21.0,
                   "friendly_name": "Soggiorno"}))

    [riga] = archivio.readings(from_ts=0, to_ts=2e9)
    tenuti = json.loads(riga["attributes"])
    assert tenuti["hvac_action"] == "heating"
    assert tenuti["temperature"] == 21.0


def test_gli_attributi_NON_voluti_non_entrano(archivio, sapere):
    """Tenere tutto costerebbe quanto non filtrare affatto."""
    osservatore = Watcher(archivio, knowledge=sapere)

    osservatore.watch_reading(_evento(
        vecchio_stato="off", nuovo_stato="heat",
        attributi={"hvac_action": "heating", "icon": "mdi:radiator",
                   "supported_features": 401}))

    [riga] = archivio.readings(from_ts=0, to_ts=2e9)
    tenuti = json.loads(riga["attributes"])
    assert set(tenuti) == {"hvac_action"}


def test_SENZA_sapere_l_osservatore_scrive_come_prima(archivio):
    """Il sapere e' facoltativo per l'osservatore: senza, niente attributi e
    nessun guasto. Un componente che si rompe quando un altro manca non e'
    autonomo (quarta fondamenta)."""
    osservatore = Watcher(archivio)

    assert osservatore.watch_reading(_evento(
        vecchio_stato="off", nuovo_stato="heat", attributi={"hvac_action": "heating"}))

    [riga] = archivio.readings(from_ts=0, to_ts=2e9)
    assert riga["attributes"] is None


# -- il cambio di un attributo VOLUTO e' un cambio --------------------------

def test_un_attributo_VOLUTO_che_cambia_e_un_cambio_anche_se_lo_stato_no(
        archivio, sapere):
    """**E' la meta' che rende rispondibile l'esempio fondativo.**

    Lo stato del termostato e' `heat` e resta `heat` per tutto il pomeriggio;
    `hvac_action` passa da `heating` a `idle` quando la casa e' arrivata in
    temperatura. Senza questa riga, «la casa e' calda alle 16:30» non si sa.

    Mutazione ESEGUITA: rimettere `if da == a: return False` nudo -- rossa,
    il cambio dell'attributo sparisce.
    """
    osservatore = Watcher(archivio, knowledge=sapere)

    scritto = osservatore.watch_reading(_evento(
        vecchio_stato="heat", nuovo_stato="heat",
        vecchi_attributi={"hvac_action": "heating"},
        attributi={"hvac_action": "idle"}))

    assert scritto
    [riga] = archivio.readings(from_ts=0, to_ts=2e9)
    assert json.loads(riga["attributes"])["hvac_action"] == "idle"


def test_un_attributo_che_NESSUNO_vuole_non_fa_nascere_una_riga(
        archivio, sapere):
    """**La misura che giustifica il filtro resta valida.** Il 10/09/2026:
    6.503 righe al giorno su 29.227 erano cambi di solo attributo, di cui
    6.446 degli otto termostati -- che di cambi veri ne fanno otto.

    Se qualunque attributo facesse nascere una riga, quel guadagno tornerebbe
    indietro tutto: passa solo cio' che qualcuno ha deciso che conta.

    Mutazione ESEGUITA: confrontare TUTTI gli attributi invece dei soli
    voluti -- rossa, la riga nasce.
    """
    osservatore = Watcher(archivio, knowledge=sapere)

    scritto = osservatore.watch_reading(_evento(
        vecchio_stato="heat", nuovo_stato="heat",
        vecchi_attributi={"hvac_action": "idle", "icon": "mdi:radiator"},
        attributi={"hvac_action": "idle", "icon": "mdi:fire"}))

    assert not scritto
    assert archivio.readings(from_ts=0, to_ts=2e9) == []


def test_la_riga_nata_da_un_ATTRIBUTO_porta_l_istante_giusto(archivio, sapere):
    """**Il difetto che la revisione indipendente ha trovato il 13/09/2026.**

    `last_changed` non si muove per un evento di solo attributo -- misurato il
    10/09, tutti e otto i termostati portavano quello del 06/09. Una riga nata
    dal passaggio di `hvac_action` da `heating` a `idle` sarebbe quindi nata
    datata a giorni prima, e sarebbe caduta fuori dalla finestra del giorno:
    scritta, e mai letta da nessuno. Cioe' il guasto che il filtro `da == a`
    chiudeva «per forza», riaperto dall'eccezione nuova sulle stesse entita'.

    L'istante e' `last_updated`, che si muove anche per un attributo -- e
    basta lui, senza rami: per un cambio di stato vero Home Assistant muove
    tutti e due insieme. La prima correzione ne aveva scritti due, e la prova
    che li distingueva non poteva fallire perche' costruiva un evento che HA
    non manda mai (Fable 5.1, 13/09/2026).

    Mutazione ESEGUITA: leggere `last_changed` -- rossa, la riga torna datata
    al 6 settembre.
    """
    from hiris.app.home_space.historian import instant_epoch

    osservatore = Watcher(archivio, knowledge=sapere)

    osservatore.watch_reading(_evento(
        vecchio_stato="heat", nuovo_stato="heat",
        vecchi_attributi={"hvac_action": "heating"},
        attributi={"hvac_action": "idle"}))

    [riga] = archivio.readings(from_ts=0, to_ts=2e9)
    assert riga["quando_ts"] == instant_epoch(QUANDO_CAMBIO_ATTRIBUTO)


# -- l'esempio fondativo, dall'evento all'oggetto ---------------------------

def test_L_ESEMPIO_FONDATIVO_il_riscaldamento_parte_e_la_casa_si_scalda(
        archivio, sapere):
    """**«Il riscaldamento parte alle 15:30, la casa e' calda alle 16:30.»**

    E' l'esempio da cui nasce tutto il cervello, e la spec §5.4 dice che
    **oggi non e' rispondibile**: lo stato di un termostato e' `heat` e resta
    `heat`, quindi l'episodio sapeva dire quando e' partito e nient'altro.

    Adesso l'oggetto porta cosa ha fatto `hvac_action` mentre durava: `heating`
    alle 15:30, `idle` alle 16:30 -- cioe' il momento in cui la casa e'
    arrivata in temperatura.

    E' anche il **lettore** della colonna `attributes` del grezzo: senza di
    lui quella colonna sarebbe scritta e non letta da nessuno, e un dato che
    nessuno puo' chiedere non esiste (quarta fondamenta).

    Mutazione ESEGUITA: togliere da `close()` il blocco che compone
    `base_body["attributi"]` -- rossa.
    """
    from hiris.app.mind.facts import aggregate_day

    osservatore = Watcher(archivio, knowledge=sapere)
    # 15:30 -- parte davvero: cambio di STATO.
    osservatore.watch_reading({
        "entity_id": "climate.soggiorno",
        "old_state": {"state": "off", "attributes": {}},
        "new_state": {"state": "heat", "attributes": {"hvac_action": "heating"},
                      "last_changed": "2026-09-12T13:30:00+00:00",
                      "last_updated": "2026-09-12T13:30:00+00:00"}})
    # 16:30 -- la casa e' calda: cambia SOLO l'attributo.
    osservatore.watch_reading({
        "entity_id": "climate.soggiorno",
        "old_state": {"state": "heat", "attributes": {"hvac_action": "heating"}},
        "new_state": {"state": "heat", "attributes": {"hvac_action": "idle"},
                      "last_changed": "2026-09-12T13:30:00+00:00",
                      "last_updated": "2026-09-12T14:30:00+00:00"}})

    aggregate_day(store=archivio, day="2026-09-12", timezone="Europe/Rome")

    [oggetto] = archivio.facts(day="2026-09-12")
    assert oggetto["genere"] == "funzionamento"
    apertura, arrivo = oggetto["corpo"]["attributi"]
    # **Tutte e due le voci**: la foto d'apertura (15:30, sta scaldando) e il
    # momento in cui la casa e' arrivata in temperatura (16:30). Senza la
    # prima, meta' della colonna `attributes` del grezzo resterebbe scritta e
    # non letta da nessuno (Fable 5.1, 13/09/2026).
    assert apertura["valori"] == {"hvac_action": "heating"}
    assert apertura["quando_ts"] == 1789219800.0
    assert arrivo["valori"] == {"hvac_action": "idle"}
    assert arrivo["quando_ts"] == 1789223400.0
