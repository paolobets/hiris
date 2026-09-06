"""«Quali sono i miei prossimi appuntamenti?» -- un evento grezzo del Task 1
diventa un impegno che una persona legge.

`read_appointment` compone UN evento; `sort_appointments` fonde impegni GIA'
letti di piu' calendari (ciascuno gia' ordinato per conto suo) in un unico
elenco ordinato -- vedi `hiris/app/home_space/appointments.py` per il perche'
di ogni scelta, in particolare la trappola della fine esclusiva sui
giornalieri (misurata sulla casa vera il 06/09/2026) e la legge sulle chiavi
che non hanno niente da dire.
"""
from unittest.mock import patch

from hiris.app.home_space import appointments as appointments_module
from hiris.app.home_space.appointments import read_appointment, sort_appointments


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
# read_appointment -- la trappola della fine esclusiva
# --------------------------------------------------------------------------

def test_an_all_day_event_ends_the_day_before_its_end_date():
    """Misurato sulla casa vera il 06/09/2026: «ANNIVERSARIO» va dal 30 al 31
    agosto ed e' UN GIORNO SOLO; «Ferie estive» dal 17 al 31 finisce il 30. E'
    la fine esclusiva di iCal, e sbagliarla sposta OGNI evento giornaliero di
    un giorno.

    Mutazione: usare `end["date"]` cosi' com'e' -- il test torna rosso su
    `assert appointment["fine"] == "2026-08-30"`.
    """
    appointment = read_appointment(
        {"start": {"date": "2026-08-17"}, "end": {"date": "2026-08-31"},
         "summary": "Ferie estive ", "description": None, "location": None,
         "uid": "270019B2", "recurrence_id": None, "rrule": None},
        timezone="Europe/Rome")
    assert appointment["giornaliero"] is True
    assert appointment["inizio"] == "2026-08-17"
    assert appointment["fine"] == "2026-08-30"


def test_a_single_day_all_day_event_lasts_exactly_one_day():
    """Il caso misurato per «ANNIVERSARIO»: `start` e `end` un giorno
    diverso, ma la durata vera e' un giorno solo -- `inizio` e `fine`
    devono coincidere.

    Mutazione: non sottrarre nessun giorno (`end["date"]` cosi' com'e') --
    il test torna rosso su `assert appointment["fine"] == "2026-08-30"`, che
    troverebbe invece `"2026-08-31"`.
    """
    appointment = read_appointment(_all_day_event(), timezone="Europe/Rome")
    assert appointment["inizio"] == "2026-08-30"
    assert appointment["fine"] == "2026-08-30"


def test_a_timed_event_keeps_its_end_untouched():
    """La correzione vale SOLO per i giornalieri: su un evento a orario la
    fine e' la fine, e togliere un giorno anche li' sarebbe il difetto
    opposto. L'evento arriva in UTC apposta: un `fine` corretto deve anche
    portare il fuso della casa, non solo il giorno giusto.

    Mutazione: applicare il -1 anche al ramo a orario -- il test torna rosso
    su `assert appointment["fine"] == "2026-09-05T23:00:00+02:00"`.
    """
    appointment = read_appointment(
        _timed_event(start={"dateTime": "2026-09-05T20:00:00+00:00"},
                     end={"dateTime": "2026-09-05T21:00:00+00:00"}),
        timezone="Europe/Rome")
    assert appointment["giornaliero"] is False
    assert appointment["inizio"] == "2026-09-05T22:00:00+02:00"
    assert appointment["fine"] == "2026-09-05T23:00:00+02:00"


def test_a_timed_event_is_rewritten_in_the_home_timezone_not_left_as_is():
    """`home_space_zone` (riusato, non reinventato) decide il fuso: un
    istante che arriva in un fuso diverso da quello della casa deve uscire
    riscritto, non lasciato com'e'.

    Mutazione: emettere `start["dateTime"]`/`end["dateTime"]` grezzi senza
    passare da `home_space_zone`/`astimezone` -- il test torna rosso su
    `assert appointment["inizio"] == "2026-09-05T22:00:00+02:00"`, che
    troverebbe invece la stringa UTC originale.
    """
    appointment = read_appointment(
        _timed_event(start={"dateTime": "2026-09-05T20:00:00+00:00"}),
        timezone="Europe/Rome")
    assert appointment["inizio"] == "2026-09-05T22:00:00+02:00"


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
    assert appointment["inizio"] == "2026-09-05T20:00:00+00:00"


def test_a_missing_timezone_falls_back_to_utc_too():
    """`read_appointment(..., timezone=None)` e' un caso VERO, non un
    capriccio della firma: `ToolDispatcher._timezone()` (`tools.py:2314`)
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
    assert appointment["inizio"] == "2026-09-05T20:00:00+00:00"


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
    `titolo`, `inizio`, `fine`, `giornaliero`, `luogo`, `descrizione`.

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


def test_sort_appointments_only_looks_at_inizio_not_at_a_raw_event():
    """`sort_appointments` prende impegni GIA' letti, non eventi grezzi da
    rileggere: non ha bisogno di nessun altro campo che `inizio` per fare
    il suo lavoro, ed e' per questo che la firma non porta piu' `timezone`
    (serviva solo perche' prima la funzione leggeva ANCHE, non solo
    fondeva).

    Mutazione: provare a rileggere l'evento (es. cercare `start`/`end`
    invece di usare `inizio` gia' scritto) -- il test torna rosso su
    `assert titles == ["a", "b"]`, con un `KeyError: 'start'` (questi
    impegni minimi non hanno `start`, solo `inizio` e `titolo`).
    """
    minimal = [{"titolo": "b", "inizio": "2026-09-05T10:00:00+02:00"},
               {"titolo": "a", "inizio": "2026-09-05T08:00:00+02:00"}]
    merged = sort_appointments(minimal)
    titles = [appointment["titolo"] for appointment in merged]
    assert titles == ["a", "b"]


def test_sort_appointments_places_an_all_day_event_before_a_timed_event_the_same_day():
    """Un giornaliero comincia a mezzanotte: nello stesso giorno precede
    qualunque orario, senza bisogno di un caso speciale -- una data ISO e'
    prefisso di ogni orario di quel giorno (stessa proprieta' di
    `HAClient.calendar_events`).

    Mutazione: ordinare per `titolo` invece che per `inizio` -- il test
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
