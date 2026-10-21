"""L'avviso delle **integrazioni ferme**: quando un'istanza d'integrazione si
ferma -- spenta dal proprietario o in errore -- una push agli amministratori,
con i dispositivi e le stanze che restano senza; quando torna, una riga.

Richiesta del proprietario del 15/10/2026: un'integrazione con 61 dispositivi
spenta e nessuno che lo dicesse. Decisioni del 16/10/2026: la prima volta le
istanze gia' ferme vanno in UNA push riassuntiva; al ritorno, una riga.
Proposta: `/mnt/project-files/chiusura/integrazioni-ferme-proposta.md`.

**Perche' non e' un'automazione di Home Assistant** (Legge I, letto nel
sorgente al tag 2026.9.4): nessun trigger scatta sul cambio di stato di
un'istanza -- viaggia come segnale interno (`SIGNAL_CONFIG_ENTRY_CHANGED`),
non come evento sul bus -- e Home Assistant non apre una riparazione ne' per
un'istanza spenta ne' per una in `setup_error`/`setup_retry`. HIRIS il cambio
lo vede gia', dall'iscrizione `config_entries/subscribe`, e sa quali
dispositivi appartengono a quale istanza.

**Due giri, non uno.** Un'istanza si dice ferma dopo `ROUNDS_BEFORE_CLOSING`
giri di fila che la vedono ferma, e tornata dopo altrettanti che la vedono
andare: e' l'isteresi dell'osservatore, misurata il 03/09 sui `setup_retry`
che spariscono per un giro e tornano. Al riavvio di Home Assistant le istanze
passano da stati di passaggio, e un avviso per giro sarebbe una raffica.

**Una volta sola anche dopo un riavvio**: cio' che si e' detto sta
nell'archivio dell'osservatore (`integration_notice`), e si segna come detto
solo cio' che e' arrivato a un telefono (`keeper/delivery.arrived`): un avviso
che non e' partito si ritenta al giro dopo.

**E una notifica persistente in Home Assistant** (richiesta del proprietario
del 21/10/2026: la push toccata apre Home Assistant e sparisce). La push dice
cosa e' cambiato; la notifica (`NOTICE_ID`, una sola) dice com'e' adesso: una
riga per ogni istanza ferma da almeno `ROUNDS_BEFORE_CLOSING` giri, che si
riscrive quando l'elenco cambia e si toglie quando l'ultima torna. Segue lo
stato, non la push: c'e' anche quando nessun telefono l'ha ricevuta.

Il testo lo compone il codice, non un modello: non e' un agente (Legge III).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..home_space.ha_vocabulary import (
    ENTRY_BROKEN,
    ENTRY_SWITCHED_OFF,
    config_entry_stop,
)
from ..home_space.house import House
from ..home_space.reader import clean_name
from ..keeper.delivery import NOTICE_HINT, arrived
from ..keeper.promise import DELIVERY_TITLE
from .store import ObservationsStore
from .watcher import ROUNDS_BEFORE_CLOSING

#: I fermi che si dicono al proprietario. Uno stato che il vocabolario non
#: conosce (`ENTRY_UNKNOWN_STATE`) no: l'osservatore lo annota, ma chi parla
#: al proprietario ne tace -- la ragione sta accanto a `config_entry_stop`.
TOLD_STOPS = frozenset({ENTRY_SWITCHED_OFF, ENTRY_BROKEN})

#: L'id della notifica persistente, uno solo per tutte le istanze ferme
#: (scelta del proprietario, 21/10/2026): viaggia verso Home Assistant, e
#: porta il suo nome in inglese.
NOTICE_ID = "hiris_stopped_integrations"
NOTICE_TITLE = f"{DELIVERY_TITLE} · integrazioni ferme"


async def tell(store: ObservationsStore, house: House, integrations: list[dict] | None,
               *, notify: Callable[[str], Awaitable[dict]],
               show: Callable[[dict], Awaitable[dict]], now: float) -> dict | None:
    """Un giro dell'avviso, sulle righe grezze di `config_entries`
    (`app[HA_INTEGRATIONS_KEY]`). Torna il resoconto di `notify`, o `None` se
    non c'era niente da dire.

    `show` riceve a ogni giro la notifica persistente che deve esserci,
    `{NOTICE_ID: (titolo, testo)}`, o `{}` quando non c'e' niente di fermo
    (`keeper/delivery.align_notices`). Viene prima della push, cosi' la push
    dice `NOTICE_HINT` solo se la notifica c'e' davvero.

    `integrations` a `None` -- l'elenco non e' ancora arrivato -- non e' una
    casa senza integrazioni: il giro non tocca niente. Un'istanza che Home
    Assistant non elenca piu' si dimentica senza avviso: e' stata tolta, non
    si e' fermata."""
    if integrations is None:
        return None
    before = store.integration_notices()
    rows: dict[str, dict] = {}
    standing: list[tuple[dict, str]] = []
    stops: list[tuple[str, dict, str]] = []
    returns: list[tuple[str, dict]] = []
    for raw in integrations:
        if not isinstance(raw, dict) or not raw.get("entry_id"):
            continue
        ident = str(raw["entry_id"])
        stop = config_entry_stop(raw.get("state"), raw.get("disabled_by"), raw.get("source"))
        if stop not in TOLD_STOPS:
            stop = None
        old = before.get(ident)
        streak = old["giri"] + 1 if old and old["fermo"] == stop else 1
        told = old["detta"] if old else None
        if stop is None and told is None:
            continue  # va, e nessuno ha detto il contrario: niente da ricordare
        rows[ident] = {"fermo": stop, "giri": streak, "detta": told, "visto_ts": now}
        if stop is not None and (told is not None or streak >= ROUNDS_BEFORE_CLOSING):
            standing.append((raw, stop))
        if streak < ROUNDS_BEFORE_CLOSING:
            continue
        if stop is not None and told is None:
            stops.append((ident, raw, stop))
        elif stop is None and told is not None:
            returns.append((ident, raw))
    wanted = ({NOTICE_ID: (NOTICE_TITLE, "\n".join(
        _stop_line(house, raw, stop) for raw, stop in standing))} if standing else {})
    shown = await show(wanted)
    report = None
    if stops or returns:
        lines = [_stop_line(house, raw, stop) for _ident, raw, stop in stops]
        lines += [f"{_who(raw)} è tornata a funzionare." for _ident, raw in returns]
        if stops and NOTICE_ID in (shown.get("allineate") or ()):
            lines.append(NOTICE_HINT)
        report = await notify("\n".join(lines))
        if arrived(report):
            for ident, _raw, stop in stops:
                rows[ident]["detta"] = stop
            for ident, _raw in returns:
                rows.pop(ident)
    store.keep_integration_notices(rows)
    return report


def _who(raw: dict) -> str:
    """«L’integrazione «Casa» (ave_domina)»: il titolo della voce e il
    dominio, perche' il titolo non e' il nome dell'integrazione (per LIFX c'e'
    una voce per lampadina) -- la stessa scelta del nucleo."""
    title = clean_name(raw.get("title"))
    domain = str(raw.get("domain") or "").strip()
    if title and domain:
        return f"L’integrazione «{title}» ({domain})"
    return f"L’integrazione {title or domain or raw.get('entry_id')}"


def _stop_line(house: House, raw: dict, stop: str) -> str:
    # «è stata spenta», non «da te» (scelta del proprietario, 19/10/2026,
    # N180-3): la push va a ogni amministratore, e Home Assistant non dice
    # chi l'ha spenta -- `ConfigEntryDisabler` ha un valore solo, `user`.
    cause = ("è stata spenta" if stop == ENTRY_SWITCHED_OFF
             else f"è in errore ({raw.get('state')})")
    devices = house.instance_devices(str(raw.get("entry_id")))
    if not devices:
        return f"{_who(raw)} {cause}: nessun suo dispositivo è nell’anagrafe."
    count = ("1 dispositivo non è più disponibile" if len(devices) == 1
             else f"{len(devices)} dispositivi non sono più disponibili")
    areas = sorted({place[0]["nome"] for d in devices if d.get("area_id")
                    for place in [house.area_place(d["area_id"])]
                    if place and place[0].get("nome")})
    where = f" ({', '.join(areas)})" if areas else ""
    return f"{_who(raw)} {cause}: {count}{where}."
