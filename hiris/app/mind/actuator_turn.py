"""Il turno dell'**attuatore** (spec 2026-09-21 §2): tre gesti, e nient'altro.

Gemello di `analyst_turn.py`, e per la stessa ragione: il modello dice cosa ha
fatto e cosa ha trovato, il codice **valida e rifiuta**. Una risposta storta
non si corregge -- si rifiuta per intero, e il giro dopo riprova.

**I tre gesti sono chiusi**, e ognuno ha il suo confine:

- `indagine` -- sola lettura. Cinque osservazioni su otto, sulla casa vera,
  sono domande: «il sensore era fermo?», «a che ore e' avvenuto il prelievo?».
  Rispondere e' meglio che proporre, e una coda che non si riempie e' il primo
  obiettivo di questo attore.
- `riparazione` -- scrive **solo nel sapere di HIRIS** (le ricette). E' l'unico
  gesto che scrive senza chiedere, e la ragione e' che e' lo stesso atto che il
  giro notturno delle ricette fa gia' senza chiedere a nessuno.
- `proposta` -- non scrive niente: passa da `costruisci`, che compone e valida
  ma non tocca la casa, e lascia i tre esiti al proprietario.

Un quarto gesto sarebbe un potere che nessuno ha dato a questo attore, e
arriverebbe dentro una risposta: per questo l'elenco e' chiuso e la risposta si
rifiuta.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner.
ACTUATION_TURN_KIND = "attuazione"

#: I tre gesti, chiusi. L'ordine e' quello della spec §2, che e' anche quello
#: in cui si preferiscono: rispondere, riparare, proporre.
GESTURES = ("indagine", "riparazione", "proposta")

SYSTEM = """Sei l'attuatore di HIRIS, un sistema che guarda una casa domotica.

L'analista ti consegna cio' che ha concluso. Il tuo mestiere e' UNO: prendere
quelle conclusioni e **fare il passo successivo** -- e il passo successivo,
quasi sempre, non e' costruire qualcosa.

Hai tre gesti, e nessun altro:

1. INDAGINE -- vai a vedere e rispondi. La maggior parte delle osservazioni
   sono domande («il sensore era fermo?», «a che ore e' avvenuto il
   prelievo?»). Guardare e rispondere vale piu' che proporre: se l'indagine
   chiude la questione, hai finito, e non si propone niente.
2. RIPARAZIONE -- quando una misura non si calcola piu' perche' la ricetta non
   regge, la ricetta si riscrive. Riguarda il sapere di HIRIS, non la casa.
3. PROPOSTA -- quando c'e' davvero qualcosa da fare. Di' se e' un oggetto che
   Home Assistant sa tenere (un'automazione, una scena, un helper) oppure una
   cosa che deve fare una persona: molte cose utili non sono oggetti di Home
   Assistant, e proporle come tali le fa fallire.

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
   "gesto": "indagine" | "riparazione" | "proposta",
   "trovato": "cosa hai trovato o cosa proponi, in una frase",
   "soggetto": "<solo per riparazione: il soggetto della misura>",
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
        if gesture == "riparazione" and not str(outcome.get("soggetto") or "").strip():
            problems.append(
                f"l'esito {index} ripara senza dire cosa: il gesto che scrive "
                "senza chiedere deve dichiarare su cosa ha scritto")
        kept.append(outcome)
    if problems:
        return {"attuazione": None, "problemi": problems, "risposta": True}
    return {"attuazione": {"esiti": kept}, "problemi": [], "risposta": True}
