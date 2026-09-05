"""«Com'e' andata questa automazione?»

`HAClient.automation_traces()` legge `trace/list` (le esecuzioni RECENTI, in
breve), `HAClient.automation_trace()` legge `trace/get` (UNA esecuzione,
per intero) -- stessa disciplina di `problems()` e `system_log()`, verificata
identica alla fonte (`homeassistant/components/trace/websocket_api.py`,
funzioni `websocket_trace_list`/`websocket_trace_get`; `trace/util.py`,
`async_list_traces`/`async_get_trace`; `trace/models.py`,
`ActionTrace.as_short_dict`/`as_extended_dict`):

1. **il client legge, non giudica**: le righe escono coi campi di HA, senza
   proiezioni -- cosa dire e cosa tacere e' di chi compone, non di questi
   metodi;
2. **un elenco (o un dizionario) vuoto su errore sarebbe una bugia** -- un
   guasto di lettura torna `{"errore": ...}`, mai un vuoto.

Una differenza di forma fra i due comandi, verificata alla fonte e non
copiata dal capitolato: `trace/list` risponde con una LISTA NUDA (come
`system_log/list`), `trace/get` con un DIZIONARIO (come `repairs/list_issues`)
-- ciascuno ha quindi la propria prova sulla forma inattesa.
"""
import copy

import pytest

from hiris.app.proxy.ha_client import HAClient


class _FakeConnection:
    """La stessa finta di `test_ha_client_system_log.py` (e di
    `test_ha_client_related_problems.py`): non se ne inventa una nuova per
    verticale."""

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


def _short_trace(**fields):
    """Una riga di `trace/list` nella forma vera di
    `ActionTrace.as_short_dict()` (`homeassistant/components/trace/models.py`,
    verificata alla fonte)."""
    row = {"last_step": "trigger/0", "run_id": "abc123", "state": "stopped",
           "script_execution": "success",
           "timestamp": {"start": "2026-09-05T10:00:00+00:00",
                         "finish": "2026-09-05T10:00:01+00:00"},
           "domain": "automation", "item_id": "luci_sera"}
    row.update(fields)
    return row


def _extended_trace(**fields):
    """Una riga di `trace/get` nella forma vera di
    `ActionTrace.as_extended_dict()` (stessa fonte): tutto quello che ha
    `as_short_dict()` piu' `trace`, `config`, `blueprint_inputs`, `context`."""
    row = _short_trace()
    row.update({"trace": {"trigger/0": [{"path": "trigger/0", "result": {}}]},
                "config": {"id": "luci_sera"}, "blueprint_inputs": None,
                "context": {"id": "ctx1", "parent_id": None, "user_id": None}})
    row.update(fields)
    return row


# --------------------------------------------------------------------------
# automation_traces() -- trace/list
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_automation_traces_are_read_as_home_assistant_sends_them():
    """Il client legge e non giudica: le righe escono coi campi di HA, e il
    comando manda `domain`/`item_id` SEPARATI (spaccati dall'`entity_id` sul
    primo punto, come fa HA stesso in `websocket_trace_list`), non
    l'`entity_id` intero.

    Mutazione: proiettare le righe su un sottoinsieme di campi che scarta
    `script_execution` -- il test torna rosso su
    `assert trace["script_execution"] == "failed"`. Una proiezione che
    scartasse solo `last_step`, o che modificasse le righe SUL POSTO,
    arrossisce piu' in basso, su `assert outcome["tracce"] == [expected]`.
    """
    row = _short_trace(run_id="xyz", state="stopped",
                       script_execution="failed")
    # Copia fatta PRIMA della chiamata: un client che modificasse la riga sul
    # posto passerebbe verde se confrontato con `row` stesso.
    expected = copy.deepcopy(row)
    fake = _FakeConnection({"result": [row]})
    outcome = await _client(fake).automation_traces("automation.luci_sera")
    trace = outcome["tracce"][0]
    assert trace["run_id"] == "xyz"
    assert trace["script_execution"] == "failed"
    assert fake.commands[0] == (
        "trace/list", {"domain": "automation", "item_id": "luci_sera"})
    assert outcome["tracce"] == [expected]


@pytest.mark.asyncio
async def test_a_failed_traces_read_says_error_not_an_empty_list():
    """Un elenco vuoto significherebbe «questa automazione non ha mai
    girato»: la stessa bugia che `system_log()` e `problems()` evitano.

    Mutazione: tornare `{"tracce": []}` invece di `{"errore": ...}` -- il
    test torna rosso su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(raises=True)
    outcome = await _client(fake).automation_traces("automation.luci_sera")
    assert "errore" in outcome
    assert "tracce" not in outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("fake,why", [
    (_FakeConnection(raises=True), "connessione caduta"),
    (_FakeConnection({"error": {"message": "non trovato"}}), "HA ha rifiutato"),
    (_FakeConnection({"result": {"issues": "non una lista nuda"}}),
     "forma inattesa: trace/list non manda un dizionario qui"),
])
async def test_every_traces_failure_shape_says_error_not_an_empty_list(fake, why):
    """Le tre forme di guasto gia' sorvegliate per `system_log()`, ripetute
    qui: connessione caduta, rifiuto esplicito di HA, e una risposta di forma
    inattesa (un dizionario al posto della lista nuda che manda davvero
    `async_list_traces`).

    Mutazione: togliere il controllo `isinstance(result, list)` -- solo il
    terzo caso (forma inattesa) tocca quel ramo e torna rosso su
    `assert "errore" in outcome, why`.
    """
    outcome = await _client(fake).automation_traces("automation.luci_sera")
    assert "errore" in outcome, why
    assert "tracce" not in outcome


@pytest.mark.asyncio
async def test_an_empty_traces_list_stays_empty_not_an_error():
    """L'altra meta' della disciplina: il vuoto non e' un errore, quanto
    l'errore non e' un vuoto. Un'automazione mai scattata ha davvero
    `async_list_traces(...) == []`, e deve restare `{"tracce": []}`.

    Mutazione: `if not result: return {"errore": "..."}` subito dopo il
    controllo di forma -- il test torna rosso su
    `assert outcome == {"tracce": []}`.
    """
    fake = _FakeConnection({"result": []})
    outcome = await _client(fake).automation_traces("automation.luci_sera")
    assert outcome == {"tracce": []}


# --------------------------------------------------------------------------
# automation_trace() -- trace/get
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_single_trace_is_read_as_home_assistant_sends_it():
    """Il client legge e non giudica anche qui, e il comando manda
    `domain`/`item_id`/`run_id`: gli stessi due primi spaccati dall'`entity_id`
    di `automation_traces()`, piu' il `run_id` richiesto.

    Mutazione: proiettare il risultato su un sottoinsieme di campi che scarta
    `trace` (il grafo) -- il test torna rosso su
    `assert trace["trace"] == row["trace"]`.
    """
    row = _extended_trace(run_id="xyz", state="stopped")
    expected = copy.deepcopy(row)
    fake = _FakeConnection({"result": row})
    outcome = await _client(fake).automation_trace("automation.luci_sera", "xyz")
    trace = outcome["traccia"]
    assert trace["run_id"] == "xyz"
    assert trace["trace"] == row["trace"]
    assert fake.commands[0] == (
        "trace/get",
        {"domain": "automation", "item_id": "luci_sera", "run_id": "xyz"})
    assert outcome["traccia"] == expected


@pytest.mark.asyncio
async def test_a_failed_trace_read_says_error_not_an_empty_dict():
    """Un dizionario vuoto qui significherebbe «questa esecuzione esiste ed
    e' senza contenuto», che non e' mai vero per una traccia reale: la stessa
    bugia dell'elenco vuoto, in un'altra forma.

    Mutazione: tornare `{"traccia": {}}` invece di `{"errore": ...}` -- il
    test torna rosso su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(raises=True)
    outcome = await _client(fake).automation_trace("automation.luci_sera", "xyz")
    assert "errore" in outcome
    assert "traccia" not in outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("fake,why", [
    (_FakeConnection(raises=True), "connessione caduta"),
    (_FakeConnection({"error": {"code": "not_found",
                                "message": "The trace could not be found"}}),
     "run_id caduto fuori dalle tracce conservate"),
    (_FakeConnection({"result": ["non un dizionario"]}),
     "forma inattesa: trace/get non manda una lista qui"),
])
async def test_every_trace_failure_shape_says_error_not_an_empty_dict(fake, why):
    """Le tre forme di guasto: connessione caduta, il rifiuto VERO che HA
    manda quando `run_id` e' gia' caduto fuori dalle tracce conservate
    (`ERR_NOT_FOUND`, verificato alla fonte in `websocket_trace_get`), e una
    risposta di forma inattesa (una lista al posto del dizionario che manda
    davvero `async_get_trace`).

    Mutazione: togliere il controllo `isinstance(result, dict)` -- solo il
    terzo caso (forma inattesa) tocca quel ramo e torna rosso su
    `assert "errore" in outcome, why`.
    """
    outcome = await _client(fake).automation_trace("automation.luci_sera", "xyz")
    assert "errore" in outcome, why
    assert "traccia" not in outcome
