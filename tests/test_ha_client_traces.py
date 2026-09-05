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

**Correzione del Task 6, e la prova che passava verde sul comportamento
sbagliato.** La prima stesura di questi due metodi spaccava un `entity_id`
sul primo punto e mandava l'`object_id` come `item_id`; il test di questo
file lo PINNAVA (`assert fake.commands[0] == ("trace/list", {"domain":
"automation", "item_id": "luci_sera"})`), cioe' asseriva il FATTO che la
finta gli aveva messo davanti invece della PROPRIETA' che avrebbe dovuto
produrlo -- e restava verde mentre sulla casa vera `trace/list` rispondeva
`[]` per ogni automazione, sempre. La chiave con cui HA archivia le tracce e'
`automation.<id della CONFIGURAZIONE>` (`config_block.get(CONF_ID)`, non
l'`object_id`): la catena e' verificata sui tag rilasciati `2024.7.0` e
`2026.9.0` e scritta anello per anello nel docstring di
`HAClient.automation_traces()`.

La proprieta' che questi test sorvegliano adesso e' quindi: **cio' che il
chiamante passa arriva a `item_id` TALE E QUALE, senza essere spaccato,
tagliato o ricomposto**, e il `domain` e' la costante `"automation"`. Per
poterla vedere davvero, l'id usato in tutto il file e' un timbro numerico
come quelli che l'interfaccia di HA genera (`"1771346155970"`) e che NON
somiglia a nessun `object_id`: con `"luci_sera"` sia da una parte sia
dall'altra, un metodo che tornasse a spaccare un `entity_id` passerebbe
verde di nuovo.
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


# L'id di CONFIGURAZIONE di un'automazione, nella forma che l'interfaccia di
# Home Assistant genera davvero: un timbro numerico. Volutamente NON
# somigliante a un `object_id` -- e' cio' che rende visibile la proprieta'
# che questo file sorveglia (vedi il docstring del modulo).
_CONFIG_ID = "1771346155970"


def _short_trace(**fields):
    """Una riga di `trace/list` nella forma vera di
    `ActionTrace.as_short_dict()` (`homeassistant/components/trace/models.py`,
    verificata alla fonte)."""
    row = {"last_step": "trigger/0", "run_id": "abc123", "state": "stopped",
           "script_execution": "success",
           "timestamp": {"start": "2026-09-05T10:00:00+00:00",
                         "finish": "2026-09-05T10:00:01+00:00"},
           "domain": "automation", "item_id": _CONFIG_ID}
    row.update(fields)
    return row


def _extended_trace(**fields):
    """Una riga di `trace/get` nella forma vera di
    `ActionTrace.as_extended_dict()` (stessa fonte): tutto quello che ha
    `as_short_dict()` piu' `trace`, `config`, `blueprint_inputs`, `context`."""
    row = _short_trace()
    row.update({"trace": {"trigger/0": [{"path": "trigger/0", "result": {}}]},
                "config": {"id": _CONFIG_ID}, "blueprint_inputs": None,
                "context": {"id": "ctx1", "parent_id": None, "user_id": None}})
    row.update(fields)
    return row


# --------------------------------------------------------------------------
# automation_traces() -- trace/list
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_automation_traces_are_read_as_home_assistant_sends_them():
    """Il client legge e non giudica: le righe escono coi campi di HA.

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
    outcome = await _client(fake).automation_traces(_CONFIG_ID)
    trace = outcome["tracce"][0]
    assert trace["run_id"] == "xyz"
    assert trace["script_execution"] == "failed"
    assert outcome["tracce"] == [expected]


@pytest.mark.asyncio
async def test_traces_are_asked_for_by_configuration_id_verbatim():
    """L'argomento arriva a `item_id` TALE E QUALE, e il `domain` e' la
    costante `"automation"`.

    E' la proprieta' che il vecchio test non sorvegliava: pinnava
    `item_id: "luci_sera"` mentre il metodo spaccava un `entity_id`, cioe'
    il fatto che la finta gli aveva messo davanti. Qui l'argomento e' un id
    di configurazione che NON somiglia a un `entity_id` (nessun punto, tutte
    cifre), quindi un metodo che tornasse a spaccare, a tagliare un prefisso
    o a ricomporre una chiave non potrebbe piu' passare per caso.

    Fonte della chiave (tag rilasciati `2024.7.0` e `2026.9.0`):
    `components/automation/__init__.py` traccia con `self.unique_id`, che e'
    `config_block.get(CONF_ID)`; `trace/models.py` ne fa
    `f"{self._domain}.{item_id}"`; `websocket_trace_list` ricompone
    `f"{msg['domain']}.{msg['item_id']}"` e fa un `.get(key)` nudo.

    Mutazione: `automation_id.partition(".")[2]` come `item_id` (cioe' il
    vecchio comportamento, che su un id senza punto restituisce `""`) -- il
    test torna rosso su `assert fake.commands == [("trace/list", {"domain":
    "automation", "item_id": _CONFIG_ID})]`, che riceve `item_id: ""`.
    """
    fake = _FakeConnection({"result": []})
    await _client(fake).automation_traces(_CONFIG_ID)
    assert fake.commands == [
        ("trace/list", {"domain": "automation", "item_id": _CONFIG_ID})]


@pytest.mark.asyncio
async def test_a_failed_traces_read_says_error_not_an_empty_list():
    """Un elenco vuoto significherebbe «questa automazione non ha mai
    girato»: la stessa bugia che `system_log()` e `problems()` evitano.

    Mutazione: tornare `{"tracce": []}` invece di `{"errore": ...}` -- il
    test torna rosso su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(raises=True)
    outcome = await _client(fake).automation_traces(_CONFIG_ID)
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
    outcome = await _client(fake).automation_traces(_CONFIG_ID)
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
    outcome = await _client(fake).automation_traces(_CONFIG_ID)
    assert outcome == {"tracce": []}


# --------------------------------------------------------------------------
# automation_trace() -- trace/get
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_single_trace_is_read_as_home_assistant_sends_it():
    """Il client legge e non giudica anche qui.

    Mutazione: proiettare il risultato su un sottoinsieme di campi che scarta
    `trace` (il grafo) -- il test torna rosso su
    `assert trace["trace"] == row["trace"]`.
    """
    row = _extended_trace(run_id="xyz", state="stopped")
    expected = copy.deepcopy(row)
    fake = _FakeConnection({"result": row})
    outcome = await _client(fake).automation_trace(_CONFIG_ID, "xyz")
    trace = outcome["traccia"]
    assert trace["run_id"] == "xyz"
    assert trace["trace"] == row["trace"]
    assert outcome["traccia"] == expected


@pytest.mark.asyncio
async def test_a_single_trace_is_asked_for_by_configuration_id_verbatim():
    """Gemello del test su `trace/list`, per `trace/get`: `item_id` e' l'id
    di configurazione tale e quale, `domain` e' `"automation"`, e `run_id`
    e' il terzo campo -- l'ordine dei due argomenti del metodo conta quanto
    il loro valore.

    Stessa fonte (`websocket_trace_get`, stessi due tag), stessa chiave
    ricomposta con un `.get(key)` nudo.

    Mutazione: scambiare i due argomenti nel comando (`"item_id": run_id,
    "run_id": automation_id`) -- il test torna rosso sull'unico assert,
    che riceve `item_id: "xyz"` e `run_id: _CONFIG_ID`.
    """
    fake = _FakeConnection({"result": _extended_trace()})
    await _client(fake).automation_trace(_CONFIG_ID, "xyz")
    assert fake.commands == [
        ("trace/get", {"domain": "automation", "item_id": _CONFIG_ID,
                       "run_id": "xyz"})]


@pytest.mark.asyncio
async def test_a_failed_trace_read_says_error_not_an_empty_dict():
    """Un dizionario vuoto qui significherebbe «questa esecuzione esiste ed
    e' senza contenuto», che non e' mai vero per una traccia reale: la stessa
    bugia dell'elenco vuoto, in un'altra forma.

    Mutazione: tornare `{"traccia": {}}` invece di `{"errore": ...}` -- il
    test torna rosso su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(raises=True)
    outcome = await _client(fake).automation_trace(_CONFIG_ID, "xyz")
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
    outcome = await _client(fake).automation_trace(_CONFIG_ID, "xyz")
    assert "errore" in outcome, why
    assert "traccia" not in outcome
