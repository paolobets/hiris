"""La storia della casa, con la stessa forma della porta (spec
`docs/design/2026-09-30-la-storia.md`).

Quattro strumenti diventano uno (decisione 1 del proprietario, 30/09/2026).
Misurato sul registro dei turni della v3.71.0: il diario rispondeva con
22.000-35.000 caratteri senza sapersi restringere, le tracce volevano una
chiamata per automazione (cinque per «perche' sono partite quelle dei
rifiuti»), e nessuno dei quattro sapeva scegliere di chi parlare coi filtri
di `search`.

Qui vivono solo funzioni PURE:
- `parse_query`: gli argomenti, gli errori e la finestra -- «oggi» e «ieri»
  nel fuso della casa (`historian.day_boundaries`);
- la scelta di chi, la profondita' e le righe di ogni genere (Task 3-5).

La scelta dei soggetti NON si fa qui: la fa `house_query.select_subjects`,
la stessa di `search` (spec §2, «un solo punto che decide di chi»). Chi
parla con Home Assistant e' il gestore di `tools.py`, che passa qui cio'
che ha letto: come `house_query`, questo modulo non conosce la rete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .historian import day_boundaries, home_space_zone, instant_epoch
from .house_query import BEHAVIOR_DOMAINS, HouseFilters, parse_filters

KINDS = ("stati", "valori", "esecuzioni", "errori")
#: Un giorno: la finestra che la parola «oggi» significa per chi chiede
#: «cosa e' successo?» senza dire quando (spec §2).
DEFAULT_HOURS = 24.0
#: Oltre 90 giorni non e' piu' una domanda sulla casa ma una scansione del
#: database: il tetto che aveva `trend` (24/08/2026), scelto e non misurato.
WINDOW_MAX_HOURS = 24 * 90
#: `system_log` raccoglie da `WARNING` in su (soglia, non elenco: verificato
#: sui tag `2024.7.0` e `2026.9.0`, `handler.setLevel(logging.WARNING)`).
LEVELS = ("WARNING", "ERROR", "CRITICAL")
#: I generi che leggono cio' che Home Assistant mostra ai soli
#: amministratori: `trace/list`, `trace/get`, `system_log/list` sono
#: `require_admin` (Core 2026.9.3, verificato il 27/09/2026, ruling R-2.25).
ADMIN_KINDS = frozenset({"esecuzioni", "errori"})
#: Le chiavi di «di chi», e della pagina: le stesse di `search`, lette da
#: `parse_filters` e da nessun altro.
_WHO_KEYS = ("nome", "riferimento", "tipo", "classe", "area", "piano",
             "integrazione", "includi_nascoste", "includi_servizio",
             "limite", "salta")
#: Il registro di Home Assistant non sa di aree ne' di cose della casa: per
#: gli errori valgono solo l'integrazione (e `livello`), piu' la pagina.
_ERROR_WHO_KEYS = frozenset({"integrazione", "limite", "salta"})


@dataclass(frozen=True)
class HistoryQuery:
    """Una domanda alla storia, gia' validata: cosa, di chi, quando."""
    kind: str
    who: HouseFilters
    start: datetime
    end: datetime
    run_id: str | None = None
    level: str | None = None

    @property
    def hours(self) -> float:
        """Le ore VERE: la differenza di due `datetime` con lo stesso `ZoneInfo`
        e' quella dell'ora del muro, quindi il giorno del cambio d'ora dura
        24 ore invece di 25 (misurato il 30/09/2026 sul 25/10). Si passa per
        l'epoch."""
        return (self.end.timestamp() - self.start.timestamp()) / 3600


def _given(a: dict, key: str) -> bool:
    return a.get(key) is not None and a.get(key) != ""


def _wrong_for_kind(kind: str, a: dict) -> str | None:
    """Il filtro che non vale per questo genere, detto (spec §2): ignorato,
    la storia risponderebbe con sicurezza a un'altra domanda."""
    if _given(a, "esecuzione") and kind != "esecuzioni":
        return "esecuzione vale solo con genere=esecuzioni"
    if _given(a, "livello") and kind != "errori":
        return "livello vale solo con genere=errori"
    if kind == "errori":
        wrong = [key for key in _WHO_KEYS if _given(a, key) and key not in _ERROR_WHO_KEYS]
        if wrong:
            verb = "vale" if len(wrong) == 1 else "valgono"
            return (f"{', '.join(wrong)}: non {verb} per genere=errori -- il registro "
                    "di Home Assistant non sa di aree ne' di cose della casa: accetta "
                    "solo integrazione e livello")
    if kind == "esecuzioni":
        if _given(a, "classe"):
            return ("classe non vale per genere=esecuzioni: le esecuzioni sono di "
                    "automazioni e script")
        if _given(a, "tipo") and a["tipo"] not in BEHAVIOR_DOMAINS:
            return ("genere=esecuzioni vale per automazioni e script: tipo accetta "
                    "automation o script")
        reference = str(a.get("riferimento") or "")
        if reference and reference.split(".", 1)[0] not in BEHAVIOR_DOMAINS:
            return (f"«{reference}» non e' un'automazione ne' uno script: "
                    "genere=esecuzioni vale solo per loro")
    return None


def _instant(raw, name: str, *, now: float, timezone: str | None) -> datetime | str:
    """Un estremo della finestra: «oggi», «ieri» o un istante ISO col fuso.

    «oggi»/«ieri» si risolvono nel fuso della casa (`day_boundaries`, lo
    stesso calcolo del resto di HIRIS): come `da` sono la mezzanotte che li
    apre; come `a`, «oggi» e' adesso e «ieri» la mezzanotte che lo chiude.
    Un istante senza fuso si rifiuta (`instant_epoch`): «alle 8» di quale
    fuso?"""
    zone = home_space_zone(timezone)
    word = str(raw).strip().lower()
    if word in ("oggi", "ieri"):
        today = datetime.fromtimestamp(now, tz=zone).date()
        day = today if word == "oggi" else today - timedelta(days=1)
        start_ts, end_ts = day_boundaries(day.isoformat(), timezone)
        if name == "da":
            return datetime.fromtimestamp(start_ts, tz=zone)
        return datetime.fromtimestamp(min(end_ts, now), tz=zone)
    epoch = instant_epoch(str(raw))
    if epoch is None:
        return (f"{name} vuole «oggi», «ieri» o un istante ISO col fuso "
                "(es. 2026-09-30T08:00:00+02:00)")
    return datetime.fromtimestamp(epoch, tz=zone)


def _window(a: dict, *, now: float,
            timezone: str | None) -> tuple[datetime, datetime] | str:
    """(inizio, fine) nel fuso della casa, o la frase dell'errore."""
    zone = home_space_zone(timezone)
    now_local = datetime.fromtimestamp(now, tz=zone)
    by_range = _given(a, "da") or _given(a, "a")
    if a.get("ore") is not None and by_range:
        return "ore e da/a insieme: una finestra si dice in un modo solo"
    if by_range:
        if not _given(a, "da"):
            return "a vuole anche da: da quando?"
        start = _instant(a["da"], "da", now=now, timezone=timezone)
        end = (_instant(a["a"], "a", now=now, timezone=timezone)
               if _given(a, "a") else now_local)
        for moment in (start, end):
            if isinstance(moment, str):
                return moment
    else:
        try:
            hours = float(a["ore"]) if a.get("ore") is not None else DEFAULT_HOURS
        except (TypeError, ValueError, OverflowError):
            return "ore vuole un numero di ore"
        if not 0 < hours <= WINDOW_MAX_HOURS:
            return f"ore va da piu' di 0 a {WINDOW_MAX_HOURS} (90 giorni)"
        start, end = now_local - timedelta(hours=hours), now_local
    # Confronti sull'epoch, mai tra `datetime` dello stesso fuso: quelli
    # ignorano il cambio d'ora (vedi `HistoryQuery.hours`).
    if end.timestamp() > now:
        return "a e' nel futuro: la storia arriva al piu' ad adesso"
    if start.timestamp() >= end.timestamp():
        return "da deve venire prima di a"
    if end.timestamp() - start.timestamp() > WINDOW_MAX_HOURS * 3600:
        return f"la finestra supera i 90 giorni ({WINDOW_MAX_HOURS} ore): restringila"
    return start, end


def parse_query(arguments: dict, *, now: float,
                timezone: str | None) -> HistoryQuery | dict:
    """Gli argomenti di `history` -> una domanda validata, o `{"errore"}`."""
    a = dict(arguments or {})
    kind = a.get("genere") or "stati"
    if kind not in KINDS:
        return {"errore": f"genere «{kind}» sconosciuto: {', '.join(KINDS)}"}
    wrong = _wrong_for_kind(kind, a)
    if wrong:
        return {"errore": wrong}
    window = _window(a, now=now, timezone=timezone)
    if isinstance(window, str):
        return {"errore": window}
    who = parse_filters({key: a[key] for key in _WHO_KEYS if key in a})
    if isinstance(who, dict):
        return who
    level = None
    if _given(a, "livello"):
        level = str(a["livello"]).strip().upper()
        if level not in LEVELS:
            return {"errore": f"livello accetta {', '.join(LEVELS)}"}
    run_id = a.get("esecuzione")
    if run_id is not None:
        if not isinstance(run_id, str) or not run_id.strip():
            return {"errore": "esecuzione, se c'e', e' il run_id di una riga delle "
                              "esecuzioni: un testo non vuoto"}
        run_id = run_id.strip()
    start, end = window
    return HistoryQuery(kind=kind, who=who, start=start, end=end, run_id=run_id,
                        level=level)
