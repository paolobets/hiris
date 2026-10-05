"""Il turno dell'**attuatore** (spec 2026-09-21 §2).

Gemello di `analyst_turn.py`, e per la stessa ragione: il modello dice cosa ha
trovato e cosa propone, il codice **valida e rifiuta**. Una risposta storta non
si corregge -- si rifiuta per intero, e il giro dopo riprova.

**Due gesti nella risposta, tre nell'archivio**, e la differenza e' esattamente
il potere che al modello non e' stato dato:

- `indagine` -- sola lettura. La maggior parte delle osservazioni, sulla casa
  vera, sono domande: «il sensore era fermo?», «a che ore e' avvenuto il prelievo?».
  Rispondere vale piu' che proporre, e una coda che non si riempie e' il primo
  obiettivo di questo attore.
- `proposta` -- non scrive niente: passa da `Workshop.propose`, che compone e valida
  ma non tocca la casa, e lascia i tre esiti a chi amministra la casa.
- `riparazione` -- **la faceva il codice**, non il modello: fino al
  05/10/2026 il giro riscriveva la ricetta rotta prima di chiamarlo e
  aggiungeva l'esito come fatto. Ora le ricette le ripara il loro giro
  (attori, Task 1.6, D2), e il gesto resta solo nelle attuazioni gia'
  archiviate, che la pagina continua a leggere. Il modello non l'ha mai
  potuto dichiarare: avrebbe potuto dichiarare una riparazione non avvenuta.
"""
from __future__ import annotations

import json
import logging

from ..action.construction.workshop import closed_fields, form_refusal
from ..home_space.tools import PROPOSE_TOOL_DEF
from ..proxy.ha_client import HAClient
from ..steering import read_json

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner.
ACTUATION_TURN_KIND = "attuazione"

#: **Il tetto della risposta, dichiarato** (Tappa 6, Task 4; D3, approvata
#: il 05/10/2026). Fino a quel giorno questo mestiere non ne passava nessuno e
#: prendeva i 4.096 di fabbrica di `claude_runner.MAX_TOKENS`: lo stesso
#: numero, scelto da nessuno. Qui e' lo stesso valore SCRITTO -- il
#: comportamento non cambia, diventa visibile. **Non e' misurato**: per l'attuatore
#: (in pausa dal 01/10/2026) non c'e' una misura, e il valore lo sceglie la
#: misura dal vivo quando il piano degli attori lo riaccende.
MAX_ANSWER_TOKENS = 4096

#: I gesti che il MODELLO puo' rivendicare nella sua risposta. **Due, non
#: tre**: la riparazione non e' sua (la faceva il codice di questo giro fino al
#: 05/10/2026, ora il giro delle ricette), e lasciarla dire al modello
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

Le ricette rotte non le ripari tu, e non le ripara questo giro: le riscrive
da solo il giro delle ricette, quando la causa e' una che una ricetta nuova
puo' aggirare. Una ricetta che non si esegue piu' la segnali come proposta da
fare a mano, senza dichiarare una riparazione.

**Non tocchi la casa.** Non accendi, non spegni, non scrivi configurazioni: le
proposte le decide chi amministra la casa, una per una.

**Il silenzio e' un esito legittimo.** Se hai guardato e non c'e' niente da
fare, dillo: e' diverso dal non aver guardato.

**Non inventare cosa hai trovato.** Se non hai potuto verificare qualcosa,
scrivilo invece di dedurlo: un'indagine inventata e' peggio di nessuna
indagine, perche' sembra una risposta."""

#: I campi dello schema di `propose` che l'attuatore NON riceve, ognuno con la
#: sua ragione. Lista di esclusione: un campo nuovo dello schema entra nel
#: contratto da solo.
#:
#: - `frase` e' «la frase di chi ti sta parlando, verbatim»: all'attuatore non
#:   parla nessuno, e qualunque cosa ci scrivesse sarebbe una citazione
#:   inventata.
INTENT_EXCLUDED = ("frase",)

#: Come si mostra il valore d'esempio di un campo, per tipo dello schema JSON.
#: Sono forme, non contenuti: cosa va dentro lo dice la descrizione del campo
#: nella legenda sotto l'esempio. Una lista si mostra VUOTA: lo schema dice
#: solo che le voci sono oggetti, e un oggetto vuoto d'esempio la porta lo
#: rifiuterebbe (un helper senza `dominio`) -- l'esempio deve passare dalla
#: porta, e lo prova `tests/test_attuatore_intenzione.py`.
_EXAMPLE_VALUE = {"string": '"..."', "boolean": "true | false", "object": "{}",
                  "array": "[]"}


def _example_value(field: str, spec: dict, vocabularies: dict) -> str:
    choices = spec.get("enum") or vocabularies.get(field)
    if choices:
        return " | ".join(json.dumps(choice, ensure_ascii=False) for choice in choices)
    return _EXAMPLE_VALUE[spec.get("type", "string")]


def _intent_contract() -> tuple[str, str]:
    """L'`intenzione` del contratto, **derivata dallo schema dello strumento
    `propose`** (`home_space/tools.PROPOSE_TOOL_DEF`) e dai vocabolari chiusi
    che la porta dell'officina impone (`workshop.closed_fields`): l'esempio,
    e la legenda dei campi con la descrizione dello schema.

    Fino al 05/10/2026 la forma era scritta a mano qui, e non era quella
    dell'officina: l'innesco come frase e «richiesto» libero. Ogni proposta
    costruibile veniva rifiutata dalla forma (Tappa 6, D5, misurato con
    `workshop._invalid_form`). Derivata, cambia insieme allo schema.
    """
    tool_schema = PROPOSE_TOOL_DEF["input_schema"]
    vocabularies = closed_fields(HAClient.CONFIGURABLE_DOMAINS)
    fields = [(name, spec) for name, spec in tool_schema["properties"].items()
              if name not in INTENT_EXCLUDED]
    pad = " " * len('   "intenzione": {')
    example = ",\n".join(
        f'{json.dumps(name)}: {_example_value(name, spec, vocabularies)}'
        for name, spec in fields).replace("\n", "\n" + pad)
    legend = "\n".join(
        f"- `{name}`"
        + (" (sempre)" if name in tool_schema.get("required", ()) else "")
        + f": {spec.get('description', '').strip()}"
        for name, spec in fields)
    return "{" + example + "}", legend


_INTENT_EXAMPLE, _INTENT_LEGEND = _intent_contract()

ANSWER_CONTRACT = f"""Rispondi SOLO con un oggetto JSON di questa forma:

{{"esiti": [
  {{"osservazione": <il numero dell'osservazione, come nell'elenco>,
   "gesto": "indagine" | "proposta",
   "trovato": "cosa hai trovato o cosa proponi, in una frase",
   "costruibile": true | false,
   "intenzione": {_INTENT_EXAMPLE}}}
]}}

`costruibile` serve solo alla proposta: `true` se e' un oggetto che Home
Assistant sa tenere, `false` se e' una cosa che deve fare una persona.

**Se scrivi `costruibile: true` devi portare anche `intenzione`**: una frase in
prosa non basta a costruire niente, e senza l'intenzione la proposta viene
rifiutata per intero. Se non sai comporla, scrivi `costruibile: false` e dilla
a parole: e' meglio di una costruzione che non sta in piedi.

L'intenzione e' la stessa che riceve chi costruisce in Home Assistant, e ne
ha la forma: un campo con le alternative ne accetta UNA, una lista resta una
lista anche con una voce sola, e i campi che non servono si omettono. I campi:
{_INTENT_LEGEND}

Un elenco vuoto va benissimo: vuol dire che hai guardato e non c'era niente da
fare."""


def build_question(observations) -> str | None:
    """La domanda intera, o `None` se non c'e' niente da chiedere.

    Le osservazioni si consegnano **numerate**, e il modello si riferisce a
    una col suo numero: ricopiarne il testo vorrebbe dire poterlo sbagliare, e
    un esito attaccato all'osservazione sbagliata e' peggio di nessun esito.
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
    lines.append(ANSWER_CONTRACT)
    return "\n".join(lines)


def apply_actuation(observations, answer: str, *, truncated: bool = False) -> dict:
    """Cosa si fa della risposta: si valida, e si rifiuta se e' storta.

    Torna `{"attuazione": dict | None, "problemi": [...], "risposta": bool}`.

    `attuazione` e' `None` quando c'e' anche un solo problema -- e **tutti i
    problemi si dicono insieme**: dirne uno per giro costringerebbe a
    rieseguire il turno per scoprire il successivo, e un turno costa.
    """
    # Il JSON lo cava il lettore unico (`steering.read_json`, D-11), come per
    # l'analista: un turno troncato non si legge (D2).
    data, reason = read_json(answer, shape=dict, what="un oggetto con gli esiti",
                             truncated=truncated)
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
        # **Costruibile senza intenzione non e' costruibile**: l'officina vuole
        # gesto, dominio e il resto, e una frase in prosa non li ha. Meglio un
        # rifiuto che una costruzione che non sta in piedi.
        if gesture == "proposta" and outcome.get("costruibile"):
            intent = outcome.get("intenzione")
            ok = (isinstance(intent, dict) and intent.get("gesto")
                  and intent.get("dominio"))
            if not ok:
                problems.append(
                    f"l'esito {index} si dice costruibile ma non porta "
                    "un'intenzione con `gesto` e `dominio`: una frase in prosa "
                    "non basta a costruire niente")
            else:
                # **La stessa porta dell'officina, prima dell'officina**
                # (Tappa 6, D5). Un'intenzione che `workshop.propose`
                # rifiuterebbe si rifiuta qui, col suo motivo: il giro dopo
                # riprova, invece di spendere il turno per una proposta che
                # muore al confine.
                refusal = form_refusal(intent, HAClient.CONFIGURABLE_DOMAINS)
                if refusal is not None:
                    problems.append(
                        f"l'esito {index} porta un'intenzione che non si puo' "
                        f"costruire: {refusal}")
        kept.append(outcome)
    if problems:
        return {"attuazione": None, "problemi": problems, "risposta": True}
    return {"attuazione": {"esiti": kept}, "problemi": [], "risposta": True}
