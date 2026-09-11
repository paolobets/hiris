"""L'osservatore che **si dà lo scope da sé**.

Guarda la casa che gli compete -- con l'obiettivo davanti -- e decide cosa
pesa: soggetto per soggetto, col perché scritto (spec §5.1). Nessuna gamba,
nessun pavimento, nessuna lista nel codice.

**Misurato sulla casa vera il 10/09/2026.** La casa intera, una riga per
entita': 833 entita', 106.433 caratteri, ≈26.600 token. Tolte le entita' di
servizio e le nascoste: **381 entita', 46.098 caratteri, ≈11.500 token** -- le
423 di servizio e le 29 nascoste valevano **15.000 token a ogni giro**, piu'
della meta' del prompt.

**Le entita' di servizio e le nascoste non entrano di default** (decisione del
proprietario, 10/09/2026); se qualcuno le chiede esplicitamente, passano. E'
la stessa legge che il nucleo applica gia' al digesto, e si CHIAMA la sua
(`briefing.digest_visible_entity_ids`) invece di riscriverla: due copie della
stessa regola divergono al primo cambiamento da una parte sola, ed e' gia'
successo in questo prodotto (rilievo R1 dell'08/09/2026).

**Quando gira** lo decide `cadence.reason_to_reconsider`: al primo avvio,
quando cambia l'obiettivo, quando compare qualcosa di nuovo, e alla cadenza di
riconsiderazione. Qui dentro non c'e' nessuna delle quattro domande -- questo
modulo sa fare un giro, non sa quando farlo.
"""
from __future__ import annotations

import json
import logging
import re

from ..home_space.briefing import digest_visible_entity_ids
from .scope import OBSERVER

logger = logging.getLogger(__name__)

#: Quanto puo' essere lunga la risposta. Su 381 entita' il modello scrive una
#: riga di giudizio ciascuna -- identificatore, dentro/fuori, motivo -- e a
#: ~80 caratteri di media fa ≈30 KB, cioe' ≈8.000 token. Il tetto sta sopra con
#: margine: una risposta troncata a meta' non e' un giudizio parziale, e' un
#: JSON rotto che si butta intero.
MAX_ANSWER_TOKENS = 16000

#: Come si chiama, nella coda del ragionamento, un turno dell'osservatore.
#: Le altre due specie sono `chat` (`api/handlers_chat.py`) e `promessa`
#: (`keeper/exchange.py`), e come loro il nome vive **dove il turno nasce**:
#: chi lo serve -- `agent/runner.reason` -- dichiara per conto suo quali
#: specie sa ragionare, che e' un'affermazione sua e non una copia di questa.
SCOPE_TURN_KIND = "scope"

SYSTEM = """Sei l'osservatore di HIRIS, un sistema che guarda una casa domotica.

Il tuo mestiere e' UNO: decidere, entita' per entita', se quello che fa merita
di essere registrato rispetto all'obiettivo che ti viene dato -- e scrivere
PERCHE'.

Quello che decidi ha due conseguenze vere, e nessuna delle due e' teorica:
- cio' che lasci DENTRO viene registrato a ogni cambio di stato, e costa spazio
  e attenzione;
- cio' che lasci FUORI **non viene registrato affatto**, e fra un mese non
  esistera': nessuno potra' rispondere a una domanda su quel periodo. Potrai
  ricrederti, ma solo finche' Home Assistant ricorda -- pochi giorni.

Quindi non essere generoso e non essere avaro: chiediti, per ognuna, se la sua
storia servirebbe a capire come la casa risponde all'obiettivo.

Il motivo che scrivi lo legge il proprietario in una pagina. Scrivilo in
italiano, in una riga, concreto: «scalda la camera, e il riscaldamento e' la
voce piu' pesante» va bene; «utile» no, «non rilevante» nemmeno."""


def _area_names(home_space: dict) -> dict[str, str]:
    return {a["id"]: a.get("nome") for a in home_space.get("aree", []) if a.get("id")}


def house_lines(home_space: dict) -> list[str]:
    """Una riga per entita', **solo quelle che competono all'osservatore**.

    Ogni riga porta cio' che serve a giudicare e nient'altro: identificatore,
    nome, classe dichiarata da Home Assistant, unita', area, e il
    `translation_key`. Quest'ultimo e' cio' che l'**integrazione dichiara di
    se'** -- `energy_today`, non «Potenza» da indovinare -- ed e' la ragione per
    cui il riconoscimento non e' mai stato il problema di questo prodotto.

    Cio' che NON c'e' e' altrettanto deliberato: `unique_id`,
    `config_entry_id`, `dispositivo_id`, `piattaforma` sono identificatori
    opachi che non aiutano nessun giudizio e costerebbero token su 381 righe.

    L'area si mostra col **nome**: un `area_id` grezzo in mezzo a un prompt in
    italiano e' rumore, e un'area cancellata non deve far comparire una stringa
    che sembra un luogo.
    """
    visible = digest_visible_entity_ids(home_space)
    areas = _area_names(home_space)
    lines = []
    for entity in home_space.get("entita", []):
        if entity.get("id") not in visible:
            continue
        parts = [entity["id"]]
        for value in (entity.get("nome"), entity.get("classe"), entity.get("unita"),
                      areas.get(entity.get("area_id")), entity.get("translation_key")):
            if value:
                parts.append(str(value))
        lines.append(" · ".join(parts))
    return lines


#: **Il contratto di risposta, e vive una volta sola.** Le due porte lo
#: mettono in due posti diversi -- la catena in coda alla domanda, il ponte
#: come istruzione di chiusura del turno (`agent/prompts.build_chat_messages`,
#: dove l'ultima riga del messaggio e' quella che il modello segue) -- ma il
#: TESTO e' lo stesso, e due copie divergerebbero alla prima correzione fatta
#: da una parte sola.
#:
#: **Il motivo si chiede esplicitamente**, e non e' una cortesia: l'archivio
#: rifiuta una decisione senza ragione (`store.decide_scope`), quindi un
#: contratto che non lo chiedesse si farebbe buttare meta' delle risposte al
#: confine senza che nessuno capisca perche'.
ANSWER_CONTRACT = (
    "Rispondi con un SOLO array JSON, un oggetto per entita':\n"
    '  {"id": "<identificatore>", "dentro": true|false, "motivo": "<una riga in italiano>"}\n'
    "Nessun testo fuori dall'array. Un'entita' su cui davvero non sai "
    "decidere: omettila, invece di inventarti una ragione."
)


def build_question(objective: str, lines: list[str]) -> str:
    """La domanda intera: l'obiettivo, la casa, e il contratto di risposta.

    E' la forma che serve alla **catena**, dove tutto viaggia in un messaggio
    solo. Il ponte usa gli stessi due pezzi montati diversamente (vedi
    `bridge_turn`): la domanda in cronologia, il contratto come istruzione di
    chiusura.
    """
    return build_house_question(objective, lines) + "\n" + ANSWER_CONTRACT


def build_house_question(objective: str, lines: list[str]) -> str:
    """L'obiettivo e la casa, **senza** il contratto di risposta."""
    return (
        f"L'obiettivo di questa casa e':\n\n  {objective}\n\n"
        f"Queste sono le {len(lines)} entita' che ti competono. Ogni riga e':\n"
        "identificatore · nome · classe · unita' · area · chiave di traduzione\n"
        "(i campi che mancano sono assenti, non vuoti).\n\n"
        + "\n".join(lines)
        + "\n"
    )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def read_decisions(answer: str) -> tuple[list[dict], str | None]:
    """Le decisioni lette dalla risposta, e la ragione per cui NON si sono
    lette se non si e' potuto.

    **`[]` e un guasto sono due cose diverse.** Un array vuoto afferma «ho
    guardato la casa e non c'e' niente da osservare»; una risposta illeggibile
    non afferma niente, e appiattire la seconda sulla prima e' la bugia che
    questo prodotto rifiuta ovunque.

    **La staccionata si tollera.** I modelli incorniciano il JSON in ```` ```json ````
    anche quando si chiede di non farlo: buttare il giro per un dettaglio di
    forma costerebbe ≈11.500 token per niente.

    **Una voce storta si salta, le altre restano.** 380 giudizi buoni non si
    perdono per uno malformato -- e la voce saltata resta NON decisa, quindi
    l'impronta la ripresentera' al giro dopo: si ripara da se'.
    """
    text = (answer or "").strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError) as error:
        return [], f"la risposta non e' un JSON leggibile ({type(error).__name__})"
    if not isinstance(parsed, list):
        return [], "la risposta non e' un elenco di decisioni"
    decisions = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("id")
        if not isinstance(entity_id, str) or not entity_id:
            continue
        decisions.append({"id": entity_id,
                          "dentro": bool(item.get("dentro")),
                          "motivo": item.get("motivo")})
    return decisions, None


def bridge_turn(store, home_space: dict) -> dict:
    """Il turno da accodare al ponte: **la stessa domanda, per un'altra porta**.

    Il ponte gira altrove e non ha gli archivi: cio' che non entra nel job non
    esiste per lui (vedi `keeper/exchange._accoda_al_ponte`, che fa lo stesso
    per una promessa). Le due chiavi sono quelle che il turno del ponte legge
    davvero -- `agent/runner._reason_chat` -> `prompts.build_chat_messages`.

    **La domanda non si ricompone qui.** Si chiamano `house_lines` e
    `build_house_question`, le stesse che il giro sincrono usa dentro
    `build_question`: due composizioni della stessa domanda sarebbero due
    verita' libere di divergere, e la prima volta che qualcuno aggiunge un
    campo alla riga della casa da una parte sola il ponte e la catena
    giudicherebbero case diverse senza che nessuna pagina lo dica
    (fondamenta 2).
    """
    return {
        "history": [{"role": "user",
                     "content": build_house_question(store.objective()["testo"],
                                                     house_lines(home_space))}],
        "system_prompt": SYSTEM,
        # **Senza questa chiave il ponte gli impone il contrario.** L'istruzione
        # che chiude ogni turno di chat dice «usa testo semplice: niente
        # blocchi di codice o JSON» (`agent/prompts._CHAT_INSTRUCTION`), e
        # l'osservatore chiede esattamente un array JSON: la risposta sarebbe
        # tornata in prosa e `read_decisions` l'avrebbe dichiarata illeggibile
        # -- lo stesso esito del guasto che questa fetta ripara, per un'altra
        # causa. Trovato leggendo il codice l'11/09/2026, prima di rilasciare.
        "istruzione": ANSWER_CONTRACT,
    }


def apply_answer(store, home_space: dict, answer: str, *, reason: str,
                 window_s: float | None = None, cadence_s: float | None = None,
                 now: float | None = None) -> dict:
    """Cosa si fa di una risposta, **da qualunque porta sia arrivata**.

    E' la seconda meta' del giro, separata dalla prima perche' le due meta'
    non avvengono piu' sempre insieme: sulla catena la risposta torna dentro
    la stessa chiamata, sul ponte torna **minuti dopo, da un altro processo**,
    e il giro che la raccoglie e' un altro. Senza questa separazione la
    scrittura delle decisioni esisterebbe in due copie, e la seconda sarebbe
    rimasta indietro alla prima correzione fatta di qua.

    **Un giro fallito non si annota come fatto.** Annotarlo farebbe aspettare
    la cadenza intera -- 84 ore sulla casa vera -- prima di riprovare, su una
    casa di cui non si e' deciso niente.

    **Si accetta solo cio' che era nella domanda.** Un modello puo' inventare
    un identificatore, e un'entita' inventata nello scope sarebbe una riga che
    nessun evento potra' mai accendere e che la pagina mostrerebbe come
    osservata.
    """
    lines = house_lines(home_space)
    decisions, failure = read_decisions(answer)
    if failure is not None:
        logger.warning("osservatore: %s", failure)
        return {"errore": failure}

    known = {line.split(" · ", 1)[0] for line in lines}
    decided = refused = ignored = 0
    for decision in decisions:
        if decision["id"] not in known:
            ignored += 1
            continue
        if store.decide_scope(decision["id"], inside=decision["dentro"],
                              reason=decision["motivo"] or "", author=OBSERVER,
                              when_ts=now):
            decided += 1
        else:
            refused += 1

    store.record_reconsideration(when_ts=now, window_s=window_s,
                                 cadence_s=cadence_s, reason=reason)
    return {"decise": decided, "rifiutate": refused, "ignorate": ignored,
            "candidate": len(lines)}


async def reconsider(runner, store, home_space: dict, *, reason: str,
                     window_s: float | None = None, cadence_s: float | None = None,
                     model: str = "auto", now: float | None = None) -> dict:
    """Un giro intero **sulla catena**: guarda la casa, chiede, e consegna la
    risposta ad `apply_answer`.

    Torna il resoconto del giro -- `{"decise", "rifiutate", "ignorate"}` -- o
    `{"errore": ...}` se non si e' potuto fare.

    **Questa e' la porta della catena, non l'unica porta.** Chi decide fra le
    due e' `steering.who_answers`, dalla stessa funzione che lo decide per la
    chat e per le promesse; quando risponde «ponte», il giro passa da
    `bridge_turn` e questa funzione non viene chiamata affatto.
    """
    lines = house_lines(home_space)
    objective = store.objective()["testo"]
    question = build_question(objective, lines)
    try:
        # `user_message=` per nome e non posizionale: `LLMRouter.chat` --
        # il runner vero, quello con la catena di ripiego -- prende `**kwargs`
        # e basta, e un posizionale ci morirebbe sopra al primo giro in
        # produzione senza che nessuna finta lo veda.
        answer = await runner.chat(user_message=question, system_prompt=SYSTEM,
                                   model=model, agent_type="observer",
                                   max_tokens=MAX_ANSWER_TOKENS)
    except Exception as error:
        logger.warning("osservatore: il giro non e' partito (%s: %s)",
                       type(error).__name__, error)
        return {"errore": f"il modello non ha risposto: {type(error).__name__}"}

    return apply_answer(store, home_space, answer, reason=reason,
                        window_s=window_s, cadence_s=cadence_s, now=now)
