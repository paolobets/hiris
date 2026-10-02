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

from ..mind.report import integration_of
from ..proxy.entity_cache import VALUES
from . import ha_vocabulary
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
from .privacy import MOVING_DOMAINS, redact_nested, redact_state
from .queries import ROWS_MAX

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
    #
    # «Adesso» e' `now_local`, non `now` (Task 7, 30/09/2026): un `datetime`
    # tiene i microsecondi e `time.time()` ne ha di piu', quindi
    # `fromtimestamp` arrotonda e la finestra senza `a` -- che FINISCE
    # adesso -- risultava «nel futuro» di mezzo microsecondo a una chiamata
    # su due. Le prove pure passavano un `now` intero e non lo vedevano.
    if end.timestamp() > now_local.timestamp():
        return "a e' nel futuro: `history` arriva al piu' ad adesso"
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
#: l'effetto (scelto il 24/08/2026): Home Assistant
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
    """Un soggetto della storia: l'identificatore, il nome, e -- solo per
    automazioni e script -- l'ultima esecuzione secondo lo specchio. NON
    ordina la corta degli stati: l'ordine lo da' la finestra letta (revisione
    del Task 3, 30/09/2026 -- vedi `Chosen`)."""
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
    names = mirror[1]
    if query.kind == "esecuzioni":
        subjects = [Subject(item["id"], item.get("nome") or item["id"],
                            values.get("last_triggered"))
                    for item, values in selection.behavior]
    else:
        subjects = [Subject(entry["id"],
                            names.get(entry["id"]) or entry.get("nome") or entry["id"])
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
    """«Per mano di HIRIS»: l'atto della
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
    in `chiesta_da`.

    SOLO il taglio sposta la finestra di tutti (revisione del Task 4,
    30/09/2026): una serie nata dentro la finestra lo dice sulla SUA riga
    (`dal`, nei valori), e i suoi conti partono da li'. Spostare la finestra
    di tutte per una sola contraddiceva i conti delle altre, calcolati
    dall'inizio chiesto."""
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


def _activity(tie: str, epoch: float | None) -> tuple:
    """L'ordine della corta: chi e' cambiato piu' di recente NELLA finestra
    prima, chi non e' cambiato mai in fondo, e a parita' `tie` (l'id; per il
    registro, che non ha id, la fonte e il messaggio) -- un ordine che non
    dipende dallo specchio ne' dall'ordine della casa, cosi' `salta` su una
    finestra fissa non salta ne' ripete nessuno."""
    return (epoch is None, -(epoch or 0.0), tie)


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
            ranked.append((_activity(s.ident, mine[-1][1] if mine else None), row))
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


#: Entro un giorno i valori si leggono cambio per cambio; oltre, per le serie
#: che le hanno, a fasce orarie di Home Assistant (la soglia di `trend`,
#: 24/08/2026: una scelta dichiarata, non una misura). Inclusiva: «le
#: ultime ventiquattr'ore» e' una domanda su oggi.
DETAIL_MAX_HOURS = 24
#: Ogni blocco di conti lo porta (decisione 2): la media di una finestra non
#: e' una misura di Home Assistant.
COUNTED = "calcolati da HIRIS sulla finestra"
#: Le serie che hanno un consumato (spec §3): i contatori.
_COUNTERS = frozenset({"total", "total_increasing"})
#: La prima fascia oraria comincia all'ora piena: una serie a fasce che
#: parte entro un'ora dall'inizio chiesto non e' nata dopo.
_COVERAGE_SLACK_S = 3600
_UNREADABLE_BAND = ("Home Assistant ha mandato fasce orarie con un inizio che non si "
                    "legge come istante col fuso: non le leggo, per non leggerle male")
#: Revisione del Task 4 (30/09/2026): `HAClient.history` chiede
#: `minimal_response&no_attributes`, quindi nei punti `last_reset` non c'e'
#: e i cicli di un `total` non si vedono. Il consumato si prende allora dal
#: `cambio` delle fasce di Home Assistant, che i cicli li conta.
_CYCLES_UNSEEN = ("questo contatore riparte a ogni ciclo (ha last_reset) e i punti "
                  "dei cambi non dicono quando: il consumato non lo calcolo -- "
                  "chiedi una finestra di piu' di 24 ore, dove e' il cambio orario "
                  "di Home Assistant")


def value_surface(query: HistoryQuery, state_class: str | None) -> str:
    """`dettaglio` o `oraria`, e nient'altro puo' deciderlo.
    Oltre `DETAIL_MAX_HOURS` solo chi
    ha statistiche va a fasce (`ha_vocabulary.produces_statistics`: non
    `bool(state_class)`, o una banderuola `measurement_angle` riceverebbe un
    elenco vuoto -- «non e' mai cambiata»). Le ore sono quelle VERE,
    dall'epoch (`HistoryQuery.hours`).

    Il prezzo di `oraria` (revisione finale della fetta, 30/09/2026): le
    fasce sono solo le ore gia' compilate da Home Assistant, e l'ora in corso
    manca in fondo. Non si rimedia qui: la riga lo dichiara con `al`
    (`_bands_until`)."""
    if query.hours <= DETAIL_MAX_HOURS:
        return "dettaglio"
    return "oraria" if ha_vocabulary.produces_statistics(state_class) else "dettaglio"


def _number(raw) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _round(value: float) -> float:
    return round(value, 3)


def _time_mean(timeline: list[tuple[float, float | None]],
               end_ts: float) -> tuple[float, float]:
    """(media pesata sul tempo, secondi senza valore). Ogni punto vale fino al
    punto SUCCESSIVO, di qualunque stato, l'ultimo fino alla fine della
    finestra. Una media dei punti conterebbe dieci volte un sensore che cambia
    dieci volte in un'ora (decisione del piano, 30/09/2026).

    Il tempo di un punto non numerico (`unavailable`, `unknown`) esce dal
    peso e si conta a parte (revisione del Task 4, 30/09/2026): nella prima
    forma valeva per il numero di prima, e [10, unavailable per 20 ore, 20]
    dava 10,8 invece di 15 -- venti ore di un 10 mai misurato.

    Tutto in secondi dall'epoch: il giorno del cambio d'ora ha 25 ore vere, e
    l'ora del muro ne conterebbe 24 (la lezione del Task 2)."""
    total = weight = blank = 0.0
    for index, (since, value) in enumerate(timeline):
        until = timeline[index + 1][0] if index + 1 < len(timeline) else end_ts
        span = max(0.0, until - since)
        if value is None:
            blank += span
            continue
        total += value * span
        weight += span
    if weight == 0:
        numbers = [value for _when, value in timeline if value is not None]
        return sum(numbers) / len(numbers), blank
    return total / weight, blank


def _consumed(values: list[float], state_class: str) -> float:
    """Il consumato come lo conta Home Assistant nelle sue statistiche
    (`homeassistant/components/sensor/recorder.py`, tag `2026.9.0`, letto il
    30/09/2026 -- la prima forma di questa funzione diceva di farlo, e non lo
    faceva):

    - `total` senza `last_reset`: la somma parte dal primo stato e non si
      azzera mai (righe 771-777 e 818) -- ultimo meno primo;
    - `total_increasing`: `reset_detected` (righe 475-493) dice azzeramento
      SOLO se il nuovo valore e' sotto il 90% del precedente. Un calo fra il
      90% e il 100% non e' un azzeramento: entra nella somma col suo segno
      (486-488 avvisano soltanto, 818 somma). Un valore NEGATIVO solleva
      `HomeAssistantError` e il ciclo lo salta (`continue`, 795-796): non
      si trasforma in zero. A un azzeramento si chiude il ciclo
      (`_sum += new_state - old_state`, 801) e il nuovo riparte da 0 (807).

    Cosi' «energia consumata oggi» chiesta da ieri somma i due giorni (Review
    Focus 2), e un contatore che trema non diventa un milione di azzeramenti:
    [100, 101, 100,5, 102] e' 2, non 103."""
    if state_class == "total":
        return values[-1] - values[0]
    used = 0.0
    cycle_start = previous = None
    for value in values:
        if value < 0:
            continue
        if previous is None:
            cycle_start = previous = value
            continue
        if value < 0.9 * previous:
            used += previous - cycle_start
            cycle_start = 0.0
        previous = value
    return used if previous is None else used + previous - cycle_start


def _detail_counts(points: list[dict], state_class, start_ts: float,
                   end_ts: float, *, cycles_unseen: bool) -> dict | None:
    """I conti di una serie di cambi veri, sulla serie INTERA (ruling P3,
    30/09/2026: il campione della completa puo' saltare il picco). Il tempo
    senza un numero si dichiara in `ore_senza_valore`; una serie nata dopo
    l'inizio conta dal suo primo punto (`dal` sulla riga)."""
    timeline = []
    for point in points:
        epoch = _epoch(point.get("quando"))
        if epoch is not None:
            timeline.append((max(epoch, start_ts), _number(point.get("valore"))))
    values = [value for _when, value in timeline if value is not None]
    if not values:
        return None
    mean, blank = _time_mean(timeline, end_ts)
    counts = {"primo": values[0], "ultimo": values[-1], "minimo": min(values),
              "massimo": max(values), "media": _round(mean)}
    if blank > 0:
        counts["ore_senza_valore"] = _round(blank / 3600)
    if state_class in _COUNTERS:
        if cycles_unseen:
            counts["consumato_non_calcolato"] = _CYCLES_UNSEEN
        else:
            counts["consumato"] = _round(_consumed(values, state_class))
    return counts


def _band_counts(bands: list[dict], state_class) -> dict | None:
    """I conti dalle fasce. Un contatore ha `stato` (a fine ora) e `cambio`
    (gia' corretto per gli azzeramenti, misurato il 27/08/2026) e NESSUNA
    media: la media delle letture di fine ora di un contatore non dice niente
    (revisione del Task 4, 30/09/2026). Una misura ha `media`, `minimo`,
    `massimo` di ogni ora -- ore di peso uguale."""
    if state_class in _COUNTERS:
        states = [x for x in (_number(b.get("stato")) for b in bands) if x is not None]
        if not states:
            return None
        counts = {"primo": states[0], "ultimo": states[-1], "minimo": min(states),
                  "massimo": max(states)}
        changes = [x for x in (_number(b.get("cambio")) for b in bands) if x is not None]
        if changes:
            counts["consumato"] = _round(sum(changes))
        return counts
    means = [x for x in (_number(b.get("media")) for b in bands) if x is not None]
    if not means:
        return None
    lows = [x for x in (_number(b.get("minimo")) for b in bands) if x is not None]
    highs = [x for x in (_number(b.get("massimo")) for b in bands) if x is not None]
    return {"primo": means[0], "ultimo": means[-1], "minimo": min(lows or means),
            "massimo": max(highs or means), "media": _round(sum(means) / len(means))}


def _band_activity(bands: list[dict]) -> float | None:
    """L'ultima ora in cui la serie si e' mossa (per `_activity`): un `cambio`
    non nullo, un minimo diverso dal massimo, o una media o uno stato diversi
    da quelli dell'ora prima. Un'ora ferma non e' attivita'."""
    last, previous = None, _NOTHING
    for band in bands:
        level = (_number(band.get("media")), _number(band.get("stato")))
        low, high = _number(band.get("minimo")), _number(band.get("massimo"))
        moved = (bool(_number(band.get("cambio")))
                 or (low is not None and high is not None and low != high)
                 or (previous is not _NOTHING and level != previous))
        if moved:
            last = _epoch(band.get("inizio"))
        previous = level
    return last


def _sample(points: list[dict], count: int) -> list[dict]:
    """Un campione distribuito nel tempo, primo e ultimo sempre compresi.
    Non una media: perdere punti si dichiara,
    inventarne uno mai esistito no."""
    if len(points) <= count:
        return list(points)
    if count <= 1:
        return [points[-1]]
    step = (len(points) - 1) / (count - 1)
    picked = [points[round(i * step)] for i in range(count)]
    picked[-1] = points[-1]
    return picked


def _in_zone(point: dict, keys: tuple[str, ...], zone) -> dict:
    return {**point, **{key: _local(point.get(key), zone) for key in keys if key in point}}


def _bands_until(bands: list[dict], end_ts: float) -> float | None:
    """La fine dell'ultima fascia, se cade PRIMA della fine chiesta, o
    `None`. Lo specchio di `_born_since` sulla coda (revisione finale della
    fetta, 30/09/2026): Home Assistant legge le fasce orarie solo dalla
    tabella `Statistics`, cioe' le ore gia' COMPILATE
    (`recorder/statistics.py`, tag 2026.9.0: `table = Statistics if period
    != "5minute" else StatisticsShortTerm`). L'ora in corso non c'e' mai: da
    0 a oltre 60 minuti mancano in fondo alla finestra, e `finestra.a` dice
    «adesso». La riga lo dice con `al`.

    Una fascia senza `fine` leggibile vale un'ora dal suo inizio: e' la
    fascia di `period="hour"`, per definizione."""
    ends = []
    for band in bands:
        until = _epoch(band.get("fine"))
        if until is None:
            since = _epoch(band.get("inizio"))
            until = None if since is None else since + 3600
        if until is not None:
            ends.append(until)
    if ends and max(ends) < end_ts:
        return max(ends)
    return None


def _born_since(points: list[dict], key: str, start_ts: float,
                slack: float) -> float | None:
    """Il primo istante di una serie che comincia DOPO l'inizio chiesto (oltre
    lo scarto), o `None`. Lo storico di Home Assistant apre ogni serie con lo
    stato all'inizio della finestra: se il primo punto viene dopo, prima non
    c'era registrazione (nata dopo, o gia' cancellata) -- o Home Assistant ha
    tagliato la testa, e allora lo dice anche `finestra`."""
    firsts = [epoch for epoch in (_epoch(p.get(key)) for p in points) if epoch is not None]
    if firsts and min(firsts) > start_ts + slack:
        return min(firsts)
    return None


#: Lo stato d'inizio dello storico porta l'istante chiesto: un secondo di
#: scarto copre l'arrotondamento dell'ISO, non una serie nata dopo.
_DETAIL_SLACK_S = 1


def _value_row(s: Subject, query: HistoryQuery, depth: str, *, surface: str,
               detail: list[dict], bands: list[dict], unit: str | None,
               state_class, cycles_unseen: bool) -> tuple[dict, list[dict], float | None]:
    """(riga, punti letti, ultima attivita' nella finestra) di UNA serie. I
    punti vuoti dicono «nessuna registrazione»; una riga con `errore` ha
    punti ma illeggibili. Una serie nata dentro la finestra porta `dal` e i
    suoi conti partono da li' (revisione del Task 4, 30/09/2026). Una serie
    a fasce che finisce prima della fine chiesta porta `al` -- l'ora in corso
    Home Assistant non l'ha ancora compilata (`_bands_until`), e i conti si
    fermano li'."""
    zone = query.start.tzinfo
    start_ts, end_ts = query.start.timestamp(), query.end.timestamp()
    row: dict = {"id": s.ident, "nome": s.name}
    if unit:
        row["unita"] = unit
    until = None
    if surface == "oraria":
        points = bands
        if any(_epoch(p.get("inizio")) is None for p in points):
            return {**row, "errore": _UNREADABLE_BAND}, points, None
        born = _born_since(points, "inizio", start_ts, _COVERAGE_SLACK_S)
        until = _bands_until(points, end_ts)
        counts = _band_counts(points, state_class)
        activity = _band_activity(points)
        keys: tuple[str, ...] = ("inizio", "fine")
    else:
        # Il valore passa da `redact_state` PRIMA di ogni conto e di ogni
        # punto: la serie di una persona e' fatta di zone (spec §5).
        points = [{**p, "valore": redact_state(s.ident, p.get("valore"))} for p in detail]
        born = _born_since(points, "quando", start_ts, _DETAIL_SLACK_S)
        counts = _detail_counts(points, state_class, start_ts, end_ts,
                                cycles_unseen=cycles_unseen)
        mine = _changes(s.ident, detail, start_ts)
        activity = mine[-1][1] if mine else None
        keys = ("quando",)
    if born is not None:
        row["dal"] = _local(born, zone)
    if until is not None:
        row["al"] = _local(until, zone)
    if counts:
        row.update(counts)
        row["conti"] = COUNTED
    if depth == "completa" and points:
        sample = _sample(points, ROWS_MAX)
        row["punti"] = [_in_zone(p, keys, zone) for p in sample]
        if len(sample) < len(points):
            row["campione"] = (f"{len(points)} punti nella finestra, ne do "
                               f"{len(sample)} distribuiti nel tempo: il primo e "
                               "l'ultimo ci sono sempre; i conti sono della serie intera")
    return row, points, activity


def value_rows(query: HistoryQuery, chosen: Chosen, *, detail: dict[str, list[dict]],
               bands: dict[str, list[dict]], truncated: bool, surfaces: dict[str, str],
               units: dict[str, str], state_classes: dict[str, str | None],
               attributes: dict[str, dict]) -> dict:
    """I valori (spec §3): per ogni serie i conti di HIRIS, dichiarati
    (decisione 2, solo per i numeri); nella completa anche la serie, al piu'
    `ROWS_MAX` punti distribuiti nel tempo, coi conti della serie INTERA
    (ruling P3). La media e la corta hanno la stessa riga: una riga per serie.

    Il contratto degli stati (revisione del Task 3, 30/09/2026): si leggono
    TUTTE le serie, si ordinano per cio' che e' successo nella finestra
    (`_activity`), e solo poi si impagina (`_page`); chi non ha
    registrazioni sta in fondo e si nomina nella SUA pagina, non in `voci`.
    `finestra` si sposta solo per il taglio di Home Assistant
    (`_declare_gaps`); una serie nata dopo lo dice con `dal`.

    `attributes` sono gli attributi ADESSO di ogni entita', nelle ceste dello
    specchio (`mirror[5]`): servono a sapere se un `total` ha `last_reset`,
    che i punti dello storico non portano (revisione del Task 4)."""
    out = _frame(query, chosen)
    ranked = []
    firsts: dict[str, list[dict]] = {}
    for s in chosen.subjects:
        surface = surfaces[s.ident]
        state_class = state_classes.get(s.ident)
        declared = (attributes.get(s.ident) or {}).get(VALUES) or {}
        row, points, activity = _value_row(
            s, query, chosen.depth, surface=surface, detail=detail.get(s.ident) or [],
            bands=bands.get(s.ident) or [], unit=units.get(s.ident),
            state_class=state_class,
            cycles_unseen=state_class == "total" and bool(declared.get("last_reset")))
        if points:
            # Il primo istante di ogni serie, nella forma che `_covered_since`
            # legge: le fasce lo hanno in `inizio`, i cambi in `quando`.
            key = "inizio" if surface == "oraria" else "quando"
            firsts[s.ident] = [{"quando": points[0].get(key)}]
        ranked.append((_activity(s.ident, activity), surface, row))
    ranked.sort(key=lambda item: item[0])
    page, beyond = _page([(surface, row) for _key, surface, row in ranked], query.who)
    shown = [row["id"] for _surface, row in page]
    out["voci"] = [row for _surface, row in page if row["id"] in firsts]
    grains = {surface for surface, row in page if row["id"] in firsts}
    if len(grains) > 1:
        for surface, row in page:
            row["grana"] = surface
        out["grana"] = "per serie"
    elif grains:
        out["grana"] = grains.pop()
    if beyond:
        out["oltre"] = _oltre(beyond)
    _declare_gaps(out, shown, firsts, truncated=truncated, query=query)
    return out


#: Le esecuzioni per automazione nella profondita' media (spec §3).
RECENT_RUNS = 3
#: Quanto di un messaggio del registro arriva al modello: la frase che dice
#: cosa e' successo, non il paragrafo (spec §3, «messaggio accorciato»).
MESSAGE_MAX = 300
UNRESOLVED_RUNS = ("non trovo la chiave con cui Home Assistant ne conserva le "
                   "esecuzioni (l'id della configurazione): puo' essere scritta in YAML "
                   "senza «id:», o non la conosco ancora. Non vuol dire che non sia "
                   "mai partita: vuol dire che non ho potuto guardare")
#: Home Assistant conserva le ULTIME esecuzioni di ognuna (`stored_traces`,
#: 5 se non si cambia) e ne scarta le piu' vecchie: se la piu' vecchia
#: conservata e' dentro la finestra, prima di lei non si sa.
_RUNS_KEPT = ("Home Assistant conserva solo le ultime esecuzioni di ognuna: `dal` dice "
              "da quando cominciano quelle conservate, e prima, nella finestra, possono "
              "essercene state altre -- una traccia che manca non vuol dire andata bene")


def _run_row(trace: dict, zone) -> dict:
    row = {"esecuzione": trace.get("run_id"),
           "inizio": _local((trace.get("timestamp") or {}).get("start"), zone),
           "esito": trace.get("script_execution"),
           "ultimo_passo": trace.get("last_step")}
    if trace.get("error"):
        # `guasto` e non `errore`: `errore` e' la chiave con cui lo strumento
        # dice che non ha potuto rispondere, e dentro una riga confonderebbe.
        row["guasto"] = trace["error"]
    return row


def _runs_in_window(traces: list, start_ts: float,
                    end_ts: float) -> tuple[list[tuple[float, dict]], float | None]:
    """(esecuzioni nella finestra dalla piu' recente, `dal` o `None`).

    `dal` e' l'inizio della piu' vecchia esecuzione CONSERVATA, se cade dentro
    la finestra: Home Assistant tiene le ultime, quindi se ne conserva una di
    prima della finestra tutte quelle della finestra ci sono; se no, prima
    della piu' vecchia non si sa (la regola di `dal` dei valori, Task 4:
    detto sulla riga di chi, la finestra di tutti non si sposta)."""
    kept, oldest = [], None
    for trace in traces or []:
        if not isinstance(trace, dict):
            continue
        began = _epoch((trace.get("timestamp") or {}).get("start"))
        if began is None:
            continue
        oldest = began if oldest is None else min(oldest, began)
        if start_ts <= began <= end_ts:
            kept.append((began, trace))
    kept.sort(key=lambda run: run[0], reverse=True)
    return kept, (oldest if oldest is not None and oldest > start_ts else None)


def run_rows(query: HistoryQuery, chosen: Chosen, *, traces: dict[str, list],
             keys: dict[str, str | None], unread: dict[str, str]) -> dict:
    """Le esecuzioni (spec §3): completa -- le esecuzioni conservate nella
    finestra; media -- le ultime `RECENT_RUNS` per automazione, raggruppate;
    corta -- una riga per automazione.

    Il contratto degli stati (revisione del Task 3, 30/09/2026): si leggono
    TUTTI i soggetti, si ordinano per l'ultima esecuzione NELLA finestra
    (`_activity`; chi non e' partita nella finestra in fondo, a parita' l'id),
    e solo poi si impagina (`_page`, `_oltre`).

    Chi non si e' potuto leggere si nomina in `non_letti`, col suo motivo, e
    non e' una riga: un elenco vuoto si leggerebbe «mai partita» (Review
    Focus 4). Nella corta, come `nessuna_registrazione` degli stati, solo
    quelli della pagina: 250 automazioni YAML senza `id:` sfonderebbero la
    soglia del ponte.

    `traces`: chiave -> righe di `trace/list`, gia' sigillate dal gestore;
    `keys`: soggetto -> la sua chiave (`None` se irrisolta); `unread`:
    chiave -> il motivo per cui Home Assistant non ha risposto.

    Revisione del Task 5 (30/09/2026):
    - `non_lette_in_tutto` esce su OGNI pagina: con i nomi solo sulla loro
      pagina, la prima si leggeva «lette tutte»;
    - `dal` della media vale solo per chi ha righe nella pagina;
    - `ultima_esecuzione` e' `last_triggered` dello specchio, `esito_ultima`
      e' della traccia conservata piu' recente: possono essere due
      esecuzioni diverse (la traccia puo' mancare, o lo specchio essere
      indietro). Quando distano piu' di `_SAME_RUN_S`, la riga dice di quando
      e' l'esito (`esito_ultima_del`)."""
    zone = query.start.tzinfo
    start_ts, end_ts = query.start.timestamp(), query.end.timestamp()
    out = _frame(query, chosen)
    not_read: dict[str, str] = {}
    runs: dict[str, list[tuple[float, dict]]] = {}
    since: dict[str, float] = {}
    for s in chosen.subjects:
        key = keys.get(s.ident)
        if key is None:
            not_read[s.ident] = UNRESOLVED_RUNS
        elif key in unread:
            not_read[s.ident] = unread[key]
        else:
            runs[s.ident], born = _runs_in_window(traces.get(key) or [], start_ts, end_ts)
            if born is not None:
                since[s.ident] = born
    unread_count = len(not_read)
    ranked = sorted(chosen.subjects, key=lambda s: _activity(
        s.ident, runs[s.ident][0][0] if runs.get(s.ident) else None))
    if chosen.depth == "corta":
        page, beyond = _page(ranked, query.who)
        rows = []
        for s in page:
            if s.ident not in runs:
                continue
            row = {"id": s.ident, "nome": s.name,
                   "partenze_conservate": len(runs[s.ident]),
                   "ultima_esecuzione": _local(s.last, zone) if s.last else "mai"}
            if runs[s.ident]:
                newest, trace = runs[s.ident][0]
                row["esito_ultima"] = trace.get("script_execution")
                mirror_last = _epoch(s.last)
                if mirror_last is None or abs(mirror_last - newest) > _SAME_RUN_S:
                    row["esito_ultima_del"] = _local(newest, zone)
            if s.ident in since:
                row["dal"] = _local(since[s.ident], zone)
            rows.append(row)
        out["voci"] = rows
        shown = {s.ident for s in page}
    else:
        per_subject = RECENT_RUNS if chosen.depth == "media" else None
        events = []
        for s in ranked:
            for _began, trace in runs.get(s.ident, [])[:per_subject]:
                row = _run_row(trace, zone)
                events.append((s.ident, {"id": s.ident, **row}
                               if chosen.depth == "media" else row))
        page, beyond = _page(events, query.who)
        out["voci"] = [row for _ident, row in page]
        shown = {ident for ident, _row in page}
        _name_subjects(out, chosen)
        if "soggetto" in out:
            s = chosen.subjects[0]
            out["soggetto"]["ultima_esecuzione"] = _local(s.last, zone) if s.last else "mai"
            if s.ident in since:
                out["soggetto"]["dal"] = _local(since[s.ident], zone)
        else:
            since = {ident: when for ident, when in since.items() if ident in shown}
            if since:
                out["dal"] = {ident: _local(when, zone) for ident, when in since.items()}
        # Nella media e nella completa i soggetti sono al piu' dieci: le non
        # lette si nominano tutte, qualunque sia la pagina delle righe.
        shown = {s.ident for s in chosen.subjects}
    if chosen.depth == "corta":
        since = {ident: when for ident, when in since.items() if ident in shown}
    not_read = {ident: why for ident, why in not_read.items() if ident in shown}
    if since:
        out["conservate"] = _RUNS_KEPT
    if beyond:
        out["oltre"] = _oltre(beyond)
    if unread_count:
        out["non_lette_in_tutto"] = unread_count
    if not_read:
        out["non_letti"] = not_read
    return out


#: Un `last_triggered` e l'inizio della sua traccia sono lo stesso istante a
#: meno di millisecondi: oltre due secondi sono due esecuzioni.
_SAME_RUN_S = 2
#: Una condizione `state` registra `{result, state, wanted_state}` SENZA
#: `entity_id` (`helpers/condition.py`, `state()`, tag `2026.9.0`, letto il
#: 30/09/2026): lo stato vivo di una persona sta li', e `redact_nested` non
#: lo riconosce. Di chi sia lo dice la configurazione, allo stesso percorso.
_CONDITION_STATE_KEYS = ("state", "wanted_state")


def _config_at(config, path: str):
    """Il nodo della configurazione a cui corrisponde il percorso di un
    elemento di traccia, o `None`.

    I percorsi li scrive Home Assistant (`trace_path`, tag `2026.9.0`):
    `condition/0/entity_id/1`, `condition/0/conditions/2/...` dentro un
    `and`/`or`, `action/3/if/condition/0/...`. Le differenze dalla
    configurazione sono tre, e si seguono qui:
    - la configurazione puo' dire `conditions` dove il percorso dice
      `condition` (le chiavi al plurale dalla 2024.10), o il contrario;
    - dentro un elenco il percorso puo' ripeterne il nome (`if/condition/0`
      per `if: [...]`): il nome si salta, la lista e' gia' lei;
    - una condizione sola, o un `entity_id` sola, si scrivono senza elenco:
      l'indice 0 e' lei."""
    node = config
    for step in path.split("/"):
        if isinstance(node, list):
            if step.isdigit():
                if int(step) >= len(node):
                    return None
                node = node[int(step)]
            continue
        if isinstance(node, dict):
            for key in (step, step + "s", step.removesuffix("s")):
                if key in node:
                    node = node[key]
                    break
            else:
                if step != "0":
                    return None
            continue
        if not (isinstance(node, str) and step == "0"):
            return None
    return node


def _entities_in(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return _entities_in(node.get("entity_id"))
    if isinstance(node, list):
        return [item for item in node if isinstance(item, str)]
    return []


def _moving_in(config) -> list[str]:
    """Le entita' che si spostano nominate OVUNQUE nella configurazione."""
    if isinstance(config, str):
        return [config] if config.split(".", 1)[0] in MOVING_DOMAINS else []
    items = config.values() if isinstance(config, dict) else (
        config if isinstance(config, list) else ())
    return [found for item in items for found in _moving_in(item)]


def _redact_condition_results(trace: dict) -> dict:
    """Lo stato vivo che le condizioni registrano senza `entity_id`, ridotto
    a in casa / fuori per chi si sposta (Review Task 5, I1, 30/09/2026).

    Di chi sia lo dice la configurazione allo stesso percorso (`_config_at`).
    Un percorso che non vi si ritrova non si lascia passare: se la
    configurazione nomina qualcuno che si sposta, lo stato si riduce come
    se fosse suo -- una zona scappata costa piu' di un «on» diventato
    `not_home`."""
    steps = trace.get("trace")
    if not isinstance(steps, dict):
        return trace
    config = trace.get("config")
    anyone_moving = _moving_in(config)
    cleaned = {}
    for path, elements in steps.items():
        owners = _entities_in(_config_at(config, str(path)))
        moving = ([e for e in owners if e.split(".", 1)[0] in MOVING_DOMAINS]
                  if owners else anyone_moving)
        if not moving or not isinstance(elements, list):
            cleaned[path] = elements
            continue
        cleaned[path] = [_reduced(element, moving[0]) for element in elements]
    return {**trace, "trace": cleaned}


def _reduced(element, entity_id: str):
    result = element.get("result") if isinstance(element, dict) else None
    if not isinstance(result, dict):
        return element
    result = dict(result)
    for key in _CONDITION_STATE_KEYS:
        if key in result:
            value = result[key]
            result[key] = ([redact_state(entity_id, item) for item in value]
                           if isinstance(value, list) else redact_state(entity_id, value))
    return {**element, "result": result}


def run_detail(query: HistoryQuery, chosen: Chosen, trace: dict) -> dict:
    """Una sola esecuzione passo per passo (`esecuzione` = il `run_id`): la
    traccia intera di `trace/get`, gia' sigillata dal gestore, senza le
    posizioni di chi si muove: `redact_nested` per gli stati annidati
    (l'innesco e le variabili dei passi portano `to_state` interi), e
    `_redact_condition_results` per lo stato che le condizioni registrano
    senza `entity_id`. La zona configurata in un innesco (`trigger.zone`)
    resta: e' configurazione, e questo genere e' dei soli amministratori."""
    out = _frame(query, chosen)
    _name_subjects(out, chosen)
    out["voci"] = [redact_nested(_redact_condition_results(trace))]
    return out


#: `integration_of` legge il logger: le librerie scrivono col loro nome
#: (`zigpy` per zha, `aiohttp`), e il filtro non le riconosce come
#: dell'integrazione. Nessuna tabella libreria -> integrazione esiste nel
#: codice: lo si dice, non si indovina (Review Task 5, M5).
_LIBRARIES_UNFILTERED = ("integrazione si legge dal nome di chi scrive nel registro: le "
                         "librerie che un'integrazione usa (es. zigpy per zha) scrivono "
                         "col loro nome e con questo filtro non ci sono -- per vederle, "
                         "togli integrazione")
#: Il registro di Home Assistant e' una coda limitata (`max_entries`, 50 se
#: non si cambia) che si svuota a ogni riavvio: prima della voce piu' vecchia
#: conservata non si sa (Review Task 5, I2).
_LOG_KEPT = ("Home Assistant tiene solo le ultime voci del registro, e lo svuota a ogni "
             "riavvio: la piu' vecchia conservata e' di `da`, prima non si sa")

def _last_message(raw) -> str | None:
    """Home Assistant tiene fino a cinque messaggi per voce (`LogEntry.message`
    e' una coda che cresce in fondo): l'ultimo e' il piu' recente."""
    if isinstance(raw, list | tuple):
        texts = [str(item) for item in raw if item not in (None, "")]
        return texts[-1] if texts else None
    return None if raw in (None, "") else str(raw)


def last_line(text) -> str | None:
    """L'ultima riga non vuota di un'eccezione: il «cosa» (tipo e messaggio),
    l'unica che `error_rows` porta. Pubblica perche' il gestore la prende
    PRIMA del sigillo dei segreti (revisione finale della fetta, M-3,
    30/09/2026): sigillare parola per parola tutta la traccia costava una
    quindicina di impronte a parola per righe che nessuno vede. Una regola
    sola, qui: il gestore la importa, non la copia."""
    lines =[line.strip() for line in str(text).splitlines() if line.strip()]
    return lines[-1] if lines else None


def _short(text: str | None) -> str | None:
    if text is None or len(text) <= MESSAGE_MAX:
        return text
    return text[:MESSAGE_MAX - 1] + "…"


def _source(raw) -> str | None:
    if isinstance(raw, list | tuple) and len(raw) == 2:
        return f"{raw[0]}:{raw[1]}"
    return None if raw is None else str(raw)


def error_rows(query: HistoryQuery, entries: list) -> dict:
    """Il registro di Home Assistant (spec §3): una forma sola, la corta, una
    riga per voce -- livello, messaggio accorciato, fonte, `count`, prima e
    ultima volta, e l'ultima riga dell'eccezione (il «cosa»). Filtrato per
    `livello`, `integrazione` e finestra; una voce senza istante leggibile
    non si scarta: non si sa se e' fuori.

    L'ordine e la pagina sono quelli delle altre corte: dall'ultima volta piu'
    recente (`_activity`, a parita' fonte e messaggio), poi `_page` e `_oltre`.

    `entries`: le voci di `system_log/list` con `message` ed `exception` GIA'
    passati dal sigillo dei segreti dal gestore (reperto B-1): qui non si
    sigilla niente, si accorcia.

    `finestra` e' quella coperta davvero: il registro e' una coda limitata,
    e se la voce piu' vecchia CONSERVATA -- di tutte, prima dei filtri -- e'
    dentro la finestra, `da` si sposta li' con `troncata` (la regola del
    taglio, Task 4; Review Task 5, I2). Una settimana chiesta a una casa
    chiacchierona diceva «nessun altro errore» a finestra intera.

    `integrazione` e' la stessa lettura del logger del primo piano
    (`mind.report.integration_of`), non una seconda."""
    zone = query.start.tzinfo
    start_ts, end_ts = query.start.timestamp(), query.end.timestamp()
    ranked = []
    retained = [epoch for epoch in (_epoch(entry.get("timestamp"))
                                    for entry in entries or [] if isinstance(entry, dict))
                if epoch is not None]
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        level = str(entry.get("level") or "").upper() or None
        if query.level and level != query.level:
            continue
        found = integration_of(str(entry.get("name") or ""))
        integration = found[1] if found else None
        if query.who.platform and integration != query.who.platform:
            continue
        last = _epoch(entry.get("timestamp"))
        if last is not None and not start_ts <= last <= end_ts:
            continue
        row = {"livello": level, "messaggio": _short(_last_message(entry.get("message"))),
               "fonte": _source(entry.get("source")), "integrazione": integration,
               "count": entry.get("count"),
               "prima": _local(entry.get("first_occurred"), zone),
               "ultima": _local(entry.get("timestamp"), zone)}
        if entry.get("exception"):
            row["eccezione"] = _short(last_line(entry["exception"]))
        ranked.append((_activity(f"{level}|{row['fonte']}|{row['messaggio']}", last),
                       row))
    ranked.sort(key=lambda item: item[0])
    page, beyond = _page([row for _key, row in ranked], query.who)
    out = {"trovate": len(ranked),
           "escluse": {"nascoste": 0, "servizio": 0, "disabilitate": 0},
           "profondita": "corta", "voci": page,
           "finestra": {"da": query.start.isoformat(), "a": query.end.isoformat()}}
    if retained and min(retained) > start_ts:
        out["finestra"]["chiesta_da"] = out["finestra"]["da"]
        out["finestra"]["da"] = _local(min(retained), zone)
        out["finestra"]["troncata"] = _LOG_KEPT
    if query.who.platform:
        out["nota_integrazione"] = _LIBRARIES_UNFILTERED
    if beyond:
        out["oltre"] = _oltre(beyond)
    return out
