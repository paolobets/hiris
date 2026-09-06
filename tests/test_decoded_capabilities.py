"""`supported_features` decodificato in parole -- topology.decoded_capabilities.

Home Assistant lo dichiara come un intero A BIT il cui significato dipende
dal DOMINIO (`LightEntityFeature`, `UpdateEntityFeature`, ...). Le tabelle in
`topology._FEATURE_NAMES` sono verificate sul SORGENTE di Home Assistant, ai
due estremi della finestra che questo add-on dichiara di supportare:
`2024.7.0` (`hiris/config.yaml: homeassistant`) e `2026.9.1`, il tag stabile
piu' recente al momento di questa fetta -- mai su `dev`.

Due bit sono stati esclusi apposta perche' il sorgente li ha rimossi fra i
due tag (`ClimateEntityFeature.AUX_HEAT`, `VacuumEntityFeature.BATTERY`,
entrambi valore 64): decodificarli avrebbe affermato un significato che il
fornitore, per meta' della finestra supportata, non garantisce piu'.

CORREZIONE del 06/09/2026 (dubbio segnalato, poi misurato dal coordinatore):
la prima versione copriva i domini di `_DOMAIN_ATTRS` (una lista fatta per
un'ALTRA domanda) invece delle 181 entita' VERE che dichiarano
`supported_features` su questa casa. Contate per davvero: `update` (53) e
`light` (50) valgono da soli 103/181; `cover`/`fan`/`water_heater`/`vacuum`
-- i quattro della prima versione -- valgono ZERO. Le tabelle di
`update`/`notify`/`camera` sono nuove di questa correzione; `button` (16
entita' su questa casa) resta fuori perche' NESSUNA versione del sorgente
definisce un `ButtonEntityFeature` -- non e' un dominio dimenticato, e' un
dominio senza bit da decodificare."""
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


def test_decoded_capabilities_covers_the_domains_measured_on_this_house():
    """Le tabelle coprono i domini MISURATI il 06/09/2026 sulle 181 entita'
    vere che dichiarano `supported_features` su questa casa -- non un elenco
    dedotto da un'altra ragione. `update`/`light` da soli sono 103/181;
    `cover`/`fan`/`water_heater`/`vacuum` restano (verificati, corretti)
    anche se valgono zero qui -- una casa diversa li avra'.

    Mutazione: cancellare una voce da `_FEATURE_NAMES` (per esempio
    `"update"`, la piu' numerosa) -- il test torna rosso su
    `assert decoded_capabilities("update", 1) == ["installazione"]`."""
    assert decoded_capabilities("update", 1) == ["installazione"]
    assert decoded_capabilities("light", 4) == ["effetti"]
    assert decoded_capabilities("notify", 1) == ["titolo"]
    assert decoded_capabilities("camera", 1) == ["accensione"]
    assert decoded_capabilities("climate", 1) == ["temperatura_target"]
    assert decoded_capabilities("media_player", 1) == ["pausa"]
    assert decoded_capabilities("valve", 1) == ["apertura"]
    assert decoded_capabilities("weather", 1) == ["previsioni_giornaliere"]
    # Zero entita' su questa casa (06/09/2026), ma le tabelle restano
    # verificate e corrette -- una casa diversa le usera'.
    assert decoded_capabilities("cover", 1) == ["apertura"]
    assert decoded_capabilities("fan", 1) == ["velocita"]
    assert decoded_capabilities("water_heater", 1) == ["temperatura_target"]
    assert decoded_capabilities("vacuum", 1) == ["accensione"]


def test_decoded_capabilities_leaves_button_out_for_lack_of_a_source():
    """16 entita' su questa casa dichiarano `supported_features` nel dominio
    `button` (misurato il 06/09/2026) -- il secondo gruppo per grandezza
    dopo quelli con tabella. Ma NESSUNA versione del sorgente fra i due tag
    (`components/button/__init__.py` e `const.py`, entrambi verificati)
    definisce un `ButtonEntityFeature`: il dominio non ha bit da
    decodificare. Resta fuori per MANCANZA DI FONTE -- la stessa legge di
    `sensor` (vedi sopra), non una svista su un dominio numeroso.

    Mutazione: aggiungere una tabella inventata per `"button"` -- il test
    torna rosso su `assert decoded_capabilities("button", 1) == []`."""
    assert decoded_capabilities("button", 1) == []


def test_decoded_capabilities_decodes_update():
    """`update` e' il dominio PIU' numeroso su questa casa (53/181, misurato
    il 06/09/2026) -- la prima versione di questa tabella lo lasciava fuori
    per intero, avendo dedotto i domini invece di misurarli.

    Mutazione: cancellare `_FEATURE_NAMES["update"]` -- il test torna rosso
    su `assert decoded_capabilities("update", 9) == [...]` (`KeyError`
    a monte, lista vuota qui)."""
    assert sorted(decoded_capabilities("update", 9)) == ["backup", "installazione"]


def test_decoded_capabilities_decodes_notify_and_camera():
    """`notify` (11/181) e `camera` (9/181): terzo e quarto dominio per
    numero su questa casa, anch'essi assenti dalla prima versione.

    Mutazione: cancellare una delle due voci da `_FEATURE_NAMES` -- il test
    torna rosso sulla riga corrispondente."""
    assert decoded_capabilities("notify", 1) == ["titolo"]
    assert sorted(decoded_capabilities("camera", 3)) == ["accensione", "streaming"]
