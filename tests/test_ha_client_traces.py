"""«Com'e' andata questa automazione?»

`HAClient.automation_traces()` legge `trace/list` (le esecuzioni RECENTI, in
breve), `HAClient.trace()` legge `trace/get` (UNA esecuzione,
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
tagliato o ricomposto**, e il `domain` e' quello che il chiamante passa (`"automation"` per i vecchi
lettori, che delegano a `traces`/`trace`; `"script"` per gli script). Per
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

    def __init__(self, response=None, replies=None):
        self.response = response
        self.replies = replies  # una risposta per comando, come `_ws_send` vero
        self.commands = []
        self.batches = []

    async def _ws_send(self, commands, timeout=10.0):
        self.commands.extend(commands)
        self.batches.append(list(commands))
        if self.replies is not None:
            return list(self.replies)
        return [self.response]


def _client(fake):
    c = HAClient.__new__(HAClient)
    c._ws_send = fake._ws_send
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

    La connessione caduta e' `replies=[None]`, come la torna il vero
    `_ws_send`, che non solleva mai. Ha DUE guardie (il controllo
    `all(reply is None ...)` in `traces` e il ramo `non_letti` di
    `automation_traces`): ciascuna da sola la copre l'altra.

    Mutazione ESEGUITA: togliere TUTTE E DUE le guardie (`{"tracce": []}`
    per una chiave non letta) -- rossa su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(replies=[None])
    outcome = await _client(fake).automation_traces(_CONFIG_ID)
    assert "errore" in outcome
    assert "tracce" not in outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("fake,why", [
    (_FakeConnection(replies=[None]), "connessione caduta"),
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
# trace() -- trace/get
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
    outcome = await _client(fake).trace("automation", _CONFIG_ID, "xyz")
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

    Mutazione ESEGUITA: scambiare i due argomenti nel comando (`"item_id": run_id,
    "run_id": automation_id`) -- il test torna rosso sull'unico assert,
    che riceve `item_id: "xyz"` e `run_id: _CONFIG_ID`.
    """
    fake = _FakeConnection({"result": _extended_trace()})
    await _client(fake).trace("automation", _CONFIG_ID, "xyz")
    assert fake.commands == [
        ("trace/get", {"domain": "automation", "item_id": _CONFIG_ID,
                       "run_id": "xyz"})]


@pytest.mark.asyncio
async def test_a_failed_trace_read_says_error_not_an_empty_dict():
    """Un dizionario vuoto qui significherebbe «questa esecuzione esiste ed
    e' senza contenuto», che non e' mai vero per una traccia reale: la stessa
    bugia dell'elenco vuoto, in un'altra forma.

    Mutazione ESEGUITA: `{"traccia": {}}` invece di `{"errore": ...}` su
    risposta assente -- rossa su `assert "errore" in outcome`.
    """
    fake = _FakeConnection(replies=[None])
    outcome = await _client(fake).trace("automation", _CONFIG_ID, "xyz")
    assert "errore" in outcome
    assert "traccia" not in outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("fake,why", [
    (_FakeConnection(replies=[None]), "connessione caduta"),
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

    Mutazione ESEGUITA: togliere il controllo `isinstance(result, dict)` -- solo il
    terzo caso (forma inattesa) tocca quel ramo e torna rosso su
    `assert "errore" in outcome, why`.
    """
    outcome = await _client(fake).trace("automation", _CONFIG_ID, "xyz")
    assert "errore" in outcome, why
    assert "traccia" not in outcome


@pytest.mark.asyncio
async def test_the_runs_of_many_automations_travel_in_one_batch():
    """Spec «la storia» §1 e §8 punto 3: «perche' sono partite le automazioni dei
    rifiuti» erano cinque chiamate. Ora una raffica, N comandi.

    Mutazione ESEGUITA: un `_ws_send` per chiave -- rossa su
    `len(fake.batches)`."""
    fake = _FakeConnection(replies=[{"result": [_short_trace(run_id="a")]}, {"result": []}])
    outcome = await _client(fake).traces([("automation", _CONFIG_ID),
                                          ("script", "buonanotte")])
    assert len(fake.batches) == 1
    assert fake.batches[0] == [
        ("trace/list", {"domain": "automation", "item_id": _CONFIG_ID}),
        ("trace/list", {"domain": "script", "item_id": "buonanotte"})]
    assert outcome == {"tracce": {f"automation.{_CONFIG_ID}": [_short_trace(run_id="a")],
                                  "script.buonanotte": []},
                       "non_letti": {}}


@pytest.mark.asyncio
async def test_a_refused_key_is_named_and_the_others_answer():
    """Una chiave rifiutata non spegne le altre, e non diventa `[]`.

    Mutazione ESEGUITA: il primo rifiuto rende `errore` tutta la risposta
    -- rossa."""
    fake = _FakeConnection(replies=[{"error": {"message": "non trovato"}},
                                    {"result": [_short_trace()]}, None,
                                    {"result": {"non": "una lista"}}])
    outcome = await _client(fake).traces([("automation", "1"), ("automation", "2"),
                                          ("automation", "3"), ("automation", "4")])
    assert outcome["non_letti"] == {"automation.1": "non trovato",
                                    "automation.3": "Home Assistant non ha risposto in tempo",
                                    "automation.4": "risposta in forma inattesa"}
    assert list(outcome["tracce"]) == ["automation.2"]


@pytest.mark.asyncio
async def test_a_dead_connection_says_error_never_no_runs():
    """`_ws_send` vero NON solleva: connessione caduta, auth rifiutata o
    timeout totale tornano `[None, None, ...]` (`tests/test_ha_client_invio.py`). Una
    raffica in cui nessuno ha risposto e' un `errore`, mai «nessuna
    esecuzione» ne' un `non_letti` di tutte le chiavi.

    Mutazione ESEGUITA: tolto il controllo `all(reply is None ...)` -- rossa."""
    fake = _FakeConnection(replies=[None, None])
    outcome = await _client(fake).traces([("automation", "1"), ("script", "s")])
    assert outcome == {"errore": "Home Assistant non ha risposto"}


@pytest.mark.asyncio
async def test_a_silent_tail_is_named_as_not_answered_in_time():
    """Il timeout taglia la coda: le chiavi senza risposta sono nominate col
    motivo giusto (non «forma inattesa»), le altre rispondono.

    Mutazione ESEGUITA: `None` trattato come forma inattesa -- rossa sul
    motivo."""
    fake = _FakeConnection(replies=[{"result": []}, None])
    outcome = await _client(fake).traces([("automation", "1"), ("script", "s")])
    assert outcome["tracce"] == {"automation.1": []}
    assert outcome["non_letti"] == {"script.s": "Home Assistant non ha risposto in tempo"}


@pytest.mark.asyncio
async def test_a_single_run_with_no_reply_says_error():
    """`trace/get` senza risposta (`[None]`, come da `_ws_send` vero) e'
    `errore`, non una forma inattesa.

    Mutazione ESEGUITA: `None` cade nel ramo «forma inattesa» -- rossa sul
    testo."""
    outcome = await _client(_FakeConnection(replies=[None])).trace("script", "s", "r")
    assert outcome == {"errore": "Home Assistant non ha risposto"}


@pytest.mark.asyncio
async def test_no_keys_ask_nothing():
    """Nessuna chiave, nessuna rete.

    Mutazione ESEGUITA: tolto il ritorno anticipato su `not keys` -- rossa
    su `fake.batches == []`."""
    fake = _FakeConnection(replies=[])
    assert await _client(fake).traces([]) == {"tracce": {}, "non_letti": {}}
    assert fake.batches == []


@pytest.mark.asyncio
async def test_a_single_run_of_a_script_is_asked_under_the_script_domain():
    """Mutazione ESEGUITA: `domain` fisso a `automation` in `trace` -- rossa."""
    fake = _FakeConnection({"result": _extended_trace()})
    outcome = await _client(fake).trace("script", "buonanotte", "r1")
    assert fake.commands == [("trace/get", {"domain": "script", "item_id": "buonanotte",
                                            "run_id": "r1"})]
    assert outcome["traccia"]["run_id"] == "abc123"


@pytest.mark.asyncio
async def test_the_real_batch_on_a_dead_network_ends_in_error():
    """La strada VERA, senza finta di `_ws_send`: rete assente -> il vero
    `_ws_send` torna `[None, None]` senza sollevare -> `traces` e `trace`
    dicono `errore`.

    Mutazione ESEGUITA: tolto il controllo `all(reply is None ...)` in
    `traces` -- rossa (le chiavi finirebbero tutte in `non_letti`)."""
    from unittest.mock import patch

    def esplode(*a, **k):
        raise OSError("rete assente")

    client = HAClient(base_url="http://ha.test", token="t")
    with patch("aiohttp.ClientSession", esplode):
        many = await client.traces([("automation", "1"), ("script", "s")])
        one = await client.trace("script", "s", "r")
    assert many == {"errore": "Home Assistant non ha risposto"}
    assert one == {"errore": "Home Assistant non ha risposto"}
