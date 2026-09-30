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

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from .behavior import BEHAVIOR_DOMAINS
from .historian import day_boundaries, home_space_zone, instant_epoch
from .house_query import (
    DETAIL_MEDIUM_MAX,
    HouseFilters,
    excluded_note,
    page_rows,
    parse_filters,
    select_subjects,
)
from .privacy import redact_state

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
        raw_hours = a.get("ore")
        try:
            if isinstance(raw_hours, bool):
                raise TypeError("un booleano non e' un numero di ore")
            hours = float(raw_hours) if raw_hours is not None else DEFAULT_HOURS
            if not math.isfinite(hours):
                raise ValueError("nan e inf non sono ore")
        except (TypeError, ValueError, OverflowError):
            return "ore vuole un numero di ore"
        if not 0 < hours <= WINDOW_MAX_HOURS:
            return f"ore va da piu' di 0 a {WINDOW_MAX_HOURS} (90 giorni)"
        # Dall'epoch, mai `now_local - timedelta`: in ora del muro il giorno
        # del cambio d'ora sbagliava di un'ora (24 ore chiedevano 25 vere).
        start = datetime.fromtimestamp(now - hours * 3600, tz=zone)
        end = now_local
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


#: Quanto possono distare un atto della cronaca e il cambio che ne e'
#: l'effetto (da `historian.MATCH_TOLERANCE_S`, 24/08/2026): Home Assistant
#: non firma i cambi, l'unico aggancio e' entita' + istante vicino, ed e' per
#: questo che l'abbinamento si dice «probabile».
MATCH_TOLERANCE_S = 60
_NARROW = ("prima restringi -- una finestra piu' corta, un'area, un nome --; "
           "scorri con salta solo se ti servono davvero tutte")
_NOTHING_CHOSEN = ("nessuna cosa di questa casa corrisponde a questi filtri: cerca "
                   "il nome con `search` e richiama `history` col suo `riferimento`")
_JOURNAL_UNREAD = ("non ho potuto leggere la mia cronaca: un cambio senza "
                   "per_mano_di potrebbe essere comunque mio")
#: Tre cause danno lo STESSO vuoto, e da qui non si distinguono (la nota di
#: `trend`, 24/08/2026): `purge_keep_days` non e' leggibile da nessuna API.
_NO_RECORDING = ("nessuna registrazione in questa finestra: la finestra puo' andare "
                 "oltre cio' che Home Assistant conserva, l'entita' puo' essere esclusa "
                 "dalla registrazione, o non esistere piu' -- da qui non si distingue")
_TRUNCATED = ("Home Assistant aveva piu' cambi di quanti se ne leggono in una volta: "
              "ho tenuto i piu' recenti, e i piu' vecchi della finestra mancano")
_NOTHING = object()


@dataclass(frozen=True)
class Subject:
    """Un soggetto della storia: l'identificatore, il nome, e l'ultimo cambio
    (entita') o l'ultima esecuzione (automazioni e script) secondo lo
    specchio. NON ordina la corta degli stati: l'ordine lo da' la finestra
    letta (revisione del Task 3, 30/09/2026 -- vedi `Chosen`)."""
    ident: str
    name: str
    last: str | None = None


@dataclass(frozen=True)
class Chosen:
    """Chi, quanti e quanto: `found` conta i soggetti scelti, `subjects` sono
    TUTTI quelli da leggere a Home Assistant (vuoto solo con `limite` 0, che
    chiede il conto), in ogni profondita'. La pagina si taglia DOPO la
    lettura, in `state_rows`.

    Revisione del Task 3 (30/09/2026): la prima forma tagliava la pagina
    della corta QUI, ordinata per l'ultimo cambio dello specchio. Provato su
    16 luci con `limite=5`: le 5 mostrate avevano tutte `cambi: 0`, e l'unica
    cambiata 5 volte nella finestra restava fuori; con `da`/`a` nel passato
    la pagina era arbitraria, e in una casa viva `salta` scorreva su un
    ordine che cambiava fra una chiamata e l'altra. Una chiamata a
    `HAClient.history` copre molte entita': si legge tutto, si ordina per cio'
    che e' successo NELLA finestra, e poi si impagina."""
    found: int
    excluded: dict
    depth: str
    subjects: list[Subject]


def depth_for(count: int) -> str:
    """Spec §3: 1 -> completa, 2-10 -> media, oltre 10 -> corta (la soglia
    della porta, `DETAIL_MEDIUM_MAX`)."""
    if count == 1:
        return "completa"
    return "media" if count <= DETAIL_MEDIUM_MAX else "corta"


def _epoch(raw) -> float | None:
    """Un istante in secondi: ISO col fuso (storico, tracce) o gia' numero
    (il registro di Home Assistant). `None` se non si legge."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return float(raw)
    return instant_epoch(raw)


def _local(raw, zone) -> str | None:
    """Un istante nel fuso della casa. Lo storico e le tracce tornano in UTC:
    due offset nella stessa risposta sono la fondamenta 3 rotta (misurato il
    24/08/2026 su `trend`). Cio' che non si legge resta com'e', come testo:
    meglio un formato inatteso che un istante inventato."""
    if raw is None:
        return None
    epoch = _epoch(raw)
    if epoch is None:
        return str(raw)
    return datetime.fromtimestamp(epoch, tz=zone).isoformat()


def _page(rows: list, f: HouseFilters) -> tuple[list, dict | None]:
    """Il tetto nella regola (spec §3), con la pagina di `search`: un punto
    solo, `house_query.page_rows` (30/09/2026)."""
    return page_rows(rows, f.offset, f.limit)


def choose(query: HistoryQuery, home_space: dict, behavior, mirror, *,
           unavailable=(), now: float) -> Chosen | dict:
    """Di chi (la scelta di `search`, `select_subjects`) e quanto.

    Stati e valori guardano le entita'; le esecuzioni automazioni e script.

    **Il contratto col gestore** (revisione del Task 3, 30/09/2026): in OGNI
    profondita', corta compresa, `subjects` e' l'elenco INTERO dei soggetti
    da leggere a Home Assistant, e la pagina (`limite`, `salta`) si taglia
    dopo la lettura, sulle righe. `choose` decide la profondita' dal conto;
    non taglia nulla, salvo `limite` 0 (solo il conto: nessuno da leggere)."""
    f = query.who
    if query.kind == "esecuzioni":
        kinds = ((BEHAVIOR_DOMAINS[f.domain],) if f.domain
                 else ("automazione", "script"))
        f = replace(f, domain=None)
    else:
        kinds = ("entita",)
    selection = select_subjects(f, kinds, home_space, behavior, mirror,
                                unavailable=unavailable, now=now)
    names, since_when = mirror[1], mirror[4]
    if query.kind == "esecuzioni":
        subjects = [Subject(item["id"], item.get("nome") or item["id"],
                            values.get("last_triggered"))
                    for item, values in selection.behavior]
    else:
        subjects = [Subject(entry["id"],
                            names.get(entry["id"]) or entry.get("nome") or entry["id"],
                            since_when.get(entry["id"]))
                    for entry, _area, _where in selection.entities]
    if query.run_id is not None and len(subjects) != 1:
        return {"errore": f"esecuzione vale per UNA sola automazione, e questi filtri "
                          f"ne scelgono {len(subjects)}: restringi con riferimento"}
    return Chosen(len(subjects), selection.excluded, depth_for(len(subjects)),
                  subjects if f.limit > 0 else [])


def _frame(query: HistoryQuery, chosen: Chosen) -> dict:
    """La forma della porta, uguale per ogni genere (spec §3): cio' che si e'
    trovato, cio' che si e' lasciato fuori con la stessa nota di `search`
    (3.71.1), e la finestra chiesta nel fuso della casa."""
    out: dict = {"trovate": chosen.found, "escluse": chosen.excluded,
                 "profondita": chosen.depth, "voci": []}
    note = excluded_note(chosen.found, chosen.excluded)
    if note:
        out["nota"] = note
    out["finestra"] = {"da": query.start.isoformat(), "a": query.end.isoformat()}
    return out


def empty_answer(query: HistoryQuery, chosen: Chosen) -> dict:
    """Nessuno da leggere: nessun soggetto, o `limite` 0. Senza soggetti e
    senza escluse la strada si indica: il nome si trova con `search`."""
    out = _frame(query, chosen)
    if chosen.found == 0 and not any(chosen.excluded.values()):
        out["suggerimento"] = _NOTHING_CHOSEN
    return out


def _name_subjects(out: dict, chosen: Chosen) -> None:
    """Di chi sono le righe: nella completa il soggetto, nella media la mappa
    `{id: nome}` -- il nome una volta sola, non su ogni riga."""
    if chosen.depth == "completa" and chosen.subjects:
        s = chosen.subjects[0]
        out["soggetto"] = {"id": s.ident, "nome": s.name}
    elif chosen.depth == "media":
        out["soggetti"] = {s.ident: s.name for s in chosen.subjects}


def _changes(entity_id: str, points: list[dict],
             start_ts: float) -> list[tuple[str, float, str | None]]:
    """I cambi VERI dentro la finestra, dal piu' vecchio: (istante, secondi,
    stato).

    Lo stato passa dal filtro di riservatezza PRIMA del confronto (spec §5):
    «Lavoro» -> «Palestra» di una persona sono due `not_home` e non sono un
    cambio. Il primo punto e' lo stato all'inizio della finestra: conta solo
    se e' dentro. Un punto uguale al precedente (un attributo cambiato) non
    e' un cambio di stato."""
    out = []
    previous = _NOTHING
    for point in points:
        epoch = _epoch(point.get("quando"))
        if epoch is None:
            continue
        # `redact_state` e non `privacy.redact_row`: queste righe non portano
        # le chiavi di stato che `redact_row` riconosce, e nella completa non
        # hanno nemmeno l'`id` da cui leggerebbe il dominio.
        value = redact_state(entity_id, point.get("valore"))
        changed = epoch > start_ts if previous is _NOTHING else value != previous
        if changed:
            out.append((point.get("quando"), epoch, value))
        previous = value
    return out


def _by_hand(entity_id: str, epoch: float, acts: list[dict] | None) -> dict:
    """«Per mano di HIRIS» (da `historian._match`, 24/08/2026): l'atto della
    cronaca su questa entita' piu' vicino al cambio, entro
    `MATCH_TOLERANCE_S`, detto `probabile`. Nessun atto: niente -- il cambio
    non e' di HIRIS, e chi l'abbia fatto la storia non lo sa."""
    best, best_gap = None, None
    for act in acts or []:
        if entity_id not in (act.get("entita") or []):
            continue
        gap = abs(float(act.get("quando_ts") or 0.0) - epoch)
        if gap <= MATCH_TOLERANCE_S and (best_gap is None or gap < best_gap):
            best, best_gap = act, gap
    if best is None:
        return {}
    return {"per_mano_di": "HIRIS", "abbinamento": "probabile",
            "atto": {"id": best.get("id"), "origine": best.get("origine"),
                     "servizio": best.get("servizio")}}


def _covered_since(idents: list[str], series: dict, start_ts: float) -> float:
    """Da quando i dati coprono DAVVERO tutti i soggetti letti (spec §3,
    `finestra` e' «il periodo davvero coperto dai dati»).

    `HAClient.history` taglia ogni entita' per conto suo e ne tiene la CODA:
    la serie di un'entita' tagliata comincia al suo primo punto tenuto, non
    all'inizio della finestra. Prima del piu' tardo di questi primi punti,
    almeno un soggetto ha cambi che mancano: e' da li' che la risposta e'
    intera. Sull'epoch, come ogni conto di tempo di questo modulo."""
    firsts = [_epoch(series[i][0].get("quando")) for i in idents if series.get(i)]
    return max([start_ts] + [epoch for epoch in firsts if epoch is not None])


def _declare_gaps(out: dict, idents: list[str], series: dict, *, truncated: bool,
                  query: HistoryQuery) -> None:
    """Cio' che la risposta non copre: i soggetti MOSTRATI senza registrazioni
    (nella corta solo la pagina -- 250 identificatori fuori pagina
    sfonderebbero la soglia del ponte), e la finestra tagliata da Home
    Assistant, con `da` spostato dove i dati cominciano davvero e la domanda
    in `chiesta_da`."""
    missing = [i for i in idents if not series.get(i)]
    if missing:
        out["nessuna_registrazione"] = {"soggetti": missing, "perche": _NO_RECORDING}
    if truncated:
        start_ts = query.start.timestamp()
        covered = _covered_since(idents, series, start_ts)
        out["finestra"]["chiesta_da"] = out["finestra"]["da"]
        out["finestra"]["da"] = _local(covered, query.start.tzinfo)
        out["finestra"]["troncata"] = _TRUNCATED


def _oltre(beyond: dict) -> dict:
    """`oltre` della storia: quello di `page_rows`, e il consiglio di
    restringere solo quando restano righe davvero (non oltre la fine)."""
    return {**beyond, "consiglio": _NARROW} if beyond.get("restano") else beyond


def _activity(row: dict, epoch: float | None) -> tuple:
    """L'ordine della corta: chi e' cambiato piu' di recente NELLA finestra
    prima, chi non e' cambiato mai in fondo, e a parita' l'id -- un ordine
    che non dipende dallo specchio ne' dall'ordine della casa, cosi' `salta`
    su una finestra fissa non salta ne' ripete nessuno."""
    return (epoch is None, -(epoch or 0.0), row["id"])


def state_rows(query: HistoryQuery, chosen: Chosen, series: dict[str, list[dict]], *,
               truncated: bool, acts: list[dict] | None,
               current: dict[str, str]) -> dict:
    """Gli stati (spec §3): completa -- ogni cambio, con «per mano di»;
    media -- ogni cambio con l'id, una riga per evento; corta -- una riga per
    soggetto (quanti cambi, l'ultimo, lo stato adesso), dal piu' attivo nella
    finestra. Ogni profondita' si ferma a `ROWS_MAX` righe, tagliate DOPO la
    lettura di tutti i soggetti (vedi `Chosen`)."""
    zone = query.start.tzinfo
    start_ts = query.start.timestamp()
    out = _frame(query, chosen)
    changes = {s.ident: _changes(s.ident, series.get(s.ident) or [], start_ts)
               for s in chosen.subjects}
    shown = [s.ident for s in chosen.subjects]
    if chosen.depth == "corta":
        ranked = []
        for s in chosen.subjects:
            mine = changes[s.ident]
            row = {"id": s.ident, "nome": s.name, "cambi": len(mine),
                   "ultimo_cambio": _local(mine[-1][0], zone) if mine else None,
                   "stato": redact_state(s.ident, current.get(s.ident))}
            ranked.append((_activity(row, mine[-1][1] if mine else None), row))
        ranked.sort(key=lambda item: item[0])
        out["voci"], beyond = _page([row for _key, row in ranked], query.who)
        shown = [row["id"] for row in out["voci"]]
    else:
        events = []
        for s in chosen.subjects:
            for when, epoch, value in changes[s.ident]:
                row = {"quando": _local(when, zone), "stato": value}
                if chosen.depth == "media":
                    row = {"id": s.ident, **row}
                row.update(_by_hand(s.ident, epoch, acts))
                events.append((epoch, row))
        events.sort(key=lambda event: event[0], reverse=True)
        out["voci"], beyond = _page([row for _when, row in events], query.who)
        _name_subjects(out, chosen)
        if "soggetto" in out:
            ident = out["soggetto"]["id"]
            out["soggetto"]["stato"] = redact_state(ident, current.get(ident))
        if acts is None:
            out["cronaca_non_letta"] = _JOURNAL_UNREAD
    if beyond:
        out["oltre"] = _oltre(beyond)
    _declare_gaps(out, shown, series, truncated=truncated, query=query)
    return out
