"""«Cosa ho in agenda?» -- il client legge i calendari e i loro eventi.

`HAClient.calendars()` legge `GET /api/calendars`, `HAClient.calendar_events()`
legge `GET /api/calendars/<entity_id>?start=&end=` -- stessa disciplina dei
tre fratelli (`system_log()`, `automation_traces()`, `automation_trace()`,
`ha_client.py`):

1. **il client legge, non giudica**: le righe escono coi campi di HA, senza
   proiezioni -- cosa dire e cosa tacere e' di chi compone, non di questi
   metodi;
2. **un elenco vuoto su errore sarebbe una bugia** -- un guasto di lettura
   torna `{"errore": ...}`, mai un vuoto.

**La differenza di trasporto**, verificata alla fonte e non assunta: i tre
fratelli parlano WebSocket, i calendari REST -- verificato su
`home-assistant/core`, `homeassistant/components/calendar/__init__.py`, sui
tag RILASCIATI `2024.7.0` (il minimo dichiarato da `hiris/config.yaml:22`) e
`2026.9.0` (il piu' recente visto finora): `CalendarListView` (`url =
"/api/calendars"`) e `CalendarEventView` (`url =
"/api/calendars/{entity_id}"`) rispondono ENTRAMBE con una LISTA NUDA su
entrambi i tag -- non con un dizionario a chiave, e non diversamente fra
loro (a differenza dei tre fratelli, dove `trace/get` rompeva la simmetria).

**I campi degli eventi**, misurati sulla casa il 06/09/2026 su 297 eventi
veri e confermati alla stessa fonte (`CalendarEvent`, dataclass a otto campi,
e `_api_event_dict_factory`, che scrive ogni campo anche quando vale
`None`): `start`, `end`, `summary`, `description`, `location`, `uid`,
`recurrence_id`, `rrule` -- SEMPRE tutti e otto. `start`/`end` hanno una
delle due forme, mai entrambe: `{"dateTime": "...+02:00"}` per un evento a
orario, `{"date": "2026-08-17"}` per un evento giornaliero.
"""
import copy

import pytest

from hiris.app.proxy.ha_client import MAX_CALENDAR_EVENTS, HAClient


class _FakeResponse:
    """Risposta HTTP finta: un solo uso, come un vero `ClientResponse`
    async-context-manager. `raises` simula un guasto di trasporto (la
    connessione cade dentro `async with`, prima di poter leggere lo status)."""

    def __init__(self, status, body=None, raises=None):
        self.status = status
        self._body = body
        self._raises = raises

    async def __aenter__(self):
        if self._raises is not None:
            raise self._raises
        return self

    async def __aexit__(self, *_exc):
        return False

    async def json(self):
        return self._body


class _FakeSession:
    """Registra gli URL chiesti: alcune prove riguardano proprio l'URL
    composto (l'`entity_id` nel percorso, `start`/`end` nella query), non
    solo la risposta."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.urls_requested = []

    def get(self, url):
        self.urls_requested.append(url)
        return self._responses.pop(0)


def _client(responses):
    c = HAClient("http://ha.local", "token")
    c._session = _FakeSession(responses)
    return c


def _event(**fields):
    """Un evento nella forma vera della risposta di `CalendarEventView`
    (`_api_event_dict_factory`, verificata alla fonte): tutte e otto le
    chiavi, anche quando valgono `None`."""
    row = {"start": {"dateTime": "2026-09-05T16:00:00+02:00"},
           "end": {"dateTime": "2026-09-05T17:00:00+02:00"},
           "summary": "Allenamento", "description": None, "location": None,
           "uid": None, "recurrence_id": None, "rrule": None}
    row.update(fields)
    return row


# --------------------------------------------------------------------------
# calendars() -- GET /api/calendars
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendars_are_read_as_home_assistant_sends_them():
    """Il client legge e non giudica: le righe escono coi campi di HA,
    `entity_id` compreso -- perche' cosa dire e cosa tacere e' di chi
    compone. Confrontata con una COPIA fatta prima della chiamata: un client
    che modificasse le righe sul posto passerebbe verde contro l'oggetto
    dato alla finta stessa.

    Mutazione: proiettare i calendari su un sottoinsieme che scarta
    `entity_id` -- il test torna rosso su
    `assert calendar["entity_id"] == "calendar.lavoro"`. Un client che
    aggiungesse una chiave in piu' SUL POSTO (nessuno dei due campi
    asseriti direttamente cambierebbe) arrossisce piu' in basso, su
    `assert outcome["calendari"] == expected`.
    """
    rows = [{"name": "Casa", "entity_id": "calendar.casa"},
            {"name": "Lavoro", "entity_id": "calendar.lavoro"}]
    expected = copy.deepcopy(rows)
    c = _client([_FakeResponse(200, rows)])
    outcome = await c.calendars()
    calendar = outcome["calendari"][1]
    assert calendar["name"] == "Lavoro"
    assert calendar["entity_id"] == "calendar.lavoro"
    assert outcome["calendari"] == expected


@pytest.mark.asyncio
async def test_calendars_are_asked_at_the_right_url():
    """Nessuna query, nessun parametro: `GET /api/calendars` e basta.

    Mutazione: comporre l'URL con una `/` finale o un parametro spurio
    (es. `f"{self._base_url}/api/calendars/"`) -- il test torna rosso su
    `assert c._session.urls_requested == ["http://ha.local/api/calendars"]`.
    """
    c = _client([_FakeResponse(200, [])])
    await c.calendars()
    assert c._session.urls_requested == ["http://ha.local/api/calendars"]


@pytest.mark.asyncio
async def test_a_failed_calendars_read_says_error_not_an_empty_list():
    """Un elenco vuoto significherebbe «questa casa non ha calendari»: un
    guasto di lettura non ha il diritto di affermarlo.

    Mutazione: tornare `{"calendari": []}` invece di `{"errore": ...}` -- il
    test torna rosso su `assert "errore" in outcome`.
    """
    c = _client([_FakeResponse(500)])
    outcome = await c.calendars()
    assert "errore" in outcome
    assert "calendari" not in outcome


@pytest.mark.asyncio
async def test_a_transport_failure_reading_calendars_says_error_not_an_empty_list():
    """Il ramo `except Exception` deve restare distinto da un HTTP 500: qui
    la connessione cade DENTRO `async with`, prima ancora di leggere uno
    status.

    Mutazione: nel blocco `except`, tornare `{"calendari": []}` invece di
    `{"errore": ...}` -- il test torna rosso su
    `assert "errore" in outcome`.
    """
    c = _client([_FakeResponse(200, raises=OSError("HA irraggiungibile"))])
    outcome = await c.calendars()
    assert "errore" in outcome
    assert "calendari" not in outcome


@pytest.mark.asyncio
async def test_a_calendars_response_of_unexpected_shape_says_error_not_an_empty_list():
    """`/api/calendars` risponde una lista nuda: un dizionario al suo posto
    e' una forma che questo metodo non sa leggere, non un elenco vuoto.

    Mutazione: togliere il controllo `isinstance(data, list)` -- il test
    torna rosso su `assert "errore" in outcome`.
    """
    c = _client([_FakeResponse(200, {"calendari": "non una lista nuda"})])
    outcome = await c.calendars()
    assert "errore" in outcome
    assert "calendari" not in outcome


@pytest.mark.asyncio
async def test_an_empty_calendar_list_stays_empty_not_an_error():
    """L'inverso, altrettanto necessario: una casa senza calendari (o un
    token senza permesso su nessuno) risponde davvero `[]`, e non e' un
    guasto.

    Mutazione: `if not data: return {"errore": "..."}` subito dopo il
    controllo di forma -- il test torna rosso su
    `assert outcome == {"calendari": []}`.
    """
    c = _client([_FakeResponse(200, [])])
    outcome = await c.calendars()
    assert outcome == {"calendari": []}


# --------------------------------------------------------------------------
# calendar_events() -- GET /api/calendars/<entity_id>?start=&end=
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_events_are_read_as_home_assistant_sends_them():
    """Il client legge e non giudica: gli eventi escono con gli otto campi di
    HA -- `uid`, `rrule` e `recurrence_id` compresi -- perche' cosa dire e
    cosa tacere e' di chi compone. E la riga si confronta con una COPIA fatta
    prima della chiamata: confrontarla con l'oggetto dato alla finta
    lascerebbe passare verde un client che modifica gli eventi sul posto.

    Mutazione: proiettare gli eventi su un sottoinsieme che scarta `uid` --
    il test torna rosso su `assert event["uid"] == "evt-123"`. Un client
    che alterasse `location` SUL POSTO (un campo qui non asserito
    direttamente) arrossisce piu' in basso su
    `assert outcome["eventi"] == [expected]`.
    """
    row = _event(summary="Partita di padel", uid="evt-123",
                 recurrence_id="2026-09-05T16:00:00+02:00",
                 rrule="FREQ=WEEKLY")
    expected = copy.deepcopy(row)
    c = _client([_FakeResponse(200, [row])])
    outcome = await c.calendar_events("calendar.casa",
                                      "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    event = outcome["eventi"][0]
    assert event["summary"] == "Partita di padel"
    assert event["uid"] == "evt-123"
    assert event["recurrence_id"] == "2026-09-05T16:00:00+02:00"
    assert event["rrule"] == "FREQ=WEEKLY"
    assert outcome["eventi"] == [expected]


@pytest.mark.asyncio
async def test_calendar_events_keep_the_null_fields_home_assistant_sends():
    """La proprieta' che il capitolato misura: OTTO chiavi sempre, anche
    quando valgono `null`. Un evento giornaliero senza descrizione, luogo,
    uid, ricorrenza o rrule le porta comunque tutte.

    Mutazione: filtrare le chiavi il cui valore e' `None` prima di
    restituire l'evento -- il test torna rosso su
    `assert "description" in event`, perche' la proiezione la farebbe
    sparire invece di lasciarla `None`.
    """
    row = _event(start={"date": "2026-08-17"}, end={"date": "2026-08-18"},
                 summary="Ferie")
    c = _client([_FakeResponse(200, [row])])
    outcome = await c.calendar_events("calendar.casa", "2026-08-01T00:00:00+02:00",
                                      "2026-08-31T00:00:00+02:00")
    event = outcome["eventi"][0]
    for key in ("start", "end", "summary", "description", "location", "uid",
                "recurrence_id", "rrule"):
        assert key in event
    assert event["description"] is None
    assert event["uid"] is None
    assert event["start"] == {"date": "2026-08-17"}
    assert event["end"] == {"date": "2026-08-18"}


@pytest.mark.asyncio
async def test_calendar_events_are_asked_at_the_right_url_with_the_window():
    """`entity_id` sta nel percorso, `start`/`end` nella query -- esattamente
    cio' che il chiamante passa, percent-encoded, non riformattato.

    Mutazione: scambiare `start` ed `end` nella query (`f"?start=
    {quote(end,...)}&end={quote(start,...)}"`) -- il test torna rosso su
    `assert "start=2026-09-05T00%3A00%3A00%2B02%3A00" in url`, che trova
    invece il valore di `end`.
    """
    c = _client([_FakeResponse(200, [])])
    await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                            "2026-09-12T00:00:00+02:00")
    url = c._session.urls_requested[0]
    assert url.startswith("http://ha.local/api/calendars/calendar.casa?")
    assert "start=2026-09-05T00%3A00%3A00%2B02%3A00" in url
    assert "end=2026-09-12T00%3A00%3A00%2B02%3A00" in url


@pytest.mark.asyncio
async def test_calendar_events_rejects_an_invalid_entity_id_before_making_a_request():
    """Stessa guardia di `history()` e `logbook()`: un `entity_id` malformato
    non deve comporre un URL, anche se il percent-encoding chiuderebbe
    comunque l'iniezione.

    Mutazione: togliere il controllo `_ENTITY_ID_RE.match(...)` -- il test
    torna rosso su `assert c._session.urls_requested == []`, perche' senza
    la guardia la richiesta parte (e fallisce comunque, ma per un motivo che
    non ha niente a che fare con la guardia mancante).
    """
    c = _client([])
    outcome = await c.calendar_events("non e' un entity_id",
                                      "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert "errore" in outcome
    assert "eventi" not in outcome
    assert c._session.urls_requested == []


@pytest.mark.asyncio
async def test_calendar_events_never_raises_even_with_a_malformed_window():
    """Il contratto di questo metodo e' «su guasto torna un errore, mai
    un'eccezione» -- vale anche per `start`/`end`, non solo per la rete.
    `quote()` (usato per comporre la query) solleva un `TypeError` su un
    valore che non e' una stringa ne' `bytes` -- qui il chiamante ha
    passato un intero -- e quel `TypeError` deve restare dentro il `try`,
    o il metodo solleverebbe invece di rispondere.

    Mutazione: comporre l'URL (e quindi chiamare `quote(start, ...)`)
    FUORI dal `try` -- il test torna rosso non su un `AssertionError` ma su
    un `TypeError` non catturato che esce da `await
    c.calendar_events(...)`, prima ancora di raggiungere il primo assert.
    """
    c = _client([])
    outcome = await c.calendar_events("calendar.casa", 123,
                                      "2026-09-12T00:00:00+02:00")
    assert "errore" in outcome
    assert "eventi" not in outcome
    assert c._session.urls_requested == []


@pytest.mark.asyncio
async def test_a_failed_read_says_error_not_an_empty_calendar():
    """Un elenco vuoto significherebbe «non hai impegni», che e' esattamente
    la bugia da cui nasce questa fetta: un calendario rotto e uno senza
    impegni rispondono la stessa identica cosa, e solo l'errore li
    distingue.

    Mutazione: tornare `{"eventi": []}` invece di `{"errore": ...}` -- il
    test torna rosso su `assert "errore" in outcome`.
    """
    c = _client([_FakeResponse(500)])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert "errore" in outcome
    assert "eventi" not in outcome


@pytest.mark.asyncio
async def test_a_transport_failure_reading_calendar_events_says_error_not_an_empty_calendar():
    """Il ramo `except Exception` deve restare distinto da un HTTP 500: la
    connessione cade DENTRO `async with`, prima di poter leggere uno status.

    Mutazione: nel blocco `except`, tornare `{"eventi": []}` invece di
    `{"errore": ...}` -- il test torna rosso su
    `assert "errore" in outcome`.
    """
    c = _client([_FakeResponse(200, raises=OSError("HA irraggiungibile"))])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert "errore" in outcome
    assert "eventi" not in outcome


@pytest.mark.asyncio
async def test_a_calendar_events_response_of_unexpected_shape_says_error_not_an_empty_calendar():
    """`/api/calendars/<entity_id>` risponde anch'essa una lista nuda: un
    dizionario al suo posto e' una forma inattesa, non un elenco vuoto.

    Mutazione: togliere il controllo `isinstance(data, list)` -- il test
    torna rosso su `assert "errore" in outcome`.
    """
    c = _client([_FakeResponse(200, {"eventi": "non una lista nuda"})])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert "errore" in outcome
    assert "eventi" not in outcome


@pytest.mark.asyncio
async def test_an_empty_calendar_stays_empty_not_an_error():
    """L'inverso, ed e' altrettanto necessario: un calendario che risponde
    davvero «niente» non e' un guasto. Sulla casa vera i prossimi sette
    giorni sono vuoti su ENTRAMBI i calendari -- il caso vuoto e' il caso
    NORMALE, non quello raro.

    Mutazione: `if not data: return {"errore": ...}` -- il test torna rosso
    su `assert outcome == {"eventi": []}`.
    """
    c = _client([_FakeResponse(200, [])])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert outcome == {"eventi": []}


# --- Il tetto: un elenco tagliato non deve poter sembrare completo -------
#
# `elenco_incompleto`/`mute_da`/`entita_stato_ignoto` (home_space/queries.py)
# seguono gia' la stessa disciplina: le chiavi che non hanno niente da dire
# non escono. Qui si applica alla stessa fetta: `troncato` esce SOLO quando
# il taglio e' avvenuto -- a differenza di `history()`/`logbook()` in questo
# stesso file, che lo dichiarano SEMPRE (anche a falso). Le due meta' dello
# stesso difetto si sorvegliano con due prove separate.

@pytest.mark.asyncio
async def test_calendar_events_declares_the_cut_when_it_happens():
    """Un elenco tagliato non deve poter sembrare completo: chi riceve
    `MAX_CALENDAR_EVENTS` eventi su una finestra che ne aveva di piu' e non
    lo sa risponderebbe «questi sono tutti i tuoi impegni», la stessa bugia
    di «non hai impegni» quando in realta' non si e' riusciti a guardare.

    Mutazione: non aggiungere mai la chiave `troncato` -- il test torna
    rosso su `assert "troncato" in outcome`.
    """
    rows = [_event(uid=f"evt-{i}") for i in range(MAX_CALENDAR_EVENTS + 5)]
    c = _client([_FakeResponse(200, rows)])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert outcome["troncato"] is True
    assert len(outcome["eventi"]) == MAX_CALENDAR_EVENTS


@pytest.mark.asyncio
async def test_calendar_events_does_not_declare_a_cut_when_there_was_none():
    """L'altra meta' dello stesso difetto: una chiave che parla quando non
    ha niente da dire e' rumore, e qui e' anche peggio -- lascerebbe
    credere che OGNI risposta sia potenzialmente incompleta.

    Mutazione: dichiarare sempre `troncato` (es. sempre `False` quando non
    scatta, invece di ometterla) -- il test torna rosso su
    `assert "troncato" not in outcome`.
    """
    rows = [_event(uid=f"evt-{i}") for i in range(3)]
    c = _client([_FakeResponse(200, rows)])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    assert "troncato" not in outcome
    assert len(outcome["eventi"]) == 3


@pytest.mark.asyncio
async def test_calendar_events_cut_keeps_the_tail_not_the_head():
    """Stessa direzione di `history()`/`logbook()`: il taglio tiene la
    CODA della lista cosi' come HA la manda, non la testa.

    Mutazione: tenere `data[:MAX_CALENDAR_EVENTS]` (la testa) invece di
    `data[-MAX_CALENDAR_EVENTS:]` -- il test torna rosso su
    `assert outcome["eventi"][0]["uid"] == "evt-5"`, che troverebbe invece
    `"evt-0"`.
    """
    rows = [_event(uid=f"evt-{i}") for i in range(MAX_CALENDAR_EVENTS + 5)]
    c = _client([_FakeResponse(200, rows)])
    outcome = await c.calendar_events("calendar.casa", "2026-09-05T00:00:00+02:00",
                                      "2026-09-12T00:00:00+02:00")
    kept = outcome["eventi"]
    assert kept[0]["uid"] == "evt-5"
    assert kept[-1]["uid"] == f"evt-{MAX_CALENDAR_EVENTS + 4}"
