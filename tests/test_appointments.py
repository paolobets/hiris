"""«Quali sono i miei prossimi appuntamenti?» -- un evento grezzo del Task 1
diventa un impegno che una persona legge.

`read_appointment` compone UN evento; `sort_appointments` fonde impegni GIA'
letti di piu' calendari (ciascuno gia' ordinato per conto suo) in un unico
elenco ordinato -- vedi `hiris/app/home_space/appointments.py` per il perche'
di ogni scelta, in particolare `al`, escluso come la `end` di Home Assistant
anche per i giornalieri (B-28, letto nel sorgente di HA l'08/10/2026), e la
legge sulle chiavi che non hanno niente da dire.
"""
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from hiris.app.home_space import appointments as appointments_module
from hiris.app.home_space.appointments import (
    merge_calendars,
    read_appointment,
    readable_calendars,
    sort_appointments,
)


def _timed_event(**fields):
    """Un evento a orario nella forma vera di `CalendarEventView` (otto
    chiavi, vedi `test_ha_client_calendars.py::_event`), gia' nel fuso di
    Roma come lo scrive `_api_event_dict_factory` (`dt_util.as_local`)."""
    row = {"start": {"dateTime": "2026-09-05T16:00:00+02:00"},
           "end": {"dateTime": "2026-09-05T17:00:00+02:00"},
           "summary": "Allenamento", "description": None, "location": None,
           "uid": None, "recurrence_id": None, "rrule": None}
    row.update(fields)
    return row


def _all_day_event(**fields):
    row = {"start": {"date": "2026-08-30"}, "end": {"date": "2026-08-31"},
           "summary": "ANNIVERSARIO", "description": None, "location": None,
           "uid": None, "recurrence_id": None, "rrule": None}
    row.update(fields)
    return row


# --------------------------------------------------------------------------
# read_appointment -- `dal`/`al`, un significato solo (B-28, D4 della Tappa 9)
# --------------------------------------------------------------------------

def _first_instant_outside(appointment: dict) -> float:
    """L'istante in cui l'intervallo finisce, letto da `al` come lo legge
    Home Assistant: una data nuda vale la sua mezzanotte nel fuso della casa
    (`get_datetime_local` -> `dt_util.start_of_local_day`, `home-assistant/core`
    @ 2026.10.0), un istante vale se stesso."""
    al = appointment["al"]
    if len(al) == 10:
        al = datetime.combine(date.fromisoformat(al), time.min,
                              tzinfo=ZoneInfo("Europe/Rome")).isoformat()
    return datetime.fromisoformat(al).timestamp()


def test_al_ha_lo_stesso_significato_per_un_giornaliero_e_per_uno_a_orario():
    """B-28: `al` e' il primo giorno (o istante) che NON fa piu' parte
    dell'impegno, per tutti e due i generi -- la `end` di Home Assistant,
    esclusa (documentazione: «The end (exclusive) of the event»,
    developers.home-assistant.io `docs/core/entity/calendar.md` @ `8da484e`;
    sorgente: lo stato `on` vale `start <= now < end`, `home-assistant/core`
    @ 2026.10.0, letto l'08/10/2026).

    Due impegni che finiscono alla STESSA mezzanotte -- «ANNIVERSARIO»,
    giornaliero del 30 agosto, e una veglia a orario che finisce alle 00:00 del
    31 -- hanno lo stesso `al`, letto allo stesso modo. Prima di B-28 la
    `fine` del giornaliero era l'ultimo giorno COMPRESO (`2026-08-30`) e quella
    a orario l'istante ESCLUSO: due significati sotto un nome solo.

    Rossa prima del codice: `KeyError: 'dal'` (la chiave non esisteva).
    Mutazione ESEGUITA l'08/10/2026: in `read_appointment` il giornaliero
    torna a togliere un giorno (`date.fromisoformat(end["date"]) -
    timedelta(days=1)`) -- rossa sulla coppia `(dal, al)`: «AssertionError:
    assert ('2026-08-30', '2026-08-30') == ('2026-08-30', '2026-08-31')»;
    ripristinato e verificato col diff.
    """
    all_day = read_appointment(_all_day_event(), timezone="Europe/Rome")
    timed = read_appointment(
        _timed_event(start={"dateTime": "2026-08-30T22:00:00+02:00"},
                     end={"dateTime": "2026-08-31T00:00:00+02:00"}),
        timezone="Europe/Rome")

    assert (all_day["dal"], all_day["al"]) == ("2026-08-30", "2026-08-31")
    assert timed["al"] == "2026-08-31T00:00:00+02:00"
    assert _first_instant_outside(all_day) == _first_instant_outside(timed)
    for appointment in (all_day, timed):
        assert "inizio" not in appointment and "fine" not in appointment


def test_un_giornaliero_di_piu_giorni_tiene_la_fine_di_home_assistant():
    """Misurato sulla casa vera il 06/09/2026: «Ferie estive» va dal 17 al 31
    agosto e l'ultimo giorno di ferie e' il 30. `al` e' il 31, come lo scrive
    Home Assistant: nessuna traduzione al confine.

    Mutazione ESEGUITA, la stessa del test qui sopra -- rossa su `assert
    appointment["al"] == "2026-08-31"`: «assert '2026-08-30' == '2026-08-31'».
    """
    appointment = read_appointment(
        {"start": {"date": "2026-08-17"}, "end": {"date": "2026-08-31"},
         "summary": "Ferie estive ", "description": None, "location": None,
         "uid": "270019B2", "recurrence_id": None, "rrule": None},
        timezone="Europe/Rome")
    assert appointment["giornaliero"] is True
    assert appointment["dal"] == "2026-08-17"
    assert appointment["al"] == "2026-08-31"


def test_un_impegno_a_orario_esce_nel_fuso_della_casa():
    """L'evento arriva in UTC apposta: `dal` e `al` portano il fuso della
    casa, non la stringa di Home Assistant.

    Mutazione: emettere `end["dateTime"]` grezzo, senza `instant_out` --
    rossa su `assert appointment["al"] == "2026-09-05T23:00:00+02:00"`.
    """
    appointment = read_appointment(
        _timed_event(start={"dateTime": "2026-09-05T20:00:00+00:00"},
                     end={"dateTime": "2026-09-05T21:00:00+00:00"}),
        timezone="Europe/Rome")
    assert appointment["giornaliero"] is False
    assert appointment["dal"] == "2026-09-05T22:00:00+02:00"
    assert appointment["al"] == "2026-09-05T23:00:00+02:00"


def test_a_timed_event_is_rewritten_in_the_home_timezone_not_left_as_is():
    """`home_space_zone` (riusato, non reinventato) decide il fuso: un
    istante che arriva in un fuso diverso da quello della casa deve uscire
    riscritto, non lasciato com'e'.

    Mutazione: emettere `start["dateTime"]`/`end["dateTime"]` grezzi senza
    passare da `home_space_zone`/`astimezone` -- il test torna rosso su
    `assert appointment["dal"] == "2026-09-05T22:00:00+02:00"`, che
    troverebbe invece la stringa UTC originale.
    """
    appointment = read_appointment(
        _timed_event(start={"dateTime": "2026-09-05T20:00:00+00:00"}),
        timezone="Europe/Rome")
    assert appointment["dal"] == "2026-09-05T22:00:00+02:00"


def test_an_unrecognized_timezone_falls_back_to_utc_like_home_space_zone_does():
    """Non un secondo aiuto per il fuso: `home_space_zone` gestisce gia' il
    fuso non riconosciuto col ripiego su UTC (`historian.py`). Un fuso
    inventato non deve far esplodere questo modulo, ne' fargli inventare un
    proprio fuso di riserva diverso da quello condiviso.

    Mutazione: usare `ZoneInfo(timezone)` direttamente invece di
    `home_space_zone(timezone)` -- il test torna rosso non su un
    `AssertionError` ma su una `ZoneInfoNotFoundError` non catturata che
    esce da `read_appointment(...)`, prima ancora di raggiungere l'assert.
    """
    appointment = read_appointment(
        _timed_event(start={"dateTime": "2026-09-05T20:00:00+00:00"}),
        timezone="Fuso/Inventato")
    assert appointment["dal"] == "2026-09-05T20:00:00+00:00"


def test_a_missing_timezone_falls_back_to_utc_too():
    """`read_appointment(..., timezone=None)` e' un caso VERO, non un
    capriccio della firma: `ToolDispatcher._timezone()` (`home_space/tools.py`)
    torna proprio `None` finche' il fuso della casa non e' ancora noto.
    `home_space_zone(None)` ripiega gia' su UTC -- questo modulo non deve
    inventare un secondo comportamento per `None`.

    Mutazione: assumere `timezone` sempre una stringa (es. chiamare
    `timezone.strip()` prima di passarla a `home_space_zone`) -- il test
    torna rosso non su un `AssertionError` ma su un `AttributeError:
    'NoneType' object has no attribute 'strip'`, uscito da
    `read_appointment(...)` prima dell'assert.
    """
    appointment = read_appointment(
        _timed_event(start={"dateTime": "2026-09-05T20:00:00+00:00"}),
        timezone=None)
    assert appointment["dal"] == "2026-09-05T20:00:00+00:00"


def test_the_timezone_is_resolved_once_per_distinct_name_not_once_per_appointment():
    """Leggere PIU' impegni con lo STESSO fuso non riconosciuto non deve
    produrre un avviso per ognuno: `home_space_zone` logga ad OGNI chiamata,
    e cinque impegni con la stessa configurazione sbagliata produrrebbero
    cinque avvisi identici per UN unico problema -- il rumore che la legge
    del prodotto vieta altrove, qui applicata ai log.

    Mutazione: chiamare `home_space_zone(timezone)` direttamente in
    `read_appointment` invece di passare dalla cache locale
    (`_cached_zone`) -- il test torna rosso su
    `assert mocked.call_count == 1`, che con la chiamata diretta
    troverebbe invece `5` (una per ogni impegno letto).
    """
    appointments_module._cached_zone.cache_clear()
    try:
        with patch.object(appointments_module, "home_space_zone",
                           wraps=appointments_module.home_space_zone) as mocked:
            for _ in range(5):
                read_appointment(_timed_event(), timezone="Fuso/Contatore-Test")
            assert mocked.call_count == 1
    finally:
        appointments_module._cached_zone.cache_clear()


# --------------------------------------------------------------------------
# read_appointment -- le chiavi che non hanno niente da dire
# --------------------------------------------------------------------------

def test_a_key_with_nothing_to_say_does_not_come_out():
    """`description` e `location` erano `null` su OGNI evento campionato sulla
    casa. Una chiave `luogo: None` invita chi legge a dire «senza luogo», che e'
    un'affermazione: le chiavi che non hanno niente da dire non escono, come
    gia' fanno `mute_da` ed `elenco_incompleto`.

    Mutazione: emettere sempre le chiavi -- il test torna rosso su
    `assert "luogo" not in appointment`.
    """
    appointment = read_appointment(_timed_event(location=None, description=None),
                                    timezone="Europe/Rome")
    assert "luogo" not in appointment
    assert "descrizione" not in appointment


def test_a_key_with_only_blank_space_to_say_does_not_come_out_either():
    """Uno spazio bianco non ha niente da dire piu' di un `null`: un
    `location` fatto solo di spazi e' la stessa assenza, non un luogo vuoto.

    Mutazione: controllare `is not None` invece del testo rifilato (es. `if
    event.get("location") is not None: result["luogo"] = ...`) -- il test
    torna rosso su `assert "luogo" not in appointment`, che troverebbe
    invece `appointment["luogo"] == "   "`.
    """
    appointment = read_appointment(_timed_event(location="   "), timezone="Europe/Rome")
    assert "luogo" not in appointment


def test_a_key_with_something_to_say_does_come_out():
    """L'inverso, altrettanto necessario: un luogo o una descrizione VERI
    devono uscire, o la legge sul silenzio diventerebbe un modo elaborato
    per non dire mai niente.

    Mutazione: non emettere mai `luogo`/`descrizione` (es. per una svista
    nel controllo, tipo `if False:`) -- il test torna rosso su
    `assert appointment["luogo"] == "Circolo Padel"`.
    """
    appointment = read_appointment(
        _timed_event(location="Circolo Padel", description="Doppio con Marco"),
        timezone="Europe/Rome")
    assert appointment["luogo"] == "Circolo Padel"
    assert appointment["descrizione"] == "Doppio con Marco"


def test_technical_identifiers_do_not_come_out_of_a_readable_appointment():
    """`uid`, `recurrence_id`, `rrule` sono identificatori tecnici di HA, non
    parte di cio' che una persona legge: l'interfaccia dichiara solo
    `titolo`, `dal`, `al`, `giornaliero`, `luogo`, `descrizione`.

    Mutazione: propagare anche `uid` nel dizionario letto -- il test torna
    rosso su `assert "uid" not in appointment`.
    """
    appointment = read_appointment(
        _timed_event(uid="evt-123", recurrence_id="2026-09-05T16:00:00+02:00",
                     rrule="FREQ=WEEKLY"),
        timezone="Europe/Rome")
    assert "uid" not in appointment
    assert "recurrence_id" not in appointment
    assert "rrule" not in appointment


def test_the_title_is_trimmed_of_stray_whitespace():
    """Un titolo con uno spazio in coda (visto sulla casa vera: "Ferie estive
    ") non e' cio' che una persona scriverebbe leggendolo: si rifila.

    Mutazione: usare `event["summary"]` cosi' com'e', senza `.strip()` -- il
    test torna rosso su `assert appointment["titolo"] == "Ferie estive"`, che
    troverebbe invece lo spazio in coda.
    """
    appointment = read_appointment(_timed_event(summary="Ferie estive "),
                                    timezone="Europe/Rome")
    assert appointment["titolo"] == "Ferie estive"


# --------------------------------------------------------------------------
# sort_appointments -- fondere impegni GIA' letti, non riordinare un
# elenco gia' ordinato
# --------------------------------------------------------------------------

def test_sort_appointments_merges_two_already_sorted_calendars_into_one_order():
    """La proprieta' che questa funzione esiste per produrre: NON riordina
    un calendario (arriva gia' ordinato dal Task 1, e gia' letto da chi
    chiama), fonde quelli di PIU' calendari. Un ingresso gia' concatenato in
    ordine cronologico non distinguerebbe «fonde davvero» da «lascia
    stare»: qui i due calendari sono concatenati SENZA intrecciarli (A
    intero, poi B intero), cosi' solo un ordinamento vero produce
    l'intreccio atteso.

    Mutazione: tornare gli impegni cosi' come arrivano, senza `sorted(...)`
    (l'ordine di concatenazione) -- il test torna rosso su
    `assert titles == ["A-mattina", "B-mattina", "A-sera", "B-sera"]`, che
    troverebbe invece l'ordine di concatenazione
    `["A-mattina", "A-sera", "B-mattina", "B-sera"]`.
    """
    calendar_a = [
        read_appointment(
            _timed_event(summary="A-mattina",
                         start={"dateTime": "2026-09-05T08:00:00+02:00"},
                         end={"dateTime": "2026-09-05T09:00:00+02:00"}),
            timezone="Europe/Rome"),
        read_appointment(
            _timed_event(summary="A-sera",
                         start={"dateTime": "2026-09-05T20:00:00+02:00"},
                         end={"dateTime": "2026-09-05T21:00:00+02:00"}),
            timezone="Europe/Rome"),
    ]
    calendar_b = [
        read_appointment(
            _timed_event(summary="B-mattina",
                         start={"dateTime": "2026-09-05T10:00:00+02:00"},
                         end={"dateTime": "2026-09-05T11:00:00+02:00"}),
            timezone="Europe/Rome"),
        read_appointment(
            _timed_event(summary="B-sera",
                         start={"dateTime": "2026-09-05T22:00:00+02:00"},
                         end={"dateTime": "2026-09-05T23:00:00+02:00"}),
            timezone="Europe/Rome"),
    ]
    merged = sort_appointments(calendar_a + calendar_b)
    titles = [appointment["titolo"] for appointment in merged]
    assert titles == ["A-mattina", "B-mattina", "A-sera", "B-sera"]


def test_sort_appointments_only_looks_at_dal_not_at_a_raw_event():
    """`sort_appointments` prende impegni GIA' letti, non eventi grezzi da
    rileggere: non ha bisogno di nessun altro campo che `dal` per fare
    il suo lavoro, ed e' per questo che la firma non porta piu' `timezone`
    (serviva solo perche' prima la funzione leggeva ANCHE, non solo
    fondeva).

    Mutazione: provare a rileggere l'evento (es. cercare `start`/`end`
    invece di usare `dal` gia' scritto) -- il test torna rosso su
    `assert titles == ["a", "b"]`, con un `KeyError: 'start'` (questi
    impegni minimi non hanno `start`, solo `dal` e `titolo`).
    """
    minimal = [{"titolo": "b", "dal": "2026-09-05T10:00:00+02:00"},
               {"titolo": "a", "dal": "2026-09-05T08:00:00+02:00"}]
    merged = sort_appointments(minimal)
    titles = [appointment["titolo"] for appointment in merged]
    assert titles == ["a", "b"]


def test_sort_appointments_orders_by_the_instant_the_night_the_clock_goes_back():
    """A17 (approvata il 05/10/2026): il 25/10/2026 alle 03:00 Roma torna da
    +02:00 a +01:00. Le 02:30+02:00 (00:30 UTC) vengono PRIMA delle
    02:10+01:00 (01:10 UTC), ma come testo vengono dopo: l'ordine per testo
    sbagliava una notte l'anno, dichiarato e lasciato. Ora si ordina per
    istante, come `search` (Tappa 4, T4).

    Mutazione eseguita: la chiave riportata al solo `dal` come testo ->
    rossa, «dopo» prima di «prima»."""
    appointments = [
        {"titolo": "dopo", "dal": "2026-10-25T02:10:00+01:00"},
        {"titolo": "prima", "dal": "2026-10-25T02:30:00+02:00"},
        {"titolo": "giornaliero", "dal": "2026-10-25"},
        {"titolo": "il giorno dopo", "dal": "2026-10-26"},
    ]
    titles = [a["titolo"] for a in sort_appointments(appointments)]
    assert titles == ["giornaliero", "prima", "dopo", "il giorno dopo"]


def test_sort_appointments_places_an_all_day_event_before_a_timed_event_the_same_day():
    """Un giornaliero comincia a mezzanotte: nello stesso giorno precede
    qualunque orario, senza bisogno di un caso speciale -- una data ISO e'
    prefisso di ogni orario di quel giorno (stessa proprieta' di
    `HAClient.calendar_events`).

    Mutazione: ordinare per `titolo` invece che per `dal` -- il test
    torna rosso su `assert titles == ["Giornaliero", "A orario"]`, che con
    l'ordine alfabetico troverebbe l'inverso.
    """
    appointments = [
        read_appointment(
            _timed_event(summary="A orario",
                         start={"dateTime": "2026-09-05T09:00:00+02:00"},
                         end={"dateTime": "2026-09-05T10:00:00+02:00"}),
            timezone="Europe/Rome"),
        read_appointment(
            _all_day_event(summary="Giornaliero",
                           start={"date": "2026-09-05"}, end={"date": "2026-09-06"}),
            timezone="Europe/Rome"),
    ]
    merged = sort_appointments(appointments)
    titles = [appointment["titolo"] for appointment in merged]
    assert titles == ["Giornaliero", "A orario"]


# --------------------------------------------------------------------------
# merge_calendars -- la logica del calendario, senza client (Tappa 5, Task 4)
# --------------------------------------------------------------------------

def test_merge_calendars_si_prova_senza_un_client_finto():
    """Uscita da `ToolDispatcher._calendar` il 05/10/2026 (R13): le risposte
    di Home Assistant arrivano gia' lette, e la fusione si prova con due
    dizionari. Un calendario che risponde `errore` e' nominato in
    `non_letti`, gli impegni dell'altro escono fusi e annotati.

    Mutazione ESEGUITA il 05/10/2026: tolto `unreadable.append(name)` sul
    ramo `errore` -- rossa su `non_letti` (KeyError: la chiave non esce)."""
    calendars = readable_calendars({"calendari": [
        {"entity_id": "calendar.personale", "name": "Personale"},
        {"entity_id": "calendar.rotto", "name": "Rotto"},
        "una voce malformata",
    ]})
    answers = [{"eventi": [_timed_event()]}, {"errore": "non risponde"}]

    result = merge_calendars(calendars, answers, timezone="Europe/Rome")

    assert result["calendari_guardati"] == ["Personale", "Rotto"]
    assert result["non_letti"] == ["Rotto"]
    assert [(a["titolo"], a["calendario"]) for a in result["impegni"]] == [
        ("Allenamento", "Personale")]
    assert "troncato" not in result
