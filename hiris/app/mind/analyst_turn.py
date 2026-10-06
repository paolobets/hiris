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

Le quattro cose che la spec elenca: **cosa** ha visto, **perche'** lo dice
(quale dei tre inneschi), **se e' spiegato**, **cosa cambierebbe** rispetto
all'obiettivo. Senza l'ultima e' una constatazione, non qualcosa che si
potrebbe fare -- e l'analista esiste per dire cosa si potrebbe fare.

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

from ..steering import read_json
from . import analyst

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner.
ANALYSIS_TURN_KIND = "analisi"

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

#: I tre inneschi della spec §10. Sono tre e sono dichiarati: un'osservazione
#: che non dice quale dei tre non e' dell'analista, e' un commento.
TRIGGERS = (1, 2, 3)

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


def apply_analysis(series: dict, answer: str, *, truncated: bool = False) -> dict:
    """Cosa si fa della risposta: si valida, e si **arricchisce coi numeri**.

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
    problems: list[str] = []
    enriched: list[dict] = []
    for number, line in enumerate(seen, start=1):
        if not isinstance(line, dict):
            problems.append(f"l'osservazione {number} non e' un'osservazione: {line!r}")
            continue
        built = _enrich(line, number, known, problems)
        if built is not None:
            enriched.append(built)

    if problems:
        return {"analisi": None, "problemi": problems, "risposta": True}
    return {"analisi": {"osservazioni": enriched}, "problemi": [], "risposta": True}


def _enrich(line: dict, number: int, known: dict, problems: list) -> dict | None:
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

    trigger = line.get("innesco")
    if trigger not in TRIGGERS:
        problems.append(
            f"l'osservazione {number} porta un innesco che non esiste "
            f"(«{trigger}»): sono tre, 1, 2 o 3, e senza uno dei tre e' un "
            "commento, non un'osservazione")

    if not str(line.get("cosa") or "").strip():
        problems.append(f"l'osservazione {number} non dice COSA ha visto")
    if not str(line.get("cosa_cambierebbe") or "").strip():
        problems.append(
            f"l'osservazione {number} non dice cosa cambierebbe: senza, e' una "
            "constatazione, e l'analista esiste per dire cosa si potrebbe fare")

    if row is None:
        return None
    deviation = row.get("scostamento") or {}
    values = row.get("valori") or []
    coverages = row.get("coperture") or []
    return {"soggetto": row.get("soggetto"), "nome": row.get("nome"),
            "misura": row.get("misura"), "chiave": row.get("chiave"),
            "unita": row.get("unita"),
            "innesco": trigger, "cosa": str(line.get("cosa") or "").strip(),
            "spiegato": line.get("spiegato"),
            "cosa_cambierebbe": str(line.get("cosa_cambierebbe") or "").strip(),
            "valore": values[-1] if values else None,
            "copertura": coverages[-1] if coverages else None,
            "quanti_scarti": deviation.get("quanti_scarti"),
            "mediana": deviation.get("mediana"),
            "base": deviation.get("base")}

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
solida."""

ANSWER_CONTRACT = """Rispondi SOLO con un oggetto JSON di questa forma:

{"osservazioni": [
  {"quale": <il NUMERO fra parentesi quadre della misura, come nell'elenco>,
   "innesco": 1 | 2 | 3,
   "cosa": "cosa hai visto, in una frase",
   "spiegato": "da cosa e' spiegato, oppure null se non lo e'",
   "cosa_cambierebbe": "cosa cambierebbe rispetto all'obiettivo"}
]}

Gli inneschi sono tre, e ogni osservazione deve dire quale:
  1 = qualcosa e' cambiato, e non e' spiegato da cio' che gia' sappiamo
  2 = qualcosa e' stabile e costa
  3 = qualcosa non c'e' piu' (la copertura crolla, o la misura smette di
      calcolarsi)

Niente numeri: li mette il codice. Un elenco vuoto va benissimo."""


def build_question(series: dict) -> str | None:
    """La domanda intera, o `None` se non c'e' niente da analizzare.

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
    """
    rows = series.get("serie") or []
    if not rows:
        return None
    days = list(series.get("giorni") or [])
    lines = ["L'obiettivo di questa casa:"]
    lines.extend(_objective_lines(series.get("obiettivi") or [], days))
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
    lines.append(ANSWER_CONTRACT)
    return "\n".join(lines)


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


def bridge_turn(series: dict) -> dict | None:
    """Il turno da accodare al ponte, o `None` se non c'e' da chiedere.

    Stessa forma di `recipe_turn.bridge_turn` e di `observer.bridge_turn`, e
    per le stesse ragioni: il ponte gira altrove e non ha gli archivi, e
    `istruzione` serve perche' altrimenti l'istruzione di chiusura della chat
    gli vieta il JSON che qui si chiede.
    """
    question = build_question(series)
    if question is None:
        return None
    return {"history": [{"role": "user", "content": question}],
            "system_prompt": SYSTEM,
            "istruzione": ANSWER_CONTRACT}
