"""**«Rendila automatica»**: da una proposta fatta a mano, un'automazione
(attori, strato 4, Task 4.5; D15 del piano degli strati 3-4).

Chi amministra la casa guarda una proposta da fare a mano e dice: «questa
voglio che succeda da sola». Per la Legge I uno schema approvato per sempre e'
un'automazione di Home Assistant, non un permesso di HIRIS: il comando apre un
turno del proponente che la compone con `propose`, e ne esce una proposta
costruibile normale, con anteprima e conferma. **Il comando non crea niente e
non esegue niente.**

Le tre scelte del proprietario (06/10/2026, schede del thread):

- il bottone si chiama «Rendila automatica»: «sempre si'» suonava come un
  permesso dato a HIRIS, cioe' il perimetro degli agenti che non esiste;
- **un'automazione che agisce su serrature o allarme si rifiuta dentro il
  turno**: agirebbe senza chiedere, e quelle chiedono sempre (decisione del
  03/10). Il livello lo calcola l'officina, che qui rifiuta `alto` invece di
  archiviarlo (`Workshop.propose`, `refuse_high`). Il comando non esiste
  nemmeno su una proposta che e' gia' `alto`;
- quando l'automazione nasce, la proposta a mano **si chiude col legame**:
  l'id della costruzione accanto, l'esito «automatizzata».

**Una alla volta.** Il turno in volo lo dice la coda del ponte
(`steering.turn_in_flight`) o, sulla catena, la chiave `IN_FLIGHT` dell'app:
mai un secondo archivio dello stesso fatto.

La consegna: sulla catena la fa il compito qui sotto quando il turno finisce;
sul ponte la fa `reasoning/consegna.py`, che chiama `settle` con la risposta.
"""
from __future__ import annotations

import logging
import secrets
import time

from ..action.construction.stakes import HIGH
from ..background import spawn
from ..steering import (
    AUTOMATE_SPECIES,
    PROPOSER_SPECIES,
    SPECIES,
    chain_answer,
    chain_turn,
    enqueue_turn,
    read_json,
    refused_tool,
    start,
    turn_in_flight,
)
from .proposal_redo import round_lines
from .proposer_turn import PROPOSE, ProposerDispatcher
from .proposer_turn import guard as proposer_guard

logger = logging.getLogger(__name__)

#: Il nome del job sulla coda del ponte: una vista sulla dichiarazione.
AUTOMATE_TURN_KIND = SPECIES[AUTOMATE_SPECIES].kind

#: La chiave di `app` che dice quale proposta ha un turno sulla catena in
#: corso. Sul ponte lo sa la coda; sulla catena il turno vive in questo
#: processo, e muore con lui: un riavvio lo perde insieme alla chiave.
IN_FLIGHT = "automazione_in_volo"

#: Il tetto della risposta, dichiarato: lo stesso del proponente, per la
#: stessa ragione e con la stessa avvertenza (non misurato: lo sceglie la
#: misura dal vivo della chiusura dello strato 4, Task 4.8).
MAX_ANSWER_TOKENS = 4096

#: Cosa si puo' proporre in questo turno: un'automazione nuova. Uno script o
#: una scena non succedono da soli, e modificare un oggetto che c'e' gia' non
#: e' cio' che chi amministra ha chiesto.
OPERATION = "crea"
DOMAIN = "automation"

SYSTEM = """Sei il proponente di HIRIS, un sistema che guarda una casa domotica.

Chi amministra la casa ha davanti una tua proposta da fare a mano, e ti dice:
«questa voglio che succeda da sola». Il tuo mestiere e' UNO: comporre
l'automazione di Home Assistant che la fa, chiamando `propose` con
`gesto: "crea"` e `dominio: "automation"`.

`propose` non scrive niente: l'officina valida l'automazione contro questa
casa e ti risponde con l'id della proposta, oppure ti dice perche' non va. Se
non va, correggi e richiama. Una proposta sola: quando `propose` ti ha dato un
id, hai finito.

Hai i lettori (search, related, history, mind) per guardare la casa prima di
comporre: un'automazione su un'entita' che non hai visto e' un'ipotesi.

Se non si puo' fare -- la cosa la deve fare una persona, o la casa non ha
cio' che serve, o l'officina ti dice che tocca qualcosa che chiede sempre a
chi amministra -- non inventare: dillo."""

ANSWER_CONTRACT = """Quando hai finito rispondi SOLO con un oggetto JSON:

{"proposta_id": "<l'id che `propose` ti ha dato>"}

oppure, se non si puo' rendere automatica:

{"perche": "<perche' no, in una frase, per chi amministra la casa>"}"""


class AutomateDispatcher(ProposerDispatcher):
    """Il guardiano del turno: quello del proponente, con `propose` stretto a
    un'automazione nuova. Il resto -- i lettori, la maschera dei nomi, la
    firma del proponente -- e' il suo."""

    async def dispatch(self, name: str, arguments: dict | None) -> dict:
        if name == PROPOSE:
            asked = arguments or {}
            if asked.get("gesto") != OPERATION or asked.get("dominio") != DOMAIN:
                return refused_tool(
                    name, doing="mentre rendo automatica una proposta",
                    instead=(f"Qui si propone solo un'automazione nuova: "
                             f"`gesto: \"{OPERATION}\"`, `dominio: \"{DOMAIN}\"`."))
        return await super().dispatch(name, arguments)


async def guard(app, exchange: str | None = None) -> AutomateDispatcher:
    """Il `dispatcher` del turno, sulla catena e sul ponte: il guardiano qui
    sopra, e l'officina che rifiuta il livello `alto`."""
    return await proposer_guard(app, exchange, kind=AutomateDispatcher,
                                refuse_high=True, species=AUTOMATE_SPECIES)


def preparing(app) -> str | None:
    """L'id della proposta che ha un turno in corso, o `None`."""
    on_chain = app.get(IN_FLIGHT)
    if on_chain:
        return on_chain
    if not turn_in_flight(app, AUTOMATE_TURN_KIND):
        return None
    queue = app.get("reasoning_queue")
    turn = queue.latest(AUTOMATE_TURN_KIND) if queue is not None else None
    return ((turn or {}).get("wake") or {}).get("proposta")


#: Il solo rifiuto che dice «il comando non esiste» (403, D15): gli altri
#: cambiano col tempo (409). La rotta sceglie il codice da questo testo, non
#: dal livello, che su una proposta gia' decisa direbbe 403 con le parole del
#: 409 (giro 67, N67-3).
HIGH_REFUSAL = "serrature e allarme chiedono sempre a te: questa non diventa automatica."


def refusal(row: dict, *, pending: str, in_flight: str | None,
            redoing: bool = False) -> str | None:
    """Perche' questa proposta non si puo' rendere automatica adesso, o
    `None`. **Una regola sola** per la rotta, che rifiuta, e per la pagina,
    che non mostra il bottone (`handlers_constructions._both_queues`).
    `redoing`: un «Rifalla» sulla stessa proposta e' in corso
    (`proposal_redo.redoing`, giro di revisione 68, G68-2)."""
    if row.get("stato") != pending:
        return "quella proposta non è più in attesa: qualcuno l’ha già decisa."
    if row.get("livello") == HIGH:
        return HIGH_REFUSAL
    if row.get("non_automatizzabile"):
        return "HIRIS ha già provato: " + row["non_automatizzabile"]
    if redoing:
        return "HIRIS la sta rifacendo: aspetta la forma nuova."
    if in_flight == row.get("id"):
        return "HIRIS la sta già preparando."
    if in_flight is not None:
        return "HIRIS sta preparando un’altra automazione: riprova quando ha finito."
    return None


def build_question(row: dict, *, presence=None) -> str:
    """La domanda: la proposta, il suo perche', la prova su cui si regge e il
    filo dei «Rifalla», perche' il modello non ricomponga una forma scartata."""
    lines = ["La proposta da fare a mano che chi amministra la casa vuole automatica:",
             f"  {row.get('testo')}",
             f"  perche': {row.get('perche')}"]
    prova = row.get("prova") or {}
    if prova:
        lines.append(f"  la prova dell'osservazione da cui e' nata: {prova}")
    lines += round_lines(row.get("giri") or [])
    lines += ["", ANSWER_CONTRACT]
    question = "\n".join(lines)
    return presence.mask(question) if presence is not None else question


def bridge_turn(row: dict, *, presence=None) -> dict:
    """Il turno da accodare al ponte: la stessa forma degli altri mestieri."""
    return {"history": [{"role": "user", "content": build_question(row, presence=presence)}],
            "system_prompt": SYSTEM,
            "istruzione": ANSWER_CONTRACT}


def begin(app, row: dict) -> str | None:
    """Fa partire il turno, sul ponte o sulla catena. Torna `None` se e'
    partito, altrimenti perche' no. **Non aspetta la risposta**: sul ponte
    arriva minuti dopo, e la pagina interroga."""
    route, _downgrade, runner = start(app, AUTOMATE_SPECIES)
    if route == "ponte":
        from ..home_space.house import House
        from ..home_space.privacy import PresenceMask

        home_space = app.get("home_space_store")
        presence = (PresenceMask(House.read(home_space, app.get("entity_cache")))
                    if home_space is not None else None)
        enqueue_turn(app, AUTOMATE_SPECIES, {"proposta": row["id"]},
                     bridge_turn(row, presence=presence))
        return None
    if runner is None:
        return "nessun modello collegato: non posso prepararla adesso."
    app[IN_FLIGHT] = row["id"]
    # Un compito senza padrone: `spawn` gli tiene il riferimento forte.
    spawn(_chain(app, row, runner), name="automazione")
    return None


async def _chain(app, row: dict, runner) -> None:
    """Il turno sulla catena, fino alla consegna. Non solleva: e' un compito
    senza nessuno che lo aspetti."""
    try:
        declared = SPECIES[AUTOMATE_SPECIES]
        exchange = secrets.token_urlsafe(9)
        dispatcher = await declared.guard(app, exchange)
        presence = getattr(dispatcher, "presence", None)
        answer, turn = await chain_turn(
            runner, AUTOMATE_SPECIES, usage=app.get("usage"),
            max_tokens=MAX_ANSWER_TOKENS,
            user_message=build_question(row, presence=presence),
            system_prompt=SYSTEM, tools=declared.catalog_for_turn(),
            dispatcher=dispatcher)
        settle(app, row["id"], exchange, chain_answer(answer, turn),
               truncated=turn.truncated, presence=presence)
    except Exception as error:
        logger.warning("automazione: turno fallito per %s (%s: %s)",
                       row.get("id"), type(error).__name__, error)
    finally:
        app[IN_FLIGHT] = None


def settle(app, ident: str, exchange: str | None, answer, *,
           truncated: bool = False, presence=None) -> str:
    """La consegna: chiude la proposta col legame, o scrive perche' no.

    **L'id lo dice l'archivio delle costruzioni**, non il modello: le
    proposte nate in quel turno, firmate dal proponente
    (`ConstructionStore.proposed_in`). Se il modello ne ha fatte due, il
    legame va alla piu' recente, e l'altra resta una proposta costruibile
    come le altre, da decidere.

    Un turno troncato, o senza risposta, **non scrive niente**: e' un guasto
    di passaggio, non un «non si puo'», e il comando torna disponibile.
    Torna l'esito, una parola sola.
    """
    store = app.get("observations")
    if store is None or not ident:
        return "senza_archivio"
    built = _built_in(app, exchange)
    if built is not None:
        if store.automate_proposal(ident, built):
            return "automatizzata"
        logger.info("automazione: %s non era piu' in attesa, la costruzione %s "
                    "resta da decidere da sola", ident, built)
        return "gia_decisa"
    data, reason = read_json(answer, shape=dict, what="un oggetto con il perche'",
                             truncated=truncated)
    why = data.get("perche") if isinstance(data, dict) else None
    if not isinstance(why, str) or not why.strip():
        logger.warning("automazione: il turno per %s e' finito senza un'automazione "
                       "e senza un perche' (%s)", ident,
                       reason or "nessun «perche'»")
        return "senza_esito"
    why = why.strip()
    if presence is not None:
        why = presence.unmask(why)
    store.refuse_automation(ident, why)
    return "non_automatizzabile"


def deliver(app, job: dict | None, decision: dict) -> str:
    """La consegna di un turno del ponte (`reasoning/consegna.py`): la
    proposta viene dalla sveglia, il turno e la risposta dalla decisione. La
    maschera dei nomi si rilegge dalla casa, come fa il proponente quando
    raccoglie (`proposer_round._collect`)."""
    from ..home_space.house import House
    from ..home_space.privacy import PresenceMask

    home_space = app.get("home_space_store")
    presence = (PresenceMask(House.read(home_space, app.get("entity_cache")))
                if home_space is not None else None)
    return settle(app, ((job or {}).get("wake") or {}).get("proposta") or "",
                  decision.get("exchange_id"), decision.get("reply"),
                  presence=presence)


def _built_in(app, exchange: str | None) -> str | None:
    """La proposta piu' recente nata nel turno, o `None`."""
    constructions = app.get("constructions")
    if constructions is None:
        return None
    ids = constructions.proposed_in(exchange, actor=PROPOSER_SPECIES)
    now = time.time()
    rows = [r for r in (constructions.read(i, now=now) for i in ids) if r is not None]
    if not rows:
        return None
    return max(rows, key=lambda r: r.get("creata_ts") or 0)["id"]
