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
import pytest

from hiris.app.proxy.ha_client import HAClient


class _FakeConnection:
    """La stessa finta di `test_ha_client_related_problems.py` (che copre
    `related()` e `problems()`): non se ne inventa una nuova per verticale."""

    def __init__(self, response=None, raises=False):
        self.response = response
        self.raises = raises
        self.commands = []

    async def _ws_batch(self, commands, timeout=10.0):
        self.commands.extend(commands)
        if self.raises:
            raise OSError("HA muto")
        return [self.response]


def _client(fake):
    c = HAClient.__new__(HAClient)
    c._ws_batch = fake._ws_batch
    return c


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

    Mutazione: proiettare le righe su un sottoinsieme di campi -- il test
    torna rosso su `assert entry["count"] == 3`.
    """
    row = _entry(name="zwave_js.const", level="WARNING", count=3,
                 first_occurred=1699999000.0, timestamp=1700000500.0)
    fake = _FakeConnection({"result": [row]})
    outcome = await _client(fake).system_log()
    entry = outcome["voci"][0]
    assert entry["name"] == "zwave_js.const"
    assert entry["level"] == "WARNING"
    assert entry["count"] == 3
    assert entry["first_occurred"] == 1699999000.0
    assert entry["timestamp"] == 1700000500.0
    assert fake.commands[0] == ("system_log/list", None)
    # La proprieta' che la docstring dichiara e' «senza proiezioni»: gli
    # assert sopra bastano a coprire la mutazione dichiarata, ma non a
    # sorvegliare `message`, `source`, `exception` -- una proiezione che
    # lasciasse cadere proprio `message` passerebbe verde. La riga intera,
    # identica a quella data alla finta, chiude la lacuna.
    assert outcome["voci"] == [row]


@pytest.mark.asyncio
async def test_a_failed_read_says_error_not_an_empty_log():
    """Un elenco vuoto significherebbe «non c'e' niente che non va»: e' la
    stessa bugia che `get_error_log` diceva restituendo zeri, ed e' il motivo
    per cui quel metodo e' uscito (v3.15.0).

    Mutazione: tornare `{"voci": []}` invece di `{"errore": ...}` -- il test
    torna rosso su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(raises=True)
    outcome = await _client(fake).system_log()
    assert "errore" in outcome
    assert "voci" not in outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("fake,why", [
    (_FakeConnection(raises=True), "connessione caduta"),
    (_FakeConnection({"error": {"message": "non trovato"}}), "HA ha rifiutato"),
    (_FakeConnection({"result": {"issues": "non una lista nuda"}}),
     "forma inattesa: HA non manda un dizionario qui"),
])
async def test_every_failure_shape_says_error_not_an_empty_log(fake, why):
    """Le tre forme di guasto che `problems()` e `related()` gia' sorvegliano,
    ripetute qui: connessione caduta, rifiuto esplicito di HA, e una risposta
    di forma inattesa (qui il caso proprio del log: un dizionario al posto
    della lista nuda che manda davvero `list_errors`).

    Mutazione: togliere il controllo `isinstance(result, list)` -- il caso
    `fake2` (forma inattesa) torna rosso su
    `assert "errore" in outcome, why`.
    """
    outcome = await _client(fake).system_log()
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
    fake = _FakeConnection({"result": []})
    outcome = await _client(fake).system_log()
    assert outcome == {"voci": []}
