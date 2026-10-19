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
from ..keeper.delivery import arrived
from .store import ObservationsStore
from .watcher import ROUNDS_BEFORE_CLOSING

#: I fermi che si dicono al proprietario. Uno stato che il vocabolario non
#: conosce (`ENTRY_UNKNOWN_STATE`) no: l'osservatore lo annota, ma chi parla
#: al proprietario ne tace -- la ragione sta accanto a `config_entry_stop`.
TOLD_STOPS = frozenset({ENTRY_SWITCHED_OFF, ENTRY_BROKEN})


async def tell(store: ObservationsStore, house: House, integrations: list[dict] | None,
               *, notify: Callable[[str], Awaitable[dict]], now: float) -> dict | None:
    """Un giro dell'avviso, sulle righe grezze di `config_entries`
    (`app[HA_INTEGRATIONS_KEY]`). Torna il resoconto di `notify`, o `None` se
    non c'era niente da dire.

    `integrations` a `None` -- l'elenco non e' ancora arrivato -- non e' una
    casa senza integrazioni: il giro non tocca niente. Un'istanza che Home
    Assistant non elenca piu' si dimentica senza avviso: e' stata tolta, non
    si e' fermata."""
    if integrations is None:
        return None
    before = store.integration_notices()
    rows: dict[str, dict] = {}
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
        if streak < ROUNDS_BEFORE_CLOSING:
            continue
        if stop is not None and told is None:
            stops.append((ident, raw, stop))
        elif stop is None and told is not None:
            returns.append((ident, raw))
    report = None
    if stops or returns:
        lines = [_stop_line(house, raw, stop) for _ident, raw, stop in stops]
        lines += [f"{_who(raw)} è tornata a funzionare." for _ident, raw in returns]
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
    cause = ("è spenta da te" if stop == ENTRY_SWITCHED_OFF
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
