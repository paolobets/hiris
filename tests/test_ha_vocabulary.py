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
tag `2026.9.1` -- vedi `ha_vocabulary.VOCABULARY_SOURCE` per la citazione
file per file.
"""
from hiris.app.home_space.ha_vocabulary import (
    DEVICE_CLASS_MEANING,
    STATE_CLASS_MEANING,
    UNAVAILABLE_MEANING,
    UNKNOWN_MEANING,
    VOCABULARY_HA_VERSION,
    VOCABULARY_SOURCE,
    house_is_newer_than_vocabulary,
)

# Le 27 coppie (dominio, classe) misurate su questa casa il 07/09/2026 --
# ricopiate a mano dal risultato della misura, non lette da
# `DEVICE_CLASS_MEANING`. Le CINQUE classi di `binary_sensor` misurate sulla
# stessa casa (`motion`, `connectivity`, `running`, `occupancy`, `plug` -- 33
# entita') NON compaiono qui apposta: hanno gia' un significato in
# `topology._CLASS_MEANING`, e questo vocabolario non le duplica (vedi il
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


def test_the_vocabulary_declares_where_it_comes_from():
    """«Non si deduce e non si indovina: si importa, si dichiara la fonte, e
    una prova si accorge quando diverge.» Un vocabolario senza fonte e'
    un'opinione con l'aspetto di un fatto.

    Mutazione: svuotare `VOCABULARY_SOURCE` (`= ""`) -- il test torna rosso
    su `assert VOCABULARY_SOURCE`.
    """
    assert VOCABULARY_SOURCE
    assert "2026.9.1" in VOCABULARY_SOURCE
    assert "dev" not in VOCABULARY_SOURCE.split()


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


def test_a_house_newer_than_the_vocabulary_is_a_fact_not_an_error():
    """Non e' un guasto ed e' inutile gridarlo: e' un fatto misurabile,
    detto una volta, che invita a rileggere la documentazione.

    Mutazione: far sollevare `house_is_newer_than_vocabulary` invece di
    dichiarare (per esempio `raise ValueError(...)` al posto del `return`) --
    il test torna rosso perche' la chiamata solleva invece di restituire un
    dizionario con `assert nota["vocabolario_piu_vecchio_della_casa"] is True`.
    """
    note = house_is_newer_than_vocabulary("2099.1.0")
    assert note["vocabolario_piu_vecchio_della_casa"] is True


def test_a_house_at_the_same_version_is_not_reported_as_newer():
    """La casa che HA misurato il vocabolario (`VOCABULARY_HA_VERSION`
    stesso) non e' "piu' vecchia di se stessa": il confronto deve essere
    stretto, non largo.

    Mutazione: cambiare il confronto da `>` a `>=` in
    `house_is_newer_than_vocabulary` -- il test torna rosso su
    `assert note["vocabolario_piu_vecchio_della_casa"] is False`.
    """
    note = house_is_newer_than_vocabulary(VOCABULARY_HA_VERSION)
    assert note["vocabolario_piu_vecchio_della_casa"] is False


def test_a_house_older_than_the_vocabulary_is_not_reported_as_newer():
    """Il minimo dichiarato da `hiris/config.yaml` (`2024.7.0`) e' PIU'
    VECCHIO del vocabolario (`2026.9.1`): una casa che parte da li' non deve
    mai leggersi "piu' nuova".

    Mutazione: invertire l'ordine del confronto (`_parsed_version(VOCABULARY_HA_VERSION)
    > _parsed_version(house_ha_version)`, scambiando i due argomenti) -- il
    test torna rosso su `assert note["vocabolario_piu_vecchio_della_casa"] is False`.
    """
    note = house_is_newer_than_vocabulary("2024.7.0")
    assert note["vocabolario_piu_vecchio_della_casa"] is False


def test_a_house_with_no_version_read_yet_is_not_reported_as_newer():
    """Una casa il cui sistema di riferimento non e' mai stato letto
    (`versione_ha` assente) non e' "piu' vecchia" ne' "piu' nuova": e' "non
    lo so", e affermare un confronto su un dato mancante sarebbe indovinare.

    Mutazione: togliere la guardia `if not house_ha_version` -- il test
    torna rosso (l'assert sotto non vede piu' `False`, o la chiamata solleva
    perche' `_parsed_version(None)` itera su un `None`).
    """
    note = house_is_newer_than_vocabulary(None)
    assert note["vocabolario_piu_vecchio_della_casa"] is False
    note_empty = house_is_newer_than_vocabulary("")
    assert note_empty["vocabolario_piu_vecchio_della_casa"] is False


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
    `topology._CLASS_MEANING`: un doppione qui violerebbe la fondamenta
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


def test_unavailable_and_unknown_are_two_different_documented_facts():
    """Il terzo pezzo del "vocabolario che HA documenta e non manda":
    `unavailable` e `unknown` non sono sinonimi -- uno dice che
    l'integrazione non e' raggiungibile, l'altro che lo e' ma il valore non
    e' ancora noto. Verificato alla fonte (`entity.py::_stringify_state`,
    tag `2026.9.1`): l'ordine dei due controlli nel sorgente e' esattamente
    "prima `available`, poi il valore".

    Mutazione: rendere `UNKNOWN_MEANING` uguale a `UNAVAILABLE_MEANING` (o
    svuotarne uno) -- il test torna rosso su
    `assert UNAVAILABLE_MEANING != UNKNOWN_MEANING`.
    """
    assert UNAVAILABLE_MEANING
    assert UNKNOWN_MEANING
    assert UNAVAILABLE_MEANING != UNKNOWN_MEANING
    assert "available" in UNAVAILABLE_MEANING.lower() or "raggiungibile" in UNAVAILABLE_MEANING
    assert "none" in UNKNOWN_MEANING.lower() or "non" in UNKNOWN_MEANING.lower()
