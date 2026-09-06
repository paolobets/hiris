"""Un impegno si legge come lo legge una persona, non come lo scrive HA.

Il Task 1 (`HAClient.calendar_events`, `proxy/ha_client.py`) legge i calendari
e i loro eventi GREZZI come Home Assistant li manda -- otto chiavi sempre,
`null` compresi, in ordine cronologico. Questo modulo compone: prende UN
evento grezzo e lo trasforma in un IMPEGNO leggibile, con le chiavi
**italiane** che una risposta puo' mostrare direttamente (`titolo`, `inizio`,
`fine`, `giornaliero`, `luogo`, `descrizione`).

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
piu' recente visto finora) -- identico sui due tag. `CalendarEvent.
__post_init__` corregge un evento giornaliero con `start == end` allungando
`end` di un giorno esatto (`self.end = self.start + timedelta(days=1)`) per
dargli una durata di un giorno: un giornaliero di un giorno solo ha percio'
SEMPRE `end.date == start.date + 1 giorno`, mai uguale. E' la stessa
semantica di RFC 5545 (`DTEND` esclusivo), incarnata nel modello dati di HA
stesso, non solo nella spec: sbagliarla sposta OGNI evento giornaliero di un
giorno, ed e' un errore che una persona nota subito perche' tocca esattamente
la domanda per cui questo modulo esiste ("fino a quando sono le ferie?").

**Per un evento a orario `end.dateTime` e' la fine vera e non si tocca** --
applicare la correzione anche li' sarebbe il difetto opposto.

**Il fuso e' quello della casa, non UTC**, e non si indovina: arriva come
parametro. Riusa `home_space_zone` (`historian.py`), che gestisce gia' il
fuso non riconosciuto con un avviso e il ripiego su UTC -- una seconda
gestione qui divergerebbe al primo caso strano. Un `dateTime` a orario esce
dalla vista di HA gia' passato per `dt_util.as_local(...)` (verificato alla
stessa fonte, `_api_event_dict_factory`), quindi e' gia' nel fuso
dell'istanza; questo modulo lo riscrive comunque nel fuso della casa
(`astimezone`) invece di limitarsi a fidarsi -- e' cio' che rende il
confronto lessicografico di `sort_appointments` qui sotto valido anche
quando gli impegni arrivano da calendari/integrazioni diverse, non solo da
uno che HA ha gia' normalizzato per conto suo.

**Le chiavi che non hanno niente da dire non escono.** Misurato: `description`
e `location` erano `null` su OGNI evento campionato sulla casa. Un
`luogo: None` invita chi legge a dire "senza luogo", che e' un'affermazione
che non si sa fare -- stessa disciplina di `elenco_incompleto`, `mute_da` ed
`entita_stato_ignoto` in `home_space/queries.py`. Un valore presente ma
tutto spazi bianchi non ha niente da dire piu' di un `null`: viene rifilato
(`strip()`) e trattato allo stesso modo se resta vuoto.

**`sort_appointments` non serve a riordinare UN calendario** -- quello arriva
gia' ordinato dal Task 1, e riordinarlo sarebbe lavoro sprecato. Serve a
**fondere gli impegni di PIU' calendari** in un elenco solo: ciascuno arriva
ordinato per conto suo, ma l'unione di due elenchi ordinati non e' ordinata
da sola. E' per questo che chiede `timezone`: legge ogni evento grezzo con
`read_appointment` (che normalizza il fuso, sopra) prima di fonderli, cosi'
il confronto per `inizio` resta valido anche a cavallo di calendari diversi.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from hiris.app.home_space.historian import home_space_zone


def _stripped_text(value) -> str:
    return (value or "").strip()


def _in_home_zone(raw: str, zone) -> str:
    """Un `dateTime` ISO-8601 -> lo stesso istante nel fuso della casa."""
    return datetime.fromisoformat(raw).astimezone(zone).isoformat()


def read_appointment(event: dict, *, timezone: str) -> dict:
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
        zone = home_space_zone(timezone)
        result["inizio"] = _in_home_zone(start["dateTime"], zone)
        result["fine"] = _in_home_zone(end["dateTime"], zone)

    location = _stripped_text(event.get("location"))
    if location:
        result["luogo"] = location
    description = _stripped_text(event.get("description"))
    if description:
        result["descrizione"] = description
    return result


def sort_appointments(events: list[dict], *, timezone: str) -> list[dict]:
    """Gli eventi grezzi di UNO O PIU' calendari -> un unico elenco di
    impegni leggibili, ordinato per `inizio`.

    Non riordina un calendario gia' ordinato (lo fa gia' il Task 1): fonde.
    Ogni calendario arriva ordinato per conto suo, ma concatenare due elenchi
    ordinati non produce un elenco ordinato -- serve un ordinamento vero
    sull'unione, che e' esattamente cio' che c'e' qui.

    L'ordinamento e' sull'`inizio` GIA' letto (stringa ISO nel fuso della
    casa per un orario, data nuda per un giornaliero): lessicografico basta,
    stessa proprieta' di `HAClient.calendar_events` (una data e' prefisso di
    ogni orario dello stesso giorno) -- e regge qui a maggior ragione,
    perche' `read_appointment` ha gia' riportato ogni orario nello stesso
    fuso, cosa che il singolo client non garantisce fra calendari diversi.
    """
    appointments = [read_appointment(event, timezone=timezone) for event in events]
    return sorted(appointments, key=lambda appointment: appointment["inizio"])
