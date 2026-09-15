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

import json
import logging

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner.
ANALYSIS_TURN_KIND = "analisi"

#: I tre inneschi della spec §10. Sono tre e sono dichiarati: un'osservazione
#: che non dice quale dei tre non e' dell'analista, e' un commento.
TRIGGERS = (1, 2, 3)

#: I campi che il modello NON deve scrivere: sono i numeri, e li mette il
#: codice. Elencati qui perche' il rifiuto possa dire quale ha trovato.
NUMERIC_FIELDS = ("valore", "numero", "copertura", "quanti_scarti", "scarto",
                  "mediana", "base")


def read_analysis(answer: str) -> tuple[dict | None, str | None]:
    """La risposta letta come dato: `(dati, ragione)`.

    Stessa forma di `recipe_turn.read_recipe`: o esce un dizionario, o esce il
    perche' non si e' potuto leggere -- mai un'eccezione, perche' un guasto di
    forma non deve fermare la notte.
    """
    text = str(answer or "").strip()
    if not text:
        return None, "il modello non ha risposto"
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as error:
        return None, f"la risposta non e' JSON leggibile: {error}"
    if not isinstance(data, dict):
        return None, "la risposta non e' un oggetto con le osservazioni"
    return data, None


def apply_analysis(series: dict, answer: str) -> dict:
    """Cosa si fa della risposta: si valida, e si **arricchisce coi numeri**.

    Torna `{"analisi": dict | None, "problemi": [...], "risposta": bool}`.

    `analisi` e' `None` quando c'e' anche un solo problema: si rifiuta, non si
    corregge, e **tutti i problemi si dicono insieme** -- dirne uno per giro
    costringerebbe a rieseguire la notte per scoprirne un altro.
    """
    data, reason = read_analysis(answer)
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

    known = {(row.get("soggetto"), row.get("misura"), row.get("chiave")): row
             for row in series.get("serie") or []}
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

    where = (line.get("soggetto"), line.get("misura"), line.get("chiave"))
    row = known.get(where)
    if row is None:
        problems.append(
            f"l'osservazione {number} parla di «{line.get('soggetto')} · "
            f"{line.get('misura')}"
            + (f" · {line.get('chiave')}" if line.get("chiave") else "")
            + "», che non e' fra le misure consegnate")

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
  {"soggetto": "<il soggetto della misura>",
   "misura": "<il nome della misura>",
   "chiave": "<la chiave, o null se la misura non ne ha>",
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

    **Costa, ed e' misurato.** Sulla casa vera il 15/09/2026, con venti giorni
    archiviati e 146 serie: ~35.000 token a giro, una volta al giorno. Tre
    volte il giro dell'osservatore. Va saputo, non scoperto in bolletta.
    """
    rows = series.get("serie") or []
    if not rows:
        return None
    lines = ["L'obiettivo di questa casa, giorno per giorno:"]
    for run in series.get("obiettivi") or []:
        lines.append(f"  dal {run['dal']} al {run['al']}: {run['testo']}")
    if not (series.get("obiettivi") or []):
        lines.append("  (nessun obiettivo dichiarato per questi giorni)")
    lines.append("")
    lines.append(f"I giorni, in ordine: {', '.join(series.get('giorni') or [])}")
    lines.append("")
    lines.append("Le misure, una riga per misura, coi valori in quell'ordine:")
    lines.append(json.dumps({"serie": [_compact(r) for r in rows]},
                            ensure_ascii=False))
    lines.append("")
    lines.append(ANSWER_CONTRACT)
    return "\n".join(lines)


def _compact(row: dict) -> dict:
    """Una riga di serie, alleggerita di cio' che non dice niente.

    **La copertura piena non si ripete trenta volte.** Misurato sulla casa vera
    il 15/09/2026: le coperture sono il **18%** del prompt, e quasi tutte sono
    `1.0` ripetuto. E' la stessa regola gia' scritta per la pagina -- «100%
    accanto a ogni numero e' rumore su cui l'attenzione smette di fermarsi» --
    e vale per il modello quanto per l'occhio.

    **Ma se la copertura cambia, si scrive per intero**: quello e' il terzo
    innesco, ed e' esattamente cio' che si va a cercare. Si comprime solo
    quando non c'e' niente da vedere.
    """
    out = dict(row)
    known = [c for c in (row.get("coperture") or []) if c is not None]
    if known and all(c == 1.0 for c in known):
        out["coperture"] = "piena tutti i giorni in cui la misura c'era"
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
