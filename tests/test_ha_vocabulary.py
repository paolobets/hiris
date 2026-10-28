"""Il vocabolario di `ha_vocabulary.py`, pinnato contro la fonte -- non
contro se stesso.

La stessa disciplina di `tests/test_feature_tables_pinned_to_source.py`
(fetta precedente, stesso ramo): la review indipendente aveva trovato tre
mutazioni delle tabelle di `_FEATURE_NAMES` che restavano VERDI perche' le
prove di allora confrontavano quasi solo il primo bit di ogni tabella. Qui la
stessa forma di difetto sarebbe: pinnare le CHIAVI del vocabolario leggendole
dal vocabolario stesso -- una tabella che verifica se stessa non verifica
niente. Le liste sotto (`_MEASURED_DEVICE_CLASS_PAIRS`,
`_MEASURED_STATE_CLASSES`) sono state ricopiate a mano dalla misura fatta sul
sorgente vero della casa (`http://192.168.1.95:8123/api/states`, 07/09/2026),
non importate da `hiris.app.home_space.ha_vocabulary`.

Fonte per il contenuto delle voci pinnate: sorgente vero di Home Assistant,
tag `2026.9.1` -- vedi la fonte in testa a `ha_vocabulary` per la citazione
file per file.
"""
from hiris.app.home_space.ha_vocabulary import (
    DEVICE_CLASS_MEANING,
    ENTITY_CATEGORY_MEANING,
    STATE_CLASS_MEANING,
    VOCABULARY_HA_VERSION,
    entity_category_measure_rule,
)

# Le due frasi di `EntityCategory` (`homeassistant/const.py`, tag `2026.9.1`)
# ricopiate a mano dal sorgente scaricato davvero
# (`raw.githubusercontent.com/home-assistant/core/2026.9.1/homeassistant/
# const.py`, righe 1032-1037), non lette da `ENTITY_CATEGORY_MEANING` --
# stessa disciplina delle liste sopra: una tabella che verifica se stessa
# non verifica niente.
_SOURCE_ENTITY_CATEGORY_MEANING = {
    "config": "An entity which allows changing the configuration of a device.",
    "diagnostic": "An entity exposing some configuration parameter, or diagnostics of a device.",
}

# Le 27 coppie (dominio, classe) misurate su questa casa il 07/09/2026 --
# ricopiate a mano dal risultato della misura, non lette da
# `DEVICE_CLASS_MEANING`. Le CINQUE classi di `binary_sensor` misurate sulla
# stessa casa (`motion`, `connectivity`, `running`, `occupancy`, `plug` -- 33
# entita') NON compaiono qui apposta: hanno gia' un significato in
# le traduzioni pubblicate da HA, e questo vocabolario non le duplica (vedi il
# docstring del modulo).
_MEASURED_DEVICE_CLASS_PAIRS = (
    ("sensor", "timestamp"), ("sensor", "energy"), ("sensor", "temperature"),
    ("sensor", "power"), ("sensor", "enum"), ("sensor", "battery"),
    ("sensor", "data_rate"), ("sensor", "duration"), ("sensor", "illuminance"),
    ("sensor", "voltage"), ("sensor", "humidity"), ("sensor", "uptime"),
    ("sensor", "current"), ("sensor", "carbon_dioxide"),
    ("sensor", "atmospheric_pressure"), ("sensor", "sound_pressure"),
    ("sensor", "data_size"), ("sensor", "pressure"),
    ("number", "duration"),
    ("button", "identify"), ("button", "restart"),
    ("switch", "outlet"), ("switch", "switch"),
    ("update", "firmware"),
    ("media_player", "speaker"), ("media_player", "tv"),
    ("valve", "water"),
)

# I tre stati di `SensorStateClass` che il sorgente dichiara -- non ce ne
# sono altri da lasciare fuori (`MEASUREMENT_ANGLE` esiste nel sorgente ma
# zero entita' di questa casa lo usano; resta fuori per la stessa regola
# "si importa cio' che la casa usa davvero").
_MEASURED_STATE_CLASSES = ("measurement", "total", "total_increasing")


def test_the_vocabulary_says_which_version_it_came_from():
    """Il pezzo che rende duraturo tutto il tema: quando la casa supera la
    versione del vocabolario, qualcuno lo DICE -- invece di scoprirlo da un
    digesto che sbaglia in silenzio.

    Mutazione: svuotare `VOCABULARY_HA_VERSION` (`= ""`) -- il test torna
    rosso su `assert VOCABULARY_HA_VERSION`.
    """
    assert VOCABULARY_HA_VERSION
    # Un tag rilasciato di Home Assistant e' sempre CalVer (anno.mese.patch):
    # "dev" non lo e' mai, ed e' il vincolo che il capitolato vieta di violare.
    assert VOCABULARY_HA_VERSION != "dev"
    assert VOCABULARY_HA_VERSION.split(".")[0].isdigit()


# Il confronto con la versione della casa e' uscito dal prodotto il
# 25/10/2026 insieme alla riga del nucleo che lo diceva: lo fa ora
# `scripts/verifica_componenti.avviso_vocabolario`, e le sue prove stanno in
# `tests/test_verifica_componenti.py`.


def test_every_measured_device_class_pair_has_a_documented_meaning():
    """Le 27 coppie (dominio, classe) misurate sulla casa vera devono avere
    tutte un significato importato -- una coppia mancante e' una classe che
    questa casa usa e il vocabolario ignora.

    Mutazione: cancellare una voce da `DEVICE_CLASS_MEANING` (per esempio
    `("sensor", "uptime")`) -- il test torna rosso su
    `assert missing == []`.
    """
    missing = [pair for pair in _MEASURED_DEVICE_CLASS_PAIRS if pair not in DEVICE_CLASS_MEANING]
    assert missing == [], f"coppie misurate senza significato importato: {missing}"


def test_the_device_class_table_does_not_go_beyond_what_this_house_measured():
    """Il contrario della prova sopra, e serve quanto quella: una coppia nel
    vocabolario che questa casa non usa e' una riga che nessuno controllera'
    mai contro la casa vera -- esattamente cio' che "importa cio' che questa
    casa usa davvero" vieta.

    Mutazione: aggiungere a `DEVICE_CLASS_MEANING` una coppia mai misurata
    (per esempio `("sensor", "moisture")`, non presente su questa casa) --
    il test torna rosso su `assert invented == []`.
    """
    measured = set(_MEASURED_DEVICE_CLASS_PAIRS)
    invented = sorted(pair for pair in DEVICE_CLASS_MEANING if pair not in measured)
    assert invented == [], f"coppie nel vocabolario mai misurate su questa casa: {invented}"


def test_binary_sensor_meanings_are_not_duplicated_here():
    """Le classi di `binary_sensor` hanno gia' un significato in
    la resa che Home Assistant pubblica: un doppione qui violerebbe la fondamenta
    "nessun doppione" -- lo stesso fatto raccontato da due tabelle puo'
    divergere silenziosamente quando una delle due si aggiorna e l'altra no.

    Mutazione: aggiungere a `DEVICE_CLASS_MEANING` una voce col dominio
    `"binary_sensor"` (per esempio `("binary_sensor", "motion")`) -- il test
    torna rosso su `assert domains_used == set()`.
    """
    domains_used = {domain for domain, _ in DEVICE_CLASS_MEANING if domain == "binary_sensor"}
    assert domains_used == set()


def test_every_measured_state_class_has_a_documented_meaning():
    """Stessa garanzia di completezza, per `state_class`: i tre stati che
    Home Assistant dichiara e che questa casa usa (misurato: 130 entita',
    tutte sensor) devono avere tutti un significato.

    Mutazione: cancellare `STATE_CLASS_MEANING["total_increasing"]` -- il
    test torna rosso su `assert missing == []`.
    """
    missing = [sc for sc in _MEASURED_STATE_CLASSES if sc not in STATE_CLASS_MEANING]
    assert missing == [], f"state_class misurati senza significato importato: {missing}"


def test_the_state_class_table_does_not_invent_states_this_house_never_measured():
    """Il gemello della prova precedente: nessuna quarta chiave oltre le tre
    misurate (`measurement`, `total`, `total_increasing`).

    Mutazione: aggiungere a `STATE_CLASS_MEANING` una chiave mai misurata su
    questa casa (per esempio `"measurement_angle"`, che il sorgente
    dichiara ma nessuna entita' qui usa) -- il test torna rosso su
    `assert set(STATE_CLASS_MEANING) == set(_MEASURED_STATE_CLASSES)`.
    """
    assert set(STATE_CLASS_MEANING) == set(_MEASURED_STATE_CLASSES)


def test_total_and_total_increasing_are_not_the_same_fact():
    """Il gotcha vero di questa tabella: `total` PUO' scendere (un contatore
    di energia netta), `total_increasing` NON dovrebbe mai scendere se non a
    un nuovo ciclo. Scambiarle significherebbe leggere un calo lecito come un
    guasto, o un guasto come un calo lecito.

    Mutazione: scambiare i due valori in `STATE_CLASS_MEANING` (mettere il
    testo di `"total"` sotto `"total_increasing"` e viceversa) -- il test
    torna rosso su uno dei due `assert "CRESCERE" in ...` / `assert
    "SOLO" in ...`, perche' l'atteso qui e' scritto a mano guardando il
    sorgente (`SensorStateClass`), non derivato dalla tabella che verifica.
    """
    assert "CRESCERE" in STATE_CLASS_MEANING["total"]
    assert "DECRESCERE" in STATE_CLASS_MEANING["total"]
    assert "SOLO" in STATE_CLASS_MEANING["total_increasing"]
    assert "azzerarsi" in STATE_CLASS_MEANING["total_increasing"]


def test_uptime_is_documented_as_a_point_in_time_not_a_duration():
    """Il gotcha di `sensor`/`uptime`: nonostante il nome suggerisca "da
    quanto tempo e' acceso", `SensorDeviceClass.UPTIME` nel sorgente e' "the
    point in time when a device or service last restarted" -- un ISTANTE
    (ISO 8601), non una durata. Confuso con `duration`, un digesto futuro
    leggerebbe un timestamp Unix come se fossero secondi di attivita'.

    Mutazione: cambiare `DEVICE_CLASS_MEANING[("sensor", "uptime")]` per
    dire che e' una durata invece di un istante -- il test torna rosso su
    `assert "ISTANTE" in ...`.
    """
    meaning = DEVICE_CLASS_MEANING[("sensor", "uptime")]
    assert "ISTANTE" in meaning
    assert "NON" in meaning


def test_entity_category_meaning_matches_the_source_word_for_word():
    """`ENTITY_CATEGORY_MEANING` deve essere ESATTAMENTE cio' che il
    sorgente dichiara -- non una parafrasi, non un riassunto.

    Mutazione: cambiare una lettera in `ENTITY_CATEGORY_MEANING["diagnostic"]`
    -- il test torna rosso su `assert ENTITY_CATEGORY_MEANING ==
    _SOURCE_ENTITY_CATEGORY_MEANING`.
    """
    assert ENTITY_CATEGORY_MEANING == _SOURCE_ENTITY_CATEGORY_MEANING


def test_entity_category_meaning_has_no_third_key():
    """Il sorgente dichiara SOLO `config` e `diagnostic` -- una terza chiave
    qui sarebbe una categoria che Home Assistant non conosce.

    Mutazione: aggiungere una chiave `"altro"` a `ENTITY_CATEGORY_MEANING`
    -- il test torna rosso su `assert set(ENTITY_CATEGORY_MEANING) ==
    {"config", "diagnostic"}`.
    """
    assert set(ENTITY_CATEGORY_MEANING) == {"config", "diagnostic"}


def test_the_measure_rule_fires_only_on_a_diagnostic_sensor_without_class_or_unit():
    """Il caso vero (`sensor.persons`, misurato il 06/09/2026): dominio
    `sensor`, categoria `diagnostic`, ne' classe ne' unita'.

    Mutazione: `entity_category_measure_rule` che ritorna sempre `None` --
    il test torna rosso su `assert rule is not None`."""
    rule = entity_category_measure_rule("sensor", "diagnostic", None, None)
    assert rule is not None
    assert "non e' una misura" in rule
    assert ENTITY_CATEGORY_MEANING["diagnostic"] in rule
    assert VOCABULARY_HA_VERSION in rule


def test_the_measure_rule_stays_silent_with_a_class_or_a_unit():
    """Una diagnostica con classe O con unita' e' gia' una misura
    dichiarata: la regola non ha niente da aggiungere.

    Mutazione: ignorare `device_class` (o `unit`) nella guardia -- il test
    torna rosso su uno dei due `assert ... is None`."""
    assert entity_category_measure_rule("sensor", "diagnostic", "battery", None) is None
    assert entity_category_measure_rule("sensor", "diagnostic", None, "%") is None


def test_the_measure_rule_stays_silent_off_sensor_and_off_diagnostic():
    """Fuori dal dominio `sensor` (tautologia strutturale, `device_tracker`
    misurato: 68/68 senza classe/unita') e fuori da `diagnostic` (un
    sensore primario senza classe/unita' non e' il caso misurato): in
    entrambi i casi la funzione non ha una regola da citare.

    Mutazione: allargare la guardia a un altro dominio o a un'altra
    categoria -- il test torna rosso su uno dei due `assert ... is None`."""
    assert entity_category_measure_rule("device_tracker", "diagnostic", None, None) is None
    assert entity_category_measure_rule("sensor", None, None, None) is None
