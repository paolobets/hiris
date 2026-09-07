"""Il difetto trovato dalla review indipendente sul Task 3 (06/09/2026).

`supported_features`/`assumed_state` uscivano DUE volte da `guarda('entita',
...)`: una decodificata (`capacita'`/`stato_presunto`, dentro
`_enrich_entity`) e una GREZZA, dentro `attributi` -- il dizionario che
`_view_entity` scarica per intero dallo specchio dello stato. Misurato sulla
catena vera:

    light.cucina_1  sf=0   -> {"attributi": {"supported_features": 0}}
    light.cucina_1  sf=36  -> {"capacita": [...], "attributi":
                               {"supported_features": 36}}
    sensor.cucina_t sf=27  -> {"attributi": {"supported_features": 27}}

Tre difetti in uno: `supported_features: 0` e' un metadato senza niente da
dire (la legge di questo task lo vieta); su un dominio senza tabella il
modello riceve il numero NUDO (un invito a indovinare, cio' che questo task
esiste per togliere); dove `capacita'` esce gia' decodificata, il grezzo
usciva ACCANTO -- un doppione.

NESSUNA prova se ne accorgeva perche' tutte costruivano `reported_attributes`
a mano, saltando `entity_cache._to_minimal` -- la trappola dello stato
condiviso pigro: la finta popolava esattamente cio' che in produzione popola
un altro anello. Questo file segue la CATENA VERA -- stato grezzo di Home
Assistant -> `_to_minimal` -> `live_mirror` -> `view()` -- stessa disciplina
di `test_attributes_to_model.py` (il difetto gemello sul termostato).
"""
from hiris.app.home_space.queries import view
from hiris.app.home_space.topology import live_mirror
from hiris.app.proxy.entity_cache import _to_minimal

_CASA = {
    "aree": [{"id": "cucina", "nome": "Cucina"}],
    "entita": [
        {"id": "light.con_capacita", "nome": "Luce con capacita'",
         "area_id": "cucina", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
        {"id": "light.senza_bit", "nome": "Luce senza bit acceso",
         "area_id": "cucina", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
        {"id": "sensor.senza_tabella", "nome": "Sensore senza tabella",
         "area_id": "cucina", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
        {"id": "select.con_opzioni", "nome": "Select con opzioni",
         "area_id": "cucina", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
    ],
    "dispositivi": [],
}


def _mirror_of(*raw_states):
    minimal = [_to_minimal(raw) for raw in raw_states]
    return live_mirror(minimal)


def _every_attribute_shown(detail: dict) -> dict:
    """Tutto cio' che il modello vede sotto `attributi`, in un dizionario
    piatto -- le tre ceste fuse.

    Serve perche' dalla fetta dell'eredita' (07/09/2026) `attributi` ha una
    forma a ceste (`campo_di_manovra`/`valori`/`non_interpretati`/
    `trattenuti`): un `assert "supported_features" not in detail["attributi"]`
    scritto sulla forma vecchia passerebbe SEMPRE -- guarderebbe i nomi delle
    ceste, non i nomi degli attributi -- ed e' un test che non puo' piu'
    fallire, il difetto n.1 di questo progetto.
    """
    shown: dict = {}
    for content in (detail.get("attributi") or {}).values():
        shown.update(content)
    return shown


def test_the_real_chain_decodes_capabilities_and_does_not_leak_the_raw_bit():
    """`light.con_capacita` dichiara `supported_features: 36` (EFFECT=4 +
    TRANSITION=32, `LightEntityFeature`, verificato) attraverso la catena
    VERA, non un `reported_attributes` scritto a mano.

    Mutazione: rimettere `supported_features`/`assumed_state` dentro
    `_RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR` vuoto (farli passare in
    `attributi`) -- il test torna rosso su
    `assert "supported_features" not in detail.get("attributi", {})`."""
    raw = {"entity_id": "light.con_capacita", "state": "on",
           "attributes": {"friendly_name": "Luce con capacita'",
                          "supported_features": 36, "assumed_state": True}}
    state, names, unit, classes, since, attributes = _mirror_of(raw)
    detail = view(_CASA, [], [], state, "entita", "light.con_capacita",
                   fallback_names=names, reported_units=unit,
                   reported_classes=classes, reported_since_when=since,
                   reported_attributes=attributes)
    assert sorted(detail["capacita"]) == ["effetti", "transizione"]
    assert detail["stato_presunto"] is True
    shown = _every_attribute_shown(detail)
    assert "supported_features" not in shown
    assert "assumed_state" not in shown


def test_supported_features_zero_does_not_come_out_anywhere():
    """`supported_features: 0` -- l'integrazione dichiara il campo ma non
    accende nessun bit -- e' il metadato che non ha niente da dire: non deve
    comparire ne' come `capacita'` (gia' vero, `decoded_capabilities` torna
    `[]`) ne' come numero grezzo dentro `attributi`.

    Mutazione: lasciare `supported_features`/`assumed_state` dentro il
    dizionario che diventa `attributi` -- il test torna rosso su
    `assert "attributi" not in detail` (comparirebbe
    `{"attributi": {"supported_features": 0}}`)."""
    raw = {"entity_id": "light.senza_bit", "state": "off",
           "attributes": {"friendly_name": "Luce senza bit acceso",
                          "supported_features": 0}}
    state, names, unit, classes, since, attributes = _mirror_of(raw)
    detail = view(_CASA, [], [], state, "entita", "light.senza_bit",
                   fallback_names=names, reported_units=unit,
                   reported_classes=classes, reported_since_when=since,
                   reported_attributes=attributes)
    assert "capacita" not in detail
    assert "attributi" not in detail


def test_a_raw_number_never_reaches_the_model_for_an_uncovered_domain():
    """`sensor` non ha nessuna tabella verificata: `supported_features: 27`
    (un valore vero, misurato su questa casa in un dominio senza fonte) non
    deve uscire come numero nudo -- e' esattamente l'invito a indovinare che
    questo task esiste per togliere.

    Mutazione: la stessa di sopra (lasciare le due chiavi dentro
    `attributi`) -- il test torna rosso su
    `assert "attributi" not in detail` (comparirebbe
    `{"attributi": {"supported_features": 27}}`)."""
    raw = {"entity_id": "sensor.senza_tabella", "state": "21.5",
           "attributes": {"friendly_name": "Sensore senza tabella",
                          "supported_features": 27}}
    state, names, unit, classes, since, attributes = _mirror_of(raw)
    detail = view(_CASA, [], [], state, "entita", "sensor.senza_tabella",
                   fallback_names=names, reported_units=unit,
                   reported_classes=classes, reported_since_when=since,
                   reported_attributes=attributes)
    assert "capacita" not in detail
    assert "attributi" not in detail


def test_options_is_the_one_lawful_door_even_next_to_the_other_two():
    """`options` NON ha nessun'altra porta -- deve restare dentro
    `attributi`, anche quando la stessa entita' porta anche
    `supported_features`/`assumed_state` (che invece devono restare fuori).

    Dalla fetta dell'eredita' esce sotto `campo_di_manovra`, e non e' un
    dettaglio di nome: `SelectEntityCapabilityAttribute.OPTIONS` sono i valori
    che si possono IMPORRE a quell'entita', cioe' esattamente il campo di
    manovra di un `select`.

    Mutazione: filtrare `options` insieme alle altre due (ampliare
    `_RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR` per errore) -- il test torna
    rosso su `assert detail["attributi"]["campo_di_manovra"]["options"] ==
    ["eco", "comfort"]` (`KeyError: 'attributi'`)."""
    raw = {"entity_id": "select.con_opzioni", "state": "eco",
           "attributes": {"friendly_name": "Select con opzioni",
                          "options": ["eco", "comfort"],
                          "supported_features": 0, "assumed_state": True}}
    state, names, unit, classes, since, attributes = _mirror_of(raw)
    detail = view(_CASA, [], [], state, "entita", "select.con_opzioni",
                   fallback_names=names, reported_units=unit,
                   reported_classes=classes, reported_since_when=since,
                   reported_attributes=attributes)
    assert detail["attributi"]["campo_di_manovra"]["options"] == ["eco", "comfort"]
    shown = _every_attribute_shown(detail)
    assert "supported_features" not in shown
    assert "assumed_state" not in shown
    assert detail["stato_presunto"] is True
