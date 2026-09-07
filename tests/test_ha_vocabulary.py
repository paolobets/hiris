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
    ENTITY_CATEGORY_MEANING,
    STATE_CLASS_MEANING,
    UNAVAILABLE_LABEL,
    UNAVAILABLE_MEANING,
    UNKNOWN_LABEL,
    UNKNOWN_MEANING,
    VOCABULARY_HA_VERSION,
    VOCABULARY_SOURCE,
    entity_category_measure_rule,
    house_is_newer_than_vocabulary,
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


def test_the_version_and_the_source_cannot_drift_apart():
    """`VOCABULARY_HA_VERSION` e `VOCABULARY_SOURCE` sono due dichiarazioni
    dello STESSO fatto (il tag su cui il modulo e' stato verificato) scritte
    in due punti diversi: senza un legame, cambiare la prima senza
    riverificare la fonte (e senza aggiornare la seconda) resta verde mentre
    la fonte citata dice ancora il tag vecchio -- due idee della stessa
    versione che divergono in silenzio.

    Mutazione: cambiare `VOCABULARY_HA_VERSION` in `"2027.1.0"` senza
    toccare `VOCABULARY_SOURCE` (che continua a citare `2026.9.1`) -- il
    test torna rosso su `assert VOCABULARY_HA_VERSION in VOCABULARY_SOURCE`.
    """
    assert VOCABULARY_HA_VERSION in VOCABULARY_SOURCE


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


def test_a_house_on_the_next_calendar_release_is_reported_as_newer():
    """Il confine VERO, non un caso di scuola: Home Assistant usa CalVer
    (anno.mese.patch), e la release dopo `2026.9.1` e' `2026.10.0` -- la
    prossima in assoluto. Un confronto LESSICOGRAFICO (stringa contro
    stringa) direbbe che `"2026.10.0"` e' PIU' VECCHIO di `"2026.9.1"`,
    perche' `'1'` (il primo carattere di `"10"`) e' minore di `'9'` come
    carattere: il primo giorno in cui questo meccanismo serve davvero (la
    prima release dopo quella pinnata) sarebbe il primo giorno in cui si
    romperebbe, in silenzio.

    Mutazione: sostituire il confronto CalVer a tuple con uno lessicografico
    a stringhe (`older = house_ha_version > VOCABULARY_HA_VERSION`) -- il
    test torna rosso su `assert note["vocabolario_piu_vecchio_della_casa"]
    is True` (con la mutazione, risulta `False`: `"2026.10.0" < "2026.9.1"`
    come stringhe).
    """
    note = house_is_newer_than_vocabulary("2026.10.0")
    assert note["vocabolario_piu_vecchio_della_casa"] is True


def test_a_house_one_patch_ahead_is_reported_as_newer():
    """Il TERZO campo di CalVer (anno.mese.PATCH, come promette il docstring
    di `_parsed_version`) non e' un dettaglio: `2026.9.2` e' la release
    successiva a `2026.9.1` senza cambiare ne' anno ne' mese. Un confronto
    che si fermasse ai primi due campi (anno, mese) direbbe che le due
    versioni sono "uguali" -- non "piu' vecchia", ma nemmeno "piu' nuova" --
    e la casa sarebbe gia' avanti senza che nessuno lo sappia.

    Mutazione: confrontare solo i primi due campi
    (`_parsed_version(house_ha_version)[:2] > _parsed_version(VOCABULARY_HA_VERSION)[:2]`)
    -- il test torna rosso su `assert note["vocabolario_piu_vecchio_della_casa"]
    is True` (con la mutazione, risulta `False`: anno e mese sono identici,
    il patch non viene mai guardato).
    """
    note = house_is_newer_than_vocabulary("2026.9.2")
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


def test_le_due_etichette_brevi_dicono_le_stesse_due_cose_delle_spiegazioni():
    """Fetta «lo stato» (07/09/2026): la stessa distinzione, in una lunghezza
    che sta in una riga accanto a un episodio. Sono DUE lunghezze di un fatto
    solo, non due fatti: se le due etichette collassassero sulla stessa
    parola, la pagina appiattirebbe cio' che le spiegazioni qui sopra
    esistono per distinguere.

    Mutazione ESEGUITA: `UNKNOWN_LABEL = UNAVAILABLE_LABEL` -- il test torna
    rosso su `assert UNAVAILABLE_LABEL != UNKNOWN_LABEL`.
    """
    assert UNAVAILABLE_LABEL
    assert UNKNOWN_LABEL
    assert UNAVAILABLE_LABEL != UNKNOWN_LABEL
    # Un'etichetta e' cio' che sta in una riga: se diventasse una frase,
    # sarebbe un doppione della spiegazione qui sopra, non la sua forma breve.
    assert len(UNAVAILABLE_LABEL) < 40
    assert len(UNKNOWN_LABEL) < 40
    assert UNAVAILABLE_LABEL != UNAVAILABLE_MEANING
    assert UNKNOWN_LABEL != UNKNOWN_MEANING


def test_la_fonte_dichiara_PERCHE_le_due_etichette_sono_nostre():
    """Le due etichette esistono solo perche' Home Assistant non le manda, e
    la prova di quel buco e' una riga di sorgente: `translation.py:469-470`,
    dove `async_translate_state` restituisce `unavailable`/`unknown` grezzi
    prima di guardare qualunque tabella. Senza questa citazione dentro
    `VOCABULARY_SOURCE`, fra sei mesi le due etichette si leggerebbero come
    una traduzione fatta a mano al posto di HA -- cioe' come un difetto.

    Mutazione ESEGUITA: togliere la citazione di `translation.py` da
    `VOCABULARY_SOURCE` -- il test torna rosso su
    `assert "helpers/translation.py:469-470" in VOCABULARY_SOURCE`.
    """
    assert "helpers/translation.py:469-470" in VOCABULARY_SOURCE
    assert "async_translate_state" in VOCABULARY_SOURCE


# --- `entity_category`: pinnato contro la fonte, non contro se stesso ------
# (Task 5, §6c -- il primo consumatore a runtime del vocabolario)


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
