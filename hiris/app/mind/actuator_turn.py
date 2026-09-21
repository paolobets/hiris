"""Il turno dell'**attuatore** (spec 2026-09-21 §2).

Gemello di `analyst_turn.py`, e per la stessa ragione: il modello dice cosa ha
trovato e cosa propone, il codice **valida e rifiuta**. Una risposta storta non
si corregge -- si rifiuta per intero, e il giro dopo riprova.

**Due gesti nella risposta, tre nell'archivio**, e la differenza e' esattamente
il potere che al modello non e' stato dato:

- `indagine` -- sola lettura. Cinque osservazioni su otto, sulla casa vera,
  sono domande: «il sensore era fermo?», «a che ore e' avvenuto il prelievo?».
  Rispondere vale piu' che proporre, e una coda che non si riempie e' il primo
  obiettivo di questo attore.
- `proposta` -- non scrive niente: passa da `costruisci`, che compone e valida
  ma non tocca la casa, e lascia i tre esiti al proprietario.
- `riparazione` -- **la fa il codice**, non il modello: il giro riscrive la
  ricetta rotta prima di chiamarlo e aggiunge l'esito come fatto. Se potesse
  dichiararla lui, potrebbe dichiarare una riparazione che non e' avvenuta --
  una bugia archiviata, indistinguibile da un fatto.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner.
ACTUATION_TURN_KIND = "attuazione"

#: I gesti che il MODELLO puo' rivendicare nella sua risposta. **Due, non
#: tre**: la riparazione la fa il codice (il giro riscrive la ricetta prima di
#: chiedere, e aggiunge l'esito come fatto), e lasciarla dire al modello
#: vorrebbe dire lasciargli dichiarare una riparazione che non e' avvenuta --
#: una bugia archiviata, indistinguibile da un fatto.
GESTURES = ("indagine", "proposta")

#: I gesti che esistono nell'ARCHIVIO, cioe' quelli che la pagina puo'
#: incontrare leggendo un'attuazione. La differenza fra i due elenchi e'
#: esattamente il potere che al modello non e' stato dato.
OUTCOME_GESTURES = ("indagine", "riparazione", "proposta")

SYSTEM = """Sei l'attuatore di HIRIS, un sistema che guarda una casa domotica.

L'analista ti consegna cio' che ha concluso. Il tuo mestiere e' UNO: prendere
quelle conclusioni e **fare il passo successivo** -- e il passo successivo,
quasi sempre, non e' costruire qualcosa.

Hai due gesti, e nessun altro:

1. INDAGINE -- vai a vedere e rispondi. La maggior parte delle osservazioni
   sono domande («il sensore era fermo?», «a che ore e' avvenuto il
   prelievo?»). Guardare e rispondere vale piu' che proporre: se l'indagine
   chiude la questione hai finito, e non si propone niente.
2. PROPOSTA -- quando c'e' davvero qualcosa da fare. Di' se e' un oggetto che
   Home Assistant sa tenere (un'automazione, una scena, un helper) oppure una
   cosa che deve fare una persona: molte cose utili non sono oggetti di Home
   Assistant, e proporle come tali le fa fallire.

Le ricette rotte le ho gia' riscritte io prima di chiamarti, e te lo dico nella
domanda: non riproporle.

**Non tocchi la casa.** Non accendi, non spegni, non scrivi configurazioni: le
proposte le decide il proprietario, una per una.

**Il silenzio e' un esito legittimo.** Se hai guardato e non c'e' niente da
fare, dillo: e' diverso dal non aver guardato.

**Non inventare cosa hai trovato.** Se non hai potuto verificare qualcosa,
scrivilo invece di dedurlo: un'indagine inventata e' peggio di nessuna
indagine, perche' sembra una risposta."""

ANSWER_CONTRACT = """Rispondi SOLO con un oggetto JSON di questa forma:

{"esiti": [
  {"osservazione": <il numero dell'osservazione, come nell'elenco>,
   "gesto": "indagine" | "proposta",
   "trovato": "cosa hai trovato o cosa proponi, in una frase",
   "costruibile": true | false}
]}

`costruibile` serve solo alla proposta: `true` se e' un oggetto che Home
Assistant sa tenere, `false` se e' una cosa che deve fare una persona.

Un elenco vuoto va benissimo: vuol dire che hai guardato e non c'era niente da
fare."""


def read_actuation(answer: str) -> tuple[dict | None, str | None]:
    """La risposta letta come dato: `(dati, ragione)`.

    Stessa forma di `analyst_turn.read_analysis`: o esce un dizionario, o esce
    il perche' non si e' potuto leggere -- mai un'eccezione, perche' un guasto
    di forma non deve fermare il giro.
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
        return None, "la risposta non e' un oggetto con gli esiti"
    return data, None


def build_question(observations, repaired) -> str | None:
    """La domanda intera, o `None` se non c'e' niente da chiedere.

    Le osservazioni si consegnano **numerate**, e il modello si riferisce a
    una col suo numero: ricopiarne il testo vorrebbe dire poterlo sbagliare, e
    un esito attaccato all'osservazione sbagliata e' peggio di nessun esito.

    `repaired` sono le ricette gia' riscritte in questo giro, prima della
    domanda: senza dirglielo, il modello proporrebbe di riparare una cosa gia'
    riparata.
    """
    rows = list(observations or [])
    if not rows:
        return None
    lines = ["Le osservazioni dell'analista di oggi, numerate:"]
    for index, row in enumerate(rows):
        lines.append(f"  [{index}] {row.get('soggetto')} · {row.get('misura')}"
                     + (f" ({row.get('chiave')})" if row.get("chiave") else ""))
        lines.append(f"      cosa ha visto: {row.get('cosa')}")
        lines.append(f"      cosa cambierebbe: {row.get('cosa_cambierebbe')}")
        base = row.get("base")
        lines.append(f"      si regge su {base} giorni di storia"
                     if base else "      non ha una storia dietro")
        if row.get("spiegato"):
            lines.append(f"      gia' spiegato da: {row.get('spiegato')}")
    lines.append("")
    if repaired:
        lines.append("Ricette gia' riscritte in questo giro (non riproporle):")
        for row in repaired:
            lines.append(f"  - {row.get('soggetto')} · {row.get('misura')}")
        lines.append("")
    lines.append(ANSWER_CONTRACT)
    return "\n".join(lines)


def apply_actuation(observations, answer: str) -> dict:
    """Cosa si fa della risposta: si valida, e si rifiuta se e' storta.

    Torna `{"attuazione": dict | None, "problemi": [...], "risposta": bool}`.

    `attuazione` e' `None` quando c'e' anche un solo problema -- e **tutti i
    problemi si dicono insieme**: dirne uno per giro costringerebbe a
    rieseguire il turno per scoprire il successivo, e un turno costa.
    """
    data, reason = read_actuation(answer)
    if data is None:
        answered = bool(str(answer or "").strip())
        if not answered:
            logger.warning(
                "attuatore: nessuna risposta -- non si scrive niente, si "
                "riprova al giro dopo (una risposta che non c'e' non e' un "
                "silenzio)")
        return {"attuazione": None, "problemi": [reason], "risposta": answered}

    seen = data.get("esiti")
    if not isinstance(seen, list):
        return {"attuazione": None, "risposta": True,
                "problemi": [("la risposta non porta un elenco `esiti`: un "
                              "elenco vuoto e' silenzio, e va bene; l'assenza "
                              "dell'elenco e' un'altra cosa")]}

    rows = list(observations or [])
    problems = []
    kept = []
    for index, outcome in enumerate(seen):
        if not isinstance(outcome, dict):
            problems.append(f"l'esito {index} non e' un oggetto")
            continue
        which = outcome.get("osservazione")
        if not isinstance(which, int) or isinstance(which, bool) \
                or not 0 <= which < len(rows):
            problems.append(
                f"l'esito {index} nomina l'osservazione {which!r}, che non e' "
                f"nell'elenco (ce ne sono {len(rows)})")
        gesture = outcome.get("gesto")
        if gesture not in GESTURES:
            problems.append(
                f"l'esito {index} porta il gesto {gesture!r}: i gesti sono "
                + ", ".join(GESTURES))
        if not str(outcome.get("trovato") or "").strip():
            problems.append(
                f"l'esito {index} non dice cosa ha trovato o cosa propone")
        kept.append(outcome)
    if problems:
        return {"attuazione": None, "problemi": problems, "risposta": True}
    return {"attuazione": {"esiti": kept}, "problemi": [], "risposta": True}
