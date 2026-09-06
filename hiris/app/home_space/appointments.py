"""Un impegno si legge come lo legge una persona, non come lo scrive HA.

Il Task 1 (`HAClient.calendar_events`, `proxy/ha_client.py`) legge i calendari
e i loro eventi GREZZI come Home Assistant li manda -- otto chiavi sempre,
`null` compresi, in ordine cronologico. Questo modulo compone: `read_appointment`
prende UN evento grezzo e lo trasforma in un IMPEGNO leggibile, con le chiavi
**italiane** che una risposta puo' mostrare direttamente (`titolo`, `inizio`,
`fine`, `giornaliero`, `luogo`, `descrizione`); `sort_appointments` fonde gli
impegni GIA' letti di uno o piu' calendari in un unico elenco ordinato.

E' PURO: nessuna rete, nessun archivio, niente da scrivere -- la stessa
scelta di `home_space/queries.py` e per la stessa ragione: e' cio' che lo
rende verificabile senza finti elaborati.

**La trappola, misurata sulla casa vera il 06/09/2026**: un evento
giornaliero ha la FINE ESCLUSIVA (convenzione iCal). «ANNIVERSARIO» va dal
`2026-08-30` al `2026-08-31` ed e' un giorno solo; «Ferie estive» va dal
`2026-08-17` al `2026-08-31` e finisce il 30 agosto. Verificato alla fonte,
non assunto: `home-assistant/core`,
`homeassistant/components/calendar/__init__.py`, sui tag RILASCIATI
`2024.7.0` (il minimo dichiarato da `hiris/config.yaml:22`) e `2026.9.0` (il
piu' recente visto finora) -- identico sui due tag. **La prova diretta e'
`_get_datetime_local`** (`2024.7.0:436-442`, `2026.9.0:464-470`): una `date`
nuda diventa `dt_util.start_of_local_day(...)`, cioe' la MEZZANOTTE
d'inizio di quella data -- percio' `end_datetime_local` di un giornaliero e'
la mezzanotte d'inizio di `end.date`, non un istante dentro quel giorno.
Ed e' cosi' che HA stessa smette di considerare "in corso" l'evento: lo
stato del calendario si spegne li' (`2026.9.0:601`,
`event.start_datetime_local <= now < event.end_datetime_local`) -- e' un
comportamento, non solo una correzione isolata. La prova INDIRETTA, che
conferma la stessa cosa da un altro lato: `CalendarEvent.__post_init__`
corregge un evento giornaliero con `start == end` allungando `end` di un
giorno esatto (`self.end = self.start + timedelta(days=1)`) per dargli una
durata di un giorno -- un giornaliero di un giorno solo ha percio' SEMPRE
`end.date == start.date + 1 giorno`, mai uguale. Sbagliare questa
convenzione sposta OGNI evento giornaliero di un giorno, ed e' un errore
che una persona nota subito perche' tocca esattamente la domanda per cui
questo modulo esiste ("fino a quando sono le ferie?").

**Per un evento a orario `end.dateTime` e' la fine vera e non si tocca** --
applicare la correzione anche li' sarebbe il difetto opposto.

**Il fuso e' quello della casa, non UTC**, e non si indovina: arriva come
parametro (`str | None` -- il produttore vero, `ToolDispatcher._timezone()`
in `home_space/tools.py:2314`, torna `None` quando il fuso non e' ancora
noto). Riusa `home_space_zone` (`historian.py`), che gestisce gia' il fuso
non riconosciuto con un avviso e il ripiego su UTC -- una seconda gestione
qui divergerebbe al primo caso strano.

Un `dateTime` a orario esce dalla vista di HA gia' passato per
`dt_util.as_local(...)`, e non per un'abitudine di questa o quella
integrazione: `CalendarEvent.__post_init__` valida OGNI istanza (qualunque
integrazione l'abbia creata) contro `CALENDAR_EVENT_SCHEMA`, che applica
`_as_local_timezone("start", "end")` -- verificato alla stessa fonte,
identico sui due tag. Il fuso locale e' un invariante dello SCHEMA di HA,
non una scelta di una integrazione in particolare. La riscrittura qui sotto
(`astimezone`, in `read_appointment`) e' percio' un NO-OP in pratica, non la
correzione di una divergenza fra calendari che non esiste -- la si tiene
comunque perche' e' la stessa disciplina che il resto del prodotto applica
a OGNI istante uscente (`historian.window`, `facts.day_boundaries`): il
fuso e' dichiarato esplicitamente via `home_space_zone`, non ereditato per
fiducia da una lettura di HA che questo modulo non riverifica ad ogni
chiamata.

**Le chiavi che non hanno niente da dire non escono.** Misurato: `description`
e `location` erano `null` su OGNI evento campionato sulla casa. Un
`luogo: None` invita chi legge a dire "senza luogo", che e' un'affermazione
che non si sa fare -- stessa disciplina di `elenco_incompleto`, `mute_da` ed
`entita_stato_ignoto` in `home_space/queries.py`. Un valore presente ma
tutto spazi bianchi non ha niente da dire piu' di un `null`: viene rifilato
(`strip()`) e trattato allo stesso modo se resta vuoto.

**`sort_appointments` prende impegni GIA' letti**, non eventi grezzi: legge
calendario per calendario spetta a chi chiama (il Task 3), perche' e' li'
che si puo' nominare un calendario che non risponde -- fondere prima
avrebbe perso quell'informazione. Il fuso non serve piu' su questa firma:
serviva solo perche' prima la funzione faceva due cose (leggere E fondere),
ed era gia' inerte per l'ORDINAMENTO (che lavora su `inizio`, stringa gia'
scritta) mentre contava solo per la LETTURA -- che ora e' compito di chi
chiama, una volta per calendario, prima di passare qui il risultato.
`sort_appointments` non serve a riordinare UN calendario, che arriva gia'
ordinato dal Task 1: serve a fondere gli impegni di PIU' calendari in un
elenco solo, perche' l'unione di due elenchi ordinati non e' ordinata da
sola.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import cache

from hiris.app.home_space.historian import home_space_zone


def _stripped_text(value) -> str:
    return (value or "").strip()


def _in_home_zone(raw: str, zone) -> str:
    """Un `dateTime` ISO-8601 -> lo stesso istante nel fuso della casa."""
    return datetime.fromisoformat(raw).astimezone(zone).isoformat()


@cache
def _cached_zone(timezone: str | None):
    """`home_space_zone(timezone)`, risolta una volta sola per ogni fuso
    DISTINTO -- delega, non reimplementa (`home_space_zone` resta l'unico
    posto che sa come leggere un fuso, condiviso con l'istoriografo).

    Leggere N impegni con lo STESSO `timezone` chiamerebbe altrimenti
    `home_space_zone` N volte: quando il fuso non e' riconosciuto,
    `home_space_zone` logga un avviso ad OGNI chiamata, e N impegni
    produrrebbero N avvisi identici per UN'UNICA configurazione sbagliata --
    il rumore su una cosa sola ripetuta che seppellisce cio' che conta, la
    stessa legge che il prodotto applica altrove. La cache e' per nome (una
    stringa, o `None`): due fusi diversi restano due risoluzioni distinte.
    """
    return home_space_zone(timezone)


def read_appointment(event: dict, *, timezone: str | None) -> dict:
    """UN evento grezzo del Task 1 -> UN impegno leggibile.

    Chiavi italiane, sempre le stesse due (`titolo`, `giornaliero`) piu'
    `inizio`/`fine`; `luogo`/`descrizione` SOLO quando hanno qualcosa da
    dire (vedi il modulo). `uid`, `recurrence_id` e `rrule` non escono: sono
    identificatori tecnici di HA, non parte di cio' che una persona legge.

    Un evento giornaliero ha `start.date` e `end.date`; un evento a orario
    ha `start.dateTime` e `end.dateTime` -- mai mescolati (verificato alla
    stessa fonte del modulo). La distinzione e' su `start`, non su `end`: le
    due forme viaggiano appaiate, HA non manda un giornaliero che finisce a
    orario.
    """
    start = event.get("start") or {}
    end = event.get("end") or {}
    all_day = "date" in start

    result: dict = {
        "titolo": _stripped_text(event.get("summary")),
        "giornaliero": all_day,
    }
    if all_day:
        result["inizio"] = start["date"]
        last_day = date.fromisoformat(end["date"]) - timedelta(days=1)
        result["fine"] = last_day.isoformat()
    else:
        zone = _cached_zone(timezone)
        result["inizio"] = _in_home_zone(start["dateTime"], zone)
        result["fine"] = _in_home_zone(end["dateTime"], zone)

    location = _stripped_text(event.get("location"))
    if location:
        result["luogo"] = location
    description = _stripped_text(event.get("description"))
    if description:
        result["descrizione"] = description
    return result


def sort_appointments(appointments: list[dict]) -> list[dict]:
    """Impegni GIA' letti (uno o piu' calendari, ciascuno gia' ordinato dal
    Task 1 e gia' passato per `read_appointment`) -> un unico elenco fuso,
    ordinato per `inizio`.

    Non riordina un calendario gia' ordinato: fonde. Ogni calendario arriva
    ordinato per conto suo, ma concatenare due elenchi ordinati non produce
    un elenco ordinato -- serve un ordinamento vero sull'unione, che e'
    esattamente cio' che c'e' qui.

    L'ordinamento e' lessicografico sull'`inizio` GIA' letto (stringa ISO
    con offset per un orario, data nuda per un giornaliero): basta, stessa
    proprieta' di `HAClient.calendar_events` (una data e' prefisso di ogni
    orario dello stesso giorno). **La stessa eccezione dichiarata li' resta
    IDENTICA qui, non migliora**: l'ultima domenica di ottobre, fra le 2 e
    le 3, `02:30+02:00` esce dopo `02:00+01:00` nel confronto
    lessicografico, perche' si confronta l'ora SCRITTA e non l'istante. Due
    impegni entrambi dentro quell'ora possono uscire invertiti; e'
    dichiarato, non corretto -- stessa scelta di `calendar_events`, per la
    stessa ragione (parsare ogni istante per un'ora l'anno costerebbe piu'
    di quanto valga).
    """
    return sorted(appointments, key=lambda appointment: appointment["inizio"])
