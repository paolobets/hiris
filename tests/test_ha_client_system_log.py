"""Il registro degli errori che Home Assistant ha gia' raccolto.

`HAClient.system_log()` legge `system_log/list` -- la stessa disciplina di
`problems()` e `related()`, verificata identica alla fonte
(`homeassistant/components/system_log/__init__.py`, funzione `list_errors`):

1. **il client legge, non giudica**: le righe escono coi campi di HA, senza
   proiezioni -- cosa dire e cosa tacere e' di chi compone, non di questo
   metodo;
2. **un elenco vuoto su errore sarebbe una bugia** -- «non c'e' niente nel
   registro» -- quindi un guasto di lettura torna `{"errore": ...}`, mai
   `{"voci": []}`.

Una differenza di forma rispetto a `problems()`: qui il risultato di HA e'
una LISTA nuda (`connection.send_result(msg["id"],
hass.data[DOMAIN].records.to_list())`), non un dizionario con una chiave
come `{"issues": [...]}`. Le prove sulla forma inattesa lo sorvegliano.
"""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

SYSTEM_LOG = "system_log/list"


def _house(rows=None, **injected) -> CasaFinta:
    """La casa finta (D8), la stessa di `test_ha_client_related_problems.py`:
    il client vero, e Home Assistant che manda `rows` come lista nuda."""
    inputs = {} if rows is None else {"system_log": {"voci": rows}}
    return CasaFinta(inputs, **injected)


def _entry(**fields):
    """Una riga del registro nella forma vera di `LogEntry.to_dict()`
    (`homeassistant/components/system_log/__init__.py`, verificata alla
    fonte): `source` e' una coppia (file, riga), non una stringa."""
    row = {"name": "homeassistant.core", "message": ["errore generico"],
           "level": "ERROR", "source": ["homeassistant/core.py", 512],
           "timestamp": 1700000000.0, "exception": "",
           "count": 1, "first_occurred": 1700000000.0}
    row.update(fields)
    return row


@pytest.mark.asyncio
async def test_the_system_log_is_read_as_home_assistant_sends_it():
    """Il client legge e non giudica: le righe escono coi campi di HA, `count`
    e `first_occurred` compresi -- la deduplicazione e' gia' stata fatta da
    lui, e non e' il client a poterla disfare.

    Mutazione: proiettare le righe su un sottoinsieme di campi che scarta
    `count` -- il test torna rosso su `assert entry["count"] == 3`. Una
    proiezione che scartasse solo `message`, o che cancellasse un campo SUL
    POSTO, arrossisce piu' in basso, su `assert outcome["voci"] ==
    [expected]`.
    """
    row = _entry(name="zwave_js.const", level="WARNING", count=3,
                 first_occurred=1699999000.0, timestamp=1700000500.0)
    # Il confronto in fondo deve reggere anche contro un client che modifica
    # le righe SUL POSTO: senza questa copia, `row` e la riga in uscita sono
    # lo STESSO oggetto, e un `r.pop("message")` dentro il client passerebbe
    # verde -- misurato, non temuto.
    expected = copy.deepcopy(row)
    house = _house([row])
    outcome = await house.system_log()
    entry = outcome["voci"][0]
    assert entry["name"] == "zwave_js.const"
    assert entry["level"] == "WARNING"
    assert entry["count"] == 3
    assert entry["first_occurred"] == 1699999000.0
    assert entry["timestamp"] == 1700000500.0
    assert house.calls == [(SYSTEM_LOG, None)]
    # La proprieta' che la docstring dichiara e' «senza proiezioni»: gli
    # assert sopra bastano a coprire la mutazione dichiarata, ma non a
    # sorvegliare `message`, `source`, `exception` -- una proiezione che
    # lasciasse cadere proprio `message` passerebbe verde. La riga intera,
    # confrontata con una COPIA fatta prima della chiamata, chiude la lacuna:
    # confrontarla con `row` non basterebbe, perche' e' lo stesso oggetto.
    assert outcome["voci"] == [expected]


@pytest.mark.asyncio
async def test_a_failed_read_says_error_not_an_empty_log():
    """Un elenco vuoto significherebbe «non c'e' niente che non va»: e' la
    stessa bugia che `get_error_log` diceva restituendo zeri, ed e' il motivo
    per cui quel metodo e' uscito (v3.15.0).

    Mutazione: tornare `{"voci": []}` invece di `{"errore": ...}` -- il test
    torna rosso su `assert "errore" in outcome`.
    """
    outcome = await _house(silence={SYSTEM_LOG}).system_log()
    assert "errore" in outcome
    assert "voci" not in outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("injected,why", [
    ({"silence": {SYSTEM_LOG}}, "connessione caduta"),
    ({"refuse": {SYSTEM_LOG: {"code": "not_found", "message": "non trovato"}}},
     "HA ha rifiutato"),
    ({"answers": {SYSTEM_LOG: lambda extra: {"issues": "non una lista nuda"}}},
     "forma inattesa: HA non manda un dizionario qui"),
])
async def test_every_failure_shape_says_error_not_an_empty_log(injected, why):
    """Le tre forme di guasto che `problems()` e `related()` gia' sorvegliano,
    ripetute qui: connessione caduta, rifiuto esplicito di HA, e una risposta
    di forma inattesa (qui il caso proprio del log: un dizionario al posto
    della lista nuda che manda davvero `list_errors`).

    Mutazione: togliere il controllo `isinstance(result, list)` -- il caso
    della forma inattesa torna rosso su `assert "errore" in outcome, why`.
    """
    outcome = await _house(**injected).system_log()
    assert "errore" in outcome, why
    assert "voci" not in outcome


@pytest.mark.asyncio
async def test_an_empty_log_stays_empty_not_an_error():
    """L'altra meta' della disciplina che apre il file: il vuoto non e' un
    errore, quanto l'errore non e' un vuoto. Una casa senza righe recenti in
    `DedupStore` ha davvero `records.to_list() == []`
    (`homeassistant/components/system_log/__init__.py`), e deve restare
    `{"voci": []}` -- scambiarlo per un guasto sarebbe la stessa bugia
    all'incontrario.

    Mutazione: `if not result: return {"errore": "..."}` subito dopo il
    controllo di forma -- il test torna rosso su
    `assert outcome == {"voci": []}`.
    """
    outcome = await _house([]).system_log()
    assert outcome == {"voci": []}
