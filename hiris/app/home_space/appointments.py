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
in `home_space/tools.py`, torna `None` quando il fuso non e' ancora
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
(`historian.instant_out`, in `read_appointment`) e' percio' un NO-OP in pratica, non la
correzione di una divergenza fra calendari che non esiste -- la si tiene
comunque perche' e' la stessa disciplina che il resto del prodotto applica
a OGNI istante uscente (`historian.day_boundaries`): il
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

import logging
from datetime import date, timedelta
from functools import cache

# Import RELATIVO, come ogni altro modulo del prodotto. Assoluto
# (`from hiris.app...`) funziona nelle prove -- li' la radice del repo e' nel
# percorso e `hiris` E' un pacchetto -- e muore nel container, dove l'add-on e'
# installato sotto `/usr/lib/hiris/app/` e la radice del pacchetto si chiama
# `app`: `ModuleNotFoundError: No module named 'hiris'`, all'avvio, prima di
# qualunque riga di log. E' costato il guasto in produzione della v3.22.0
# (07/09/2026); il cancello che lo impedisce e' in
# `tests/test_import_boundary.py`.
from ..proxy._sanitize import sanitize_ha_free_text, sanitize_ha_value
from .historian import home_space_zone, instant_out

logger = logging.getLogger(__name__)


def _stripped_text(value) -> str:
    return (value or "").strip()


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
        result["inizio"] = instant_out(start["dateTime"], zone)
        result["fine"] = instant_out(end["dateTime"], zone)

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


def readable_calendars(listing: dict) -> list[dict]:
    """L'elenco dei calendari di `HAClient.calendars()` -> quelli che si possono
    provare a leggere: un dizionario con un `entity_id`. Una voce malformata
    si salta, non solleva."""
    calendars = listing.get("calendari")
    calendars = calendars if isinstance(calendars, list) else []
    return [entry for entry in calendars
            if isinstance(entry, dict) and entry.get("entity_id")]


def merge_calendars(calendars: list[dict], answers: list[dict], *,
                    timezone: str | None) -> dict:
    """I calendari provati e le loro risposte (`HAClient.calendar_events`,
    nello stesso ordine) -> la risposta dello strumento `calendar`.

    Uscita da `ToolDispatcher._calendar` il 05/10/2026 (Tappa 5, Task 4, R13):
    li' resta la composizione -- la finestra, le due letture, il fuso -- e qui
    la logica del calendario. E' PURA come il resto del modulo: le risposte di
    Home Assistant arrivano gia' lette, percio' si prova senza finti client.

    **Il cuore della fetta «i calendari»: la leggibilita' si verifica
    LEGGENDO, mai dallo stato.** Un calendario rotto e uno senza impegni
    hanno lo STESSO stato `off` in Home Assistant e tornerebbero lo
    STESSO elenco vuoto -- solo un tentativo di lettura li distingue.
    Percio' `_calendar` prende l'elenco dei calendari (Task 1,
    `HAClient.calendars()`) e prova a leggere CIASCUNO (Task 1,
    `HAClient.calendar_events()`), e qui si guarda ogni risposta, una per
    una: nessun elenco dichiarato di calendari ammessi, nessuna decisione presa dallo stato. Un
    calendario che fallisce NON sparisce in silenzio: il suo `name`
    finisce in `non_letti`, che esce SOLO se c'e' almeno un calendario
    illeggibile -- se sparisse, «non hai impegni» sarebbe una bugia detta
    con la sicurezza di chi ha guardato tutto, ed e' il difetto che la
    fetta precedente («le tracce e il log») ha trovato tre volte.

    **`calendari_guardati` esce SEMPRE, anche vuoto -- a differenza di
    `non_letti`/`troncato`, che tacciono quando non hanno niente da
    dire.** Senza di lui, zero calendari e due calendari letti e
    VUOTI sono indistinguibili: entrambi tornerebbero `{"impegni": []}`,
    e il modello direbbe «non hai impegni segnati» quando la verita'
    potrebbe essere «questa casa non ha calendari». E' la PROVA di cosa
    e' stato guardato, non un dato su cosa c'e' scritto: senza di essa
    la risposta non e' verificabile, quindi non e' condizionale come
    gli altri due.

    **Il tetto sul testo libero vive QUI, non nel client.**
    `HAClient.calendar_events()` lascia `summary`/`description`/
    `location` grezzi apposta (il suo docstring lo dice: nessun
    consumatore prima di questo strumento) -- e' questo il punto in cui
    quel testo, scritto da una persona in un calendario condiviso, entra
    DAVVERO in un prompt. `titolo`/`luogo`/`descrizione` passano da
    `sanitize_ha_free_text`, la stessa strada dei fratelli (`motivo` di
    un'integrazione rotta), non una seconda. **Il NOME del calendario passa da
    `sanitize_ha_value`** (non `sanitize_ha_free_text`: e' un
    `friendly_name`, la stessa forma di `nome` per le altre entita', non testo
    libero senza tetto HA) -- e' `state.name` di
    `HAClient.calendars()`, scelto da una persona e potenzialmente
    condiviso (un Google Calendar puo' esserlo), quindi un vettore di
    testo iniettato quanto `summary`/`description`/`location`: sanificare
    tre campi su quattro e lasciare il quarto grezzo sarebbe la stessa
    fuga che l'audit di questo prodotto ha gia' pagato altrove
    (L1-sicurezza.md). Sanificato UNA volta, prima di finire sia in
    `calendario` sia in `non_letti` -- non due sanificazioni per due
    destinazioni dello stesso valore.

    **Ogni impegno porta `calendario`**, il nome (non l'`entity_id`) del
    calendario da cui viene: fondendo «Personale» e «Famiglia» in un
    unico elenco, sapere DA QUALE viene un impegno e' meta' della
    risposta -- perderlo fondendo prima di annotarlo sarebbe
    un'informazione che avevamo in mano e abbiamo buttato via.

    **`troncato` esce SOLO se almeno un calendario lo ha dichiarato**
    (`HAClient.calendar_events`, `MAX_CALENDAR_EVENTS`): un elenco
    tagliato non deve poter sembrare completo, stessa legge del client
    che lo genera -- propagarla in silenzio sarebbe ricreare lo stesso
    difetto un livello piu' in alto. Non dice quale calendario (vedi la
    `description` dello strumento).

    **Un evento che non si sa interpretare affonda il SUO calendario,
    non tutti quanti.** `read_appointment` puo' sollevare (un evento
    senza ne' `start.date` ne' `start.dateTime`, per esempio): senza una
    guardia qui, quell'eccezione risalirebbe fino alla rete di
    sicurezza di `dispatch`, e la risposta perderebbe INSIEME gli
    impegni gia' letti di questo calendario e quelli di ogni altro
    calendario gia' letto bene in questo stesso giro -- il guasto di
    UNO che costa il silenzio su TUTTI, l'esatto difetto opposto a
    quello che questa fetta cura. Un calendario il cui evento non si sa
    interpretare finisce quindi in `non_letti` come uno che non
    risponde -- e i suoi impegni GIA' raccolti in questo giro si
    scartano: un elenco parziale che si finge completo e' peggio di un
    elenco assente, la stessa legge di `add_label_to` in
    `proxy/ha_client.py` («non ho letto» non e' «non ce n'erano»).
    """
    appointments: list[dict] = []
    examined: list[str] = []
    unreadable: list[str] = []
    truncated = False
    for entry, events in zip(calendars, answers, strict=True):
        name = sanitize_ha_value(entry.get("name") or entry["entity_id"])
        examined.append(name)
        if "errore" in events:
            unreadable.append(name)
            continue
        if events.get("troncato"):
            # Non gestito, DICHIARATO: se questo STESSO calendario viene
            # anche scartato qui sotto (un evento che non si sa
            # interpretare, `unreadable_event`), `truncated` resta vero
            # ma i suoi impegni finiscono comunque in `non_letti`, non in
            # `impegni` -- `troncato: true` sopravvivrebbe su un elenco
            # che non contiene piu' nessun impegno di QUESTO calendario.
            # Serve >MAX_CALENDAR_EVENTS eventi E un evento malformato
            # nello stesso calendario per innescarlo: visto, deciso di
            # non trattarlo (il caso e' cosi' raro da non giustificare
            # il costo di un secondo stato "troncato ma poi scartato").
            truncated = True
        calendar_appointments: list[dict] = []
        unreadable_event = False
        for raw_event in events.get("eventi") or []:
            try:
                appointment = read_appointment(raw_event, timezone=timezone)
            except Exception as error:
                logger.warning(
                    "calendario «%s»: un evento non si sa interpretare "
                    "(%s: %s) -- l'intero calendario finisce in non_letti",
                    name, type(error).__name__, error)
                unreadable_event = True
                break
            appointment["titolo"] = sanitize_ha_free_text(appointment["titolo"])
            if "luogo" in appointment:
                appointment["luogo"] = sanitize_ha_free_text(appointment["luogo"])
            if "descrizione" in appointment:
                appointment["descrizione"] = sanitize_ha_free_text(
                    appointment["descrizione"])
            appointment["calendario"] = name
            calendar_appointments.append(appointment)
        if unreadable_event:
            unreadable.append(name)
            continue
        appointments.extend(calendar_appointments)

    result: dict = {"impegni": sort_appointments(appointments),
                    "calendari_guardati": examined}
    if unreadable:
        result["non_letti"] = unreadable
    if truncated:
        result["troncato"] = True
    return result
