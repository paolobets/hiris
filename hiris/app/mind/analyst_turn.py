"""Il turno dell'**analista** (spec §10): il modello sceglie, il codice calcola.

## La regola che regge tutto

**Il modello indica QUALE misura, e non scrive il numero.** Valore, copertura,
scostamento e base ce li attacca questo modulo, letti dalla serie. Cosi' un
numero inventato dentro un rapporto che sembra autorevole e' **impossibile** --
ed e' *«il codice calcola, il modello sceglie»* preso alla lettera invece che
come slogan.

Se il modello un numero lo scrive lo stesso, la risposta si **rifiuta**: non si
ignora in silenzio (nasconderebbe che ha letto male) e non si sostituisce col
nostro (sarebbe correggere invece di rifiutare). Stessa dottrina delle ricette.

## Cosa deve avere un'osservazione

**Cosa** ha visto, **su quale misura** (il numero) e **se e' spiegato**.
**Perche'** lo dice -- quale dei tre inneschi -- lo sa il codice, che li marca
sulla riga: il modello sceglie solo fra quelli, quando sono piu' d'uno.
**Cosa cambierebbe** rispetto all'obiettivo e' facoltativo dal Task 3.5 del
piano degli attori: obbligatorio, contraddiceva «il silenzio e' un esito
legittimo» -- spingeva a inventare un'azione per ogni constatazione (audit del
01/10/2026). Facoltativo anche **da riverificare**: cio' che l'analista vuole
ricontrollare, archiviato con l'osservazione.

## Il silenzio

*«Il silenzio e' un esito legittimo.»* Zero osservazioni non e' un errore e non
e' un giro sprecato: e' una risposta, e si archivia. Ma una risposta **vuota**
-- il modello che non ha risposto affatto -- non e' silenzio: e' un giro da
rifare, e non si scrive niente. E' il difetto gia' pagato dalle ricette il
13/09/2026, quando una decisione vuota veniva registrata come «non capito» di
un modello mai interpellato.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

from ..home_space.ha_vocabulary import is_entity_id
from ..steering import ANALYST_SPECIES, SPECIES, read_json, refused_lines
from . import analyst

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner.
ANALYSIS_TURN_KIND = SPECIES[ANALYST_SPECIES].kind

#: **Il tetto della risposta, dichiarato** (Tappa 6, Task 4; D3, approvata
#: il 05/10/2026). Fino a quel giorno questo mestiere non ne passava nessuno e
#: prendeva i 4.096 di fabbrica di `claude_runner.MAX_TOKENS`: lo stesso
#: numero, scelto da nessuno. Qui e' lo stesso valore SCRITTO -- il
#: comportamento non cambia, diventa visibile. **Non e' misurato**: 7 turni
#: dell'analista su 8 si fermano qui (`docs/misure/2026-10-tappa-0.md`), e il
#: valore giusto lo sceglie la misura dal vivo della chiusura della tappa
#: (T9: 8 turni con un tetto alto, la risposta piu' lunga piu' un margine),
#: scritto con la data.
MAX_ANSWER_TOKENS = 4096

#: I campi che il modello NON deve scrivere: sono i numeri, e li mette il
#: codice. Elencati qui perche' il rifiuto possa dire quale ha trovato.
NUMERIC_FIELDS = ("valore", "numero", "copertura", "quanti_scarti", "scarto",
                  "mediana", "base")


def fondamento(stamps) -> dict:
    """Il **`fondamento`** di un'analisi: su quali resoconti e' stata scritta.

    `{"giorni": n, "impronta": "..."}`. L'impronta compatta le coppie
    `(giorno, scritto_ts)`: cambia se un giorno compare, se sparisce, o se
    **e' stato riscritto** -- un recupero o un rifacimento dopo una correzione
    di giudizio.

    **Perche' esiste** (difetto trovato dal proprietario il 20/09/2026): il
    giro chiedeva «c'e' gia' un'analisi per oggi?», e un resoconto recuperato
    alle 15:00 non entrava in nessuna analisi, mai. E' la stessa meccanica
    dell'impronta dei giudizi sulla cronaca, un piano piu' su: si confronta il
    `fondamento`, non la data.

    **L'ordine non conta**: le coppie si ordinano prima di impastarle, o due
    letture dello stesso archivio darebbero due impronte.
    """
    pairs = sorted((str(day), float(when)) for day, when in (stamps or []))
    text = "|".join(f"{day}@{when!r}" for day, when in pairs)
    return {"giorni": len(pairs),
            "impronta": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]}


def apply_analysis(series: dict, answer: str, *, truncated: bool = False,
                   previous: list[dict] | None = None,
                   tool_calls: list[dict] | None = None,
                   presence=None) -> dict:
    """Cosa si fa della risposta: si valida, e si **arricchisce coi numeri**.

    `tool_calls` sono le letture fatte nel turno, dal registro delle chiamate
    del runner (`last_tool_calls`: `{tool, input}`), mai dal testo del modello
    (Task 3.5, Passo 3). Stanno nell'analisi una volta sola, in `letture`:
    il turno non dice quale lettura e' servita a quale osservazione, e
    ripeterle su ognuna sarebbe una copia. Dal Task 3.6 (D5) arrivano sulla
    catena da `steering.TurnOutcome.tool_calls`, sul ponte dalla decisione
    del turno, con lo stesso nome nudo (`server._collect_analyst_turn`).

    `presence` (`privacy.PresenceMask`) riporta all'id vero un segnaposto che
    il modello ha letto negli strumenti e scritto in un `rimetti`.

    `previous` e' la memoria (`analyst.previous_observations`, D4): il codice
    attacca a ogni osservazione se e' nuova (`analyst.novelty`), e quella gia'
    detta con la stessa prova **si toglie**, si dice nel registro e torna in
    `ripetute` (le impronte). Non si rifiuta l'analisi per lei: non e' un
    errore di lettura del modello, e' un doppione che il codice riconosce.

    Torna `{"analisi": dict | None, "problemi": [...], "risposta": bool}`.

    `analisi` e' `None` quando c'e' anche un solo problema: si rifiuta, non si
    corregge, e **tutti i problemi si dicono insieme** -- dirne uno per giro
    costringerebbe a rieseguire la notte per scoprirne un altro.
    """
    # Il JSON lo cava il lettore unico (`steering.read_json`, D-11): o esce
    # un dizionario, o esce il perche' no -- e un turno troncato non si legge
    # (D2).
    data, reason = read_json(answer, shape=dict,
                             what="un oggetto con le osservazioni",
                             truncated=truncated)
    if data is None:
        answered = bool(str(answer or "").strip())
        if not answered:
            logger.warning(
                "analista: nessuna risposta -- non si scrive niente, si "
                "richiede al giro dopo (una risposta che non c'e' non e' un "
                "silenzio)")
        return {"analisi": None, "problemi": [reason], "risposta": answered}

    seen = data.get("osservazioni")
    if not isinstance(seen, list):
        return {"analisi": None, "risposta": True,
                "problemi": [("la risposta non porta un elenco "
                              "`osservazioni`: un elenco vuoto e' silenzio, e "
                              "va bene; l'assenza dell'elenco e' un'altra cosa")]}

    # L'elenco IN ORDINE: il numero che il modello indica e' la posizione qui,
    # ed e' lo stesso ordine con cui `build_question` lo ha consegnato.
    known = list(series.get("serie") or [])
    days = list(series.get("giorni") or [])
    problems: list[str] = []
    enriched: list[dict] = []
    repeated: list[str] = []
    for number, line in enumerate(seen, start=1):
        if not isinstance(line, dict):
            problems.append(f"l'osservazione {number} non e' un'osservazione: {line!r}")
            continue
        built = _enrich(line, number, known, problems, days)
        if built is not None:
            fresh = analyst.novelty(built, previous or [])
            if fresh is None:
                repeated.append(analyst.observation_key(built))
                continue
            enriched.append({**built, "novita": fresh})

    asked_back = data.get("rimetti")
    if presence is not None:
        asked_back = presence.unmask(asked_back)
    back_in = _back_in(asked_back, problems)
    if problems:
        return {"analisi": None, "problemi": problems, "risposta": True,
                "ripetute": repeated}
    if repeated:
        logger.info("analista: %d osservazioni gia' dette con la stessa prova, "
                    "tolte: %s", len(repeated), " \u00b7 ".join(repeated))
    analysis = {"osservazioni": enriched}
    if back_in:
        analysis["rimetti"] = back_in
    if tool_calls:
        analysis["letture"] = [{"tool": c.get("tool"), "input": c.get("input")}
                               for c in tool_calls if isinstance(c, dict)]
    return {"analisi": analysis, "problemi": [], "risposta": True,
            "ripetute": repeated}


def _enrich(line: dict, number: int, known: dict, problems: list,
            days: list[str]) -> dict | None:
    """Un'osservazione validata e completata coi numeri della serie."""
    written = [f for f in NUMERIC_FIELDS if f in line]
    if written:
        problems.append(
            f"l'osservazione {number} scrive un numero ({', '.join(written)}): "
            "i numeri li mette il codice, dalla serie. Indica la misura e di' "
            "perche'")

    # **Il NUMERO, non il nome** (difetto misurato il 22/09/2026, sei giorni di
    # silenzio). Ogni riga arriva al modello con due identificatori -- l'impronta
    # del soggetto e il nome umano -- e chiedergli l'impronta significava
    # chiedergli quello che a un modello linguistico somiglia meno a un
    # identificatore: rispondeva «Presa Smart», «Alexa», «Corridoio T», e la
    # risposta veniva rifiutata per intero. Cinque osservazioni su cinque.
    #
    # Il numero toglie l'ambiguita' alla fonte, ed e' la stessa scelta gia'
    # fatta un giorno prima nel turno dell'attuatore: «ricopiarne il testo
    # vorrebbe dire poterlo sbagliare».
    which = line.get("quale")
    row = None
    if not isinstance(which, int) or isinstance(which, bool):
        problems.append(
            f"l'osservazione {number} non porta `quale`, il numero della misura "
            f"nell'elenco consegnato (ha {which!r}): il numero e' l'unica "
            "chiave, un nome non basta")
    elif not 0 <= which < len(known):
        problems.append(
            f"l'osservazione {number} indica la misura {which}, che non e' "
            f"nell'elenco (ce ne sono {len(known)}, da 0 a {len(known) - 1})")
    else:
        row = known[which]

    if not str(line.get("cosa") or "").strip():
        problems.append(f"l'osservazione {number} non dice COSA ha visto")

    if row is None:
        return None
    trigger = _trigger(line.get("innesco"), row, which, number, problems, days)
    if trigger is None:
        return None
    deviation = row.get("scostamento") or {}
    values = row.get("valori") or []
    coverages = row.get("coperture") or []
    return {"soggetto": row.get("soggetto"), "nome": row.get("nome"),
            "misura": row.get("misura"), "chiave": row.get("chiave"),
            "unita": row.get("unita"),
            "innesco": trigger, "cosa": str(line.get("cosa") or "").strip(),
            "spiegato": line.get("spiegato"),
            "cosa_cambierebbe": _text(line.get("cosa_cambierebbe")),
            "da_riverificare": _text(line.get("da_riverificare")),
            "valore": values[-1] if values else None,
            "copertura": coverages[-1] if coverages else None,
            "quanti_scarti": deviation.get("quanti_scarti"),
            "mediana": deviation.get("mediana"),
            "base": deviation.get("base")}


def _trigger(written, row: dict, which: int, number: int, problems: list,
             days: list[str]) -> int | None:
    """L'innesco dell'osservazione, **dai fatti che il codice ha marcato**
    sulla riga (D3, Task 3.5; `analyst.trigger_facts`).

    Una riga con un innesco solo lo prende senza che il modello lo scriva.
    Con piu' inneschi il modello sceglie, e sceglie FRA quelli della riga:
    un innesco che la riga non ha si rifiuta -- prima era il modello a
    dichiararlo, e una scelta sbagliata era indistinguibile da una giusta.
    Una riga senza fatti non e' candidata a niente.
    """
    marked = sorted({fact["innesco"] for fact in analyst.trigger_facts(row, days)})
    # Solo un `int` vero (G21-1 del revisore, giro 21): in Python `True == 1`
    # e `1.0 == 1`, e un innesco scritto cosi' passava il confronto, finiva
    # nell'impronta con un'altra forma e la ripetizione non si toglieva piu'.
    if written is not None and (type(written) is not int or written not in marked):
        problems.append(
            f"l'osservazione {number} dice innesco «{written}», ma la misura "
            f"[{which}] e' candidata a {marked or 'nessun innesco'}: gli "
            "inneschi li marca il codice, e si sceglie fra quelli")
        return None
    if written is not None:
        return written
    if len(marked) == 1:
        return marked[0]
    if not marked:
        problems.append(
            f"l'osservazione {number} parla della misura [{which}], che non ha "
            "nessun fatto d'innesco: non e' candidata a un'osservazione")
    else:
        problems.append(
            f"l'osservazione {number} non dice l'innesco, e la misura [{which}] "
            f"e' candidata a piu' di uno ({marked}): scegline uno")
    return None


def _text(value) -> str | None:
    """Un campo di testo facoltativo: la frase, o `None` se non c'e'."""
    clean = str(value or "").strip()
    return clean or None


def _back_in(asked, problems: list) -> list[dict]:
    """Il **rimetti dentro** (D9): le entita' che l'analista chiede di far
    rientrare nello scope, `[{id, perche}]`. Si valida la forma -- anche
    quella dell'`id`, che deve essere un `entity_id` (G21-2 del revisore:
    «camera da letto» passava); lo scrive il
    Task 3.7, con autore `ANALYST`, e `scope.may_overwrite` lascia fuori cio'
    che il proprietario ha tolto."""
    if asked is None:
        return []
    if not isinstance(asked, list):
        problems.append("`rimetti` vuole un elenco di {id, perche}")
        return []
    out = []
    for number, item in enumerate(asked, start=1):
        ident = str((item or {}).get("id") or "").strip() if isinstance(item, dict) else ""
        why = _text(item.get("perche")) if isinstance(item, dict) else None
        if not is_entity_id(ident) or why is None:
            problems.append(f"il rimetti {number} vuole `id` e `perche`: {item!r}")
            continue
        out.append({"id": ident, "perche": why})
    return out

SYSTEM = """Sei l'analista di HIRIS, un sistema che guarda una casa domotica.

Il tuo mestiere qui e' UNO: leggere le misure di molti giorni e dire **cosa si
potrebbe fare**. Non osservi e non cataloghi: quello lo fanno altri.

I numeri li ha gia' calcolati il codice. Tu **non scrivi numeri**: indichi quale
misura, e dici perche'. Se scrivi un numero la risposta viene rifiutata per
intero -- non perche' sia scortese, ma perche' un numero sbagliato dentro un
rapporto che sembra autorevole e' il danno peggiore che tu possa fare.

**Il silenzio e' un esito legittimo.** Se una cosa funziona non va segnalata:
otto giorni al 99% non sono una notizia. Poche cose dette bene, o nessuna.

**Non inventare soglie.** Lo scostamento e' gia' misurato contro la storia di
quel dato; se la base e' di pochi giorni, dillo invece di fingere che sia
solida.

**Puoi guardare la casa, non toccarla.** Hai i lettori (search, related,
history, mind) e compute, che fa un conto col motore delle ricette: usali
quando una riga non basta a dire se una cosa e' spiegata. Cio' che leggi lo
registra il codice; anche i numeri che ti tornano restano fuori dalla
risposta."""

ANSWER_CONTRACT = """Rispondi SOLO con un oggetto JSON di questa forma:

{"osservazioni": [
  {"quale": <il NUMERO fra parentesi quadre della misura, come nell'elenco>,
   "innesco": <solo se la misura ne ha piu' d'uno: uno dei suoi «inneschi»>,
   "cosa": "cosa hai visto, in una frase",
   "spiegato": "da cosa e' spiegato, oppure null se non lo e'",
   "cosa_cambierebbe": "facoltativo: cosa cambierebbe rispetto all'obiettivo",
   "da_riverificare": "facoltativo: cosa vuoi ricontrollare"}
],
 "rimetti": [{"id": "<entity_id da far rientrare fra le cose guardate>",
              "perche": "perche' serve"}]}

Gli inneschi sono tre, e il codice li ha gia' marcati su ogni misura:
  1 = qualcosa e' cambiato, e non e' spiegato da cio' che gia' sappiamo
  2 = qualcosa e' stabile e costa
  3 = qualcosa non c'e' piu' (la copertura crolla, o la misura smette di
      calcolarsi)
Una misura senza «inneschi» non e' candidata a un'osservazione. «rimetti» e'
facoltativo.

Cio' che hai gia' detto con la stessa prova non ridirlo: il codice lo
riconosce e lo toglie. Se la prova e' cambiata, puoi ridirlo.

Niente numeri: li mette il codice. Un elenco vuoto va benissimo."""


def build_question(series: dict, previous: list[dict] | None = None, *,
                   refused: list[str] | None = None,
                   presence=None) -> str | None:
    """La domanda intera, o `None` se non c'e' niente da analizzare.

    `refused` sono i problemi della risposta di prima, se e' stata rifiutata
    (D10, `steering.refused_problems`): il giro che riprova li rimette nella
    domanda, sulla catena come sul ponte, cosi' il modello sa cosa correggere.

    `presence` (`privacy.PresenceMask`) copre i nomi delle persone anche qui,
    non solo nelle risposte degli strumenti (G26-1, nota sull'indice): i nomi
    delle misure vengono dai resoconti, coi nomi dei dispositivi, e un
    dispositivo di una persona nello scope portava il suo nome nella domanda.
    E' la stessa maschera del guardiano del turno, quindi la stessa
    numerazione.

    `None` quando non c'e' nessuna serie: una casa senza misure non ha niente
    da analizzare, e la domanda costerebbe un giro per una risposta che non
    puo' esistere. Stessa regola di `recipe_turn.build_device_question` con un
    dispositivo senza entita'.

    **L'indice, non le trenta colonne** (D2 del piano degli attori,
    06/10/2026). Fino a quel giorno ogni misura arrivava con i suoi trenta
    valori e le sue trenta coperture: ~35.000 token il 15/09/2026, 58.404 a
    turno il 01/10. Ora una riga per misura coi numeri che il codice ha gia'
    calcolato (`analyst.index`) e i fatti dei tre inneschi; le serie intere
    sono una lettura da chiedere, non un peso da portare.

    **La memoria** (D4): cio' che l'analista ha gia' detto nei giorni della
    finestra, una voce per impronta, con la prova di allora e l'esito della
    proposta che ne e' nata (`analyst.previous_observations`).
    """
    rows = series.get("serie") or []
    if not rows:
        return None
    days = list(series.get("giorni") or [])
    lines = ["L'obiettivo di questa casa:"]
    lines.extend(_objective_lines(series.get("obiettivi") or [], days))
    lines.append("")
    rules = _rules_lines(series.get("regole") or [])
    if rules:
        lines.extend(rules)
        lines.append("")
    if days:
        lines.append(f"I resoconti vanno dal {days[0]} al {days[-1]}: "
                     f"{len(days)} giorni. «ultimo» e' il {days[-1]}.")
        lines.append("")
    lines.append("Le misure, NUMERATE e in ordine: prima quelle che si "
                 "scostano di piu' dalla loro storia, poi le altre. Il numero "
                 "fra parentesi quadre e' la chiave con cui te ne riferisci. "
                 "«inneschi» sono i fatti che il codice ha trovato per ogni "
                 "riga:")
    for number, row in analyst.index(series):
        lines.append(f"[{number}] " + json.dumps(row, ensure_ascii=False))
    lines.append("")
    if previous:
        lines.append("Cio' che hai gia' detto nei giorni scorsi, una voce per "
                     "misura e innesco, con la prova di allora e l'esito della "
                     "proposta che ne e' nata («quale» e' il numero della "
                     "misura qui sopra, se c'e' ancora):")
        for said in previous:
            shown = {k: v for k, v in said.items() if k != "impronta"}
            lines.append("- " + json.dumps(shown, ensure_ascii=False))
        lines.append("")
    lines.extend(refused_lines(refused))
    lines.append(ANSWER_CONTRACT)
    question = "\n".join(lines)
    return presence.mask(question) if presence is not None else question


def _objective_lines(runs: list[dict], days: list[str]) -> list[str]:
    """L'obiettivo «in vigore dal ...», e «fino al ...» solo per quello che e'
    stato cambiato (D2, piano degli attori). «Dal ... al ...» su quello
    corrente si leggeva come una scadenza: l'audit del 01/10/2026 l'ha
    trovato."""
    if not runs:
        return ["  (nessun obiettivo dichiarato per questi giorni)"]
    last_day = days[-1] if days else None
    out = []
    for run in runs:
        if run.get("al") == last_day:
            out.append(f"  in vigore dal {run['dal']}: {run['testo']}")
        else:
            out.append(f"  dal {run['dal']} fino al {run['al']}: {run['testo']}")
    return out


def _rules_lines(runs: list[dict]) -> list[str]:
    """I giorni misurati prima della regola del dato fermo (Tappa 8, G-03, D2):
    i tratti con `regole: None` (`report._rules_runs`). Senza questa riga
    l'analista leggerebbe come vero un valore che puo' venire da una fonte
    ferma -- la produzione a zero del 30/09/2026, con la copertura piena. Una
    lista vuota quando ogni giorno porta le sue regole: la frase non serve."""
    before = [run for run in runs if run.get("regole") is None]
    if not before:
        return []
    out = [("Misurati prima della regola del dato fermo (le regole con cui "
            "sono nati non sono scritte): un valore di questi giorni puo' "
            "venire da una fonte che aveva smesso di parlare.")]
    for run in before:
        if run.get("dal") == run.get("al"):
            out.append(f"  il {run.get('dal')}")
        else:
            out.append(f"  dal {run.get('dal')} al {run.get('al')}")
    return out


def bridge_turn(series: dict, previous: list[dict] | None = None, *,
                refused: list[str] | None = None,
                presence=None) -> dict | None:
    """Il turno da accodare al ponte, o `None` se non c'e' da chiedere.

    Stessa forma di `recipe_turn.bridge_turn` e di `observer.bridge_turn`, e
    per le stesse ragioni: il ponte gira altrove e non ha gli archivi, e
    `istruzione` serve perche' altrimenti l'istruzione di chiusura della chat
    gli vieta il JSON che qui si chiede.
    """
    question = build_question(series, previous, refused=refused, presence=presence)
    if question is None:
        return None
    return {"history": [{"role": "user", "content": question}],
            "system_prompt": SYSTEM,
            "istruzione": ANSWER_CONTRACT}


# ── Gli strumenti dell'analista (D5 del piano degli attori; Task 3.6) ────────

#: **I lettori che l'analista riceve: un elenco d'AMMISSIONE**, come
#: `keeper/exchange.SOLA_LETTURA` -- decisione 13 della spec della fonte
#: unica, «un attore non e' una persona: sola lettura dichiarata». Uno
#: strumento nuovo della chat non entra qui da solo: entra quando qualcuno
#: scrive perche'.
#:
#: - `search` -- cosa e' una cosa della casa, e dove sta;
#: - `related` -- a cosa e' legata (il dispositivo, l'area, le sorelle);
#: - `history` -- stati, valori, esecuzioni e registro degli errori: cio' che
#:   una riga dell'indice riassume, quando l'analista vuole vederlo;
#: - `mind` -- cio' che il cervello guarda: lo scope, l'obiettivo, le porzioni
#:   dei resoconti e le analisi (Tappa 5, Task 8).
#:
#: Fuori, per scelta (D5): `execute`, `remember`, `promise`, `propose`,
#: `confirm`, `cancel` -- scrivono o impegnano -- e `fetch`, `calendar`, che
#: nessuna osservazione dell'audit del 01/10/2026 ha chiesto. `compute` non
#: e' un lettore della chat: lo serve il guardiano qui sotto.
READERS = ("search", "related", "history", "mind")


def analyst_tools() -> list[dict]:
    """Il catalogo del turno: i lettori, con gli STESSI dizionari della chat
    (`KNOWLEDGE_TOOLS`, filtrati e non copiati), piu' `compute`."""
    from ..home_space.tools import KNOWLEDGE_TOOLS
    from .compute import tool_def

    admitted = [d for d in KNOWLEDGE_TOOLS if d["name"] in READERS]
    if len(admitted) != len(READERS):
        # Un lettore rinominato nella chat svuoterebbe il catalogo IN
        # SILENZIO: si dichiara, come per la promessa.
        logger.error("catalogo dell'analista incompleto: mancano %s",
                     sorted(set(READERS) - {d["name"] for d in admitted}))
    return admitted + [tool_def()]


class AnalystDispatcher:
    """Il guardiano del turno: lascia scendere i lettori, serve `compute`, e
    rifiuta il resto con la frase della promessa (`steering.refused_tool`).

    Sta DAVANTI al dispatcher della chat invece di modificarlo, come
    `PromiseDispatcher`: `compute` non deve esistere nella chat. Lo stesso
    oggetto risponde sulla catena (`server.analyst_round`) e sul ponte
    (`/api/mcp`, `steering.Species.guard`).
    """

    def __init__(self, below, *, ha, house, timezone: str | None,
                 presence=None) -> None:
        self._below = below
        self._ha = ha
        self._house = house
        self._timezone = timezone
        #: Il filtro dei nomi delle persone (`privacy.PresenceMask`; decisione
        #: 12 estesa agli strumenti degli attori, «Segnaposto», 06/10/2026):
        #: cio' che torna al modello passa da `mask`, cio' che il modello manda
        #: da `unmask`. `None` senza casa: non c'e' niente da coprire.
        self.presence = presence

    async def dispatch(self, name: str, arguments: dict | None) -> dict:
        from ..steering import refused_tool
        from .compute import COMPUTE_TOOL_NAME, compute

        arguments = arguments or {}
        if name == COMPUTE_TOOL_NAME:
            if self._ha is None or self._house is None:
                return {"errore": ("la casa non e' ancora letta, o Home Assistant "
                                   "non e' collegato: non posso leggere le serie")}
            return self._covered(await compute(
                self._uncovered(arguments), ha=self._ha, house=self._house,
                now=time.time(), timezone=self._timezone))
        if name not in READERS:
            return refused_tool(
                name, doing="mentre analizzo le misure",
                instead=("Se serve un'azione, scrivila in «cosa_cambierebbe»: "
                         "la proposta la decide qualcun altro."))
        return self._covered(await self._below.dispatch(name, self._uncovered(arguments)))

    def _covered(self, result):
        return result if self.presence is None else self.presence.mask(result)

    def _uncovered(self, arguments):
        return arguments if self.presence is None else self.presence.unmask(arguments)


async def guard(app, exchange: str | None = None) -> AnalystDispatcher:
    """Il dispatcher di un turno dell'analista, sulla catena e sul ponte.

    Una casa sola per il turno: quella dei lettori e quella di `compute` sono
    la stessa (`create_tool_dispatcher(house=...)`), con l'elenco delle
    statistiche dalla lettura condivisa dei giri
    (`house_history.statistic_ids_for_round`). Se l'elenco non si legge,
    `compute` non afferma che un'entita' ne e' senza.
    """
    from ..api.handlers_chat import create_tool_dispatcher
    from ..home_space import historian
    from ..home_space.house import House
    from ..home_space.house_history import statistic_ids_for_round
    from ..home_space.privacy import PresenceMask

    store = app.get("home_space_store")
    ha = app.get("ha_client")
    house = House.read(store, app.get("entity_cache")) if store is not None else None
    if house is not None and ha is not None:
        with_statistics = await statistic_ids_for_round(app, ha)
        if not isinstance(with_statistics, dict):
            house = house.with_statistics(with_statistics)
    # Il soffitto dichiarato dal mestiere (decisione 13): legge e amministra,
    # non comanda. Fino al 07/10/2026 qui non c'era, e `None` non negava niente.
    below = create_tool_dispatcher(app, exchange=exchange, house=house,
                                   soffitto=SPECIES[ANALYST_SPECIES].ceiling())
    return AnalystDispatcher(below, ha=ha, house=house,
                             timezone=historian.house_timezone(store),
                             presence=PresenceMask(house) if house is not None else None)
