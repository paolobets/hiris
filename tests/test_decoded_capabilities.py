"""`supported_features` decodificato in parole -- topology.decoded_capabilities.

Home Assistant lo dichiara come un intero A BIT il cui significato dipende
dal DOMINIO (`LightEntityFeature`, `CoverEntityFeature`, ...). Le tabelle in
`topology._FEATURE_NAMES` sono verificate sul SORGENTE di Home Assistant, ai
due estremi della finestra che questo add-on dichiara di supportare:
`2024.7.0` (`hiris/config.yaml: homeassistant`) e `2026.9.1`, il tag stabile
piu' recente al momento di questa fetta -- mai su `dev`.

Due bit sono stati esclusi apposta perche' il sorgente li ha rimossi fra i
due tag (`ClimateEntityFeature.AUX_HEAT`, `VacuumEntityFeature.BATTERY`,
entrambi valore 64): decodificarli avrebbe affermato un significato che il
fornitore, per meta' della finestra supportata, non garantisce piu'.
"""
from hiris.app.home_space.topology import decoded_capabilities


def test_decoded_capabilities_decodes_a_known_domain_bitmask():
    """32 e' `LightEntityFeature.TRANSITION` (`components/light/const.py`,
    verificato sui tag `2024.7.0` e `2026.9.1`: il valore non e' cambiato).

    Mutazione: restituire sempre `[]` -- il test torna rosso su
    `assert decoded_capabilities("light", 32) == ["transizione"]`."""
    assert decoded_capabilities("light", 32) == ["transizione"]


def test_decoded_capabilities_decodes_every_bit_set():
    """`EFFECT(4) | FLASH(8)` -- due bit insieme, non uno: una decodifica che
    si fermasse al primo bit trovato lascerebbe l'altro invisibile.

    Mutazione: `next(... for ...)` al posto della comprensione (un solo
    nome anche con piu' bit accesi) -- il test torna rosso su
    `assert sorted(decoded_capabilities("light", 12)) == ["effetti", "flash"]`."""
    assert sorted(decoded_capabilities("light", 12)) == ["effetti", "flash"]


def test_decoded_capabilities_is_empty_for_a_domain_without_a_verified_source():
    """`sensor` non ha nessun `EntityFeature` alla fonte: nessuna tabella,
    quindi nessuna decodifica -- MAI un'ipotesi su un bit non verificato.

    Mutazione: un ripiego (`_FEATURE_NAMES.get(domain, _FEATURE_NAMES["light"])`)
    che decodifica con la tabella di un altro dominio quando quello vero
    manca -- il test torna rosso su
    `assert decoded_capabilities("sensor", 32) == []`."""
    assert decoded_capabilities("sensor", 32) == []


def test_decoded_capabilities_ignores_a_non_integer_value():
    """Un'integrazione che manda `supported_features` fuori forma (stringa,
    `None`, un dizionario) non deve far esplodere la decodifica -- e non
    deve nemmeno inventare un significato: `[]`, non un errore.

    Mutazione: togliere il controllo `isinstance(supported_features, int)`
    -- il test solleva `TypeError` invece di tornare `[]`."""
    assert decoded_capabilities("light", None) == []
    assert decoded_capabilities("light", "32") == []


def test_decoded_capabilities_does_not_decode_the_excluded_climate_bit():
    """`ClimateEntityFeature.AUX_HEAT` valeva 64 a `2024.7.0` -- rimosso dal
    sorgente a `2026.9.1` (`components/climate/const.py`, nessuna delle due
    versioni lo dichiara entrambe). Decodificarlo affermerebbe un significato
    che il fornitore non garantisce per l'intera finestra supportata.

    Mutazione: rimettere `64: "riscaldamento_ausiliario"` in
    `_FEATURE_NAMES["climate"]` -- il test torna rosso su
    `assert decoded_capabilities("climate", 64) == []`."""
    assert decoded_capabilities("climate", 64) == []


def test_decoded_capabilities_does_not_decode_the_excluded_vacuum_bit():
    """`VacuumEntityFeature.BATTERY` valeva 64 a `2024.7.0`, sparito dal
    sorgente a `2026.9.1` (`components/vacuum/const.py`) -- stessa sorte di
    `AUX_HEAT` sul climate, stessa ragione dell'esclusione.

    Mutazione: rimettere `64: "livello_batteria"` in
    `_FEATURE_NAMES["vacuum"]` -- il test torna rosso su
    `assert decoded_capabilities("vacuum", 64) == []`."""
    assert decoded_capabilities("vacuum", 64) == []


def test_decoded_capabilities_covers_every_domain_this_house_has():
    """Le tabelle coprono gli stessi domini di
    `proxy/entity_cache.py::_DOMAIN_ATTRS` (misurati come domini che QUESTA
    casa ha davvero, fetta "attributi al modello" 2026-08-25) piu' `weather`
    -- non un dominio in piu', non uno in meno: un dominio senza fonte
    verificata resta fuori per dichiarazione esplicita, non per
    dimenticanza.

    Mutazione: cancellare una voce da `_FEATURE_NAMES` (per esempio
    `"valve"`) -- il test torna rosso su
    `assert decoded_capabilities("valve", 1) == ["apertura"]`."""
    assert decoded_capabilities("climate", 1) == ["temperatura_target"]
    assert decoded_capabilities("cover", 1) == ["apertura"]
    assert decoded_capabilities("media_player", 1) == ["pausa"]
    assert decoded_capabilities("vacuum", 1) == ["accensione"]
    assert decoded_capabilities("fan", 1) == ["velocita"]
    assert decoded_capabilities("water_heater", 1) == ["temperatura_target"]
    assert decoded_capabilities("valve", 1) == ["apertura"]
    assert decoded_capabilities("weather", 1) == ["previsioni_giornaliere"]
