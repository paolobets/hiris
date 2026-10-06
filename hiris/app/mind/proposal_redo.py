"""«Rifalla»: un turno del **proponente** su una proposta da fare a mano
(piano degli attori, strato 4, Task 4.4; D16).

Fino al 06/10/2026 il «Rifalla» aveva un turno suo, dentro la rotta
(`api/handlers_proposals.py`): una domanda scritta li', un lettore della
risposta suo, contato come turno di chat e **sempre sulla catena**, anche su
una casa che gira sul Piano Max. Adesso e' il proponente, con i suoi strumenti
e il suo contratto, dalla partenza unica (`steering.start`): sul ponte si
accoda e la pagina interroga, sulla catena risponde subito.

**Tre esiti, quelli del proponente** (`proposer_turn.OUTCOMES`):
- **a mano**: il filo guadagna un giro e la proposta cambia frase;
- **costruita**: nasce una proposta costruibile, e quella a mano si chiude
  `superata` (D24-1);
- **niente**: la proposta resta com'era, e il giro porta il perche'.

**Lo stato «in rifacimento» vive nella coda** (fondamenta 2): il turno porta
nella sveglia l'id della proposta e la richiesta, e `state` lo rilegge da li'.
Nessuna colonna lo ricopia, e un riavvio non lo perde.

Le scelte del proprietario del 06/10/2026 (proposta del Task 4.4, «tutto
consigliato»): una proposta decisa mentre il rifacimento e' in volo scarta in
silenzio la risposta che arriva dopo; sul ponte il turno ha la precedenza
della chat; alla scadenza si dice, e non si ripiega a consumo.
"""
from __future__ import annotations

import logging
import secrets
import time

from ..reasoning.queue import PRIORITY_CHAT
from ..steering import (
    PROPOSER_SPECIES,
    SPECIES,
    chain_answer,
    chain_turn,
    enqueue_turn,
    start,
)
from . import proposer_turn

logger = logging.getLogger(__name__)

#: La chiave della sveglia che fa di un turno del proponente un «Rifalla»: il
#: suo valore e' l'id della proposta. Il giro orario porta `giorno`
#: (`proposer_round.ROUND_KEY`), e ognuno legge solo i suoi.
WAKE_KEY = "proposta"

#: Gli stati di un rifacimento non ancora scritto nel filo, come li legge la
#: pagina (`state`).
RUNNING = "in_corso"
EXPIRED = "scaduto"
FAILED = "fallito"
UNREADABLE = "illeggibile"

#: Cosa e' successo a un rifacimento finito: uno degli esiti del proponente,
#: oppure la risposta scartata perche' la proposta non era piu' in attesa.
DISCARDED = "scartato"

#: I rifacimenti in corso sulla catena, per id di proposta. Sulla catena il
#: turno non passa dalla coda, e due pressioni ravvicinate pagherebbero due
#: turni: questo insieme vive solo finche' la richiesta e' aperta.
CHAIN_IN_FLIGHT = "rifalla_in_volo"

#: La regola del rifacimento, davanti al contratto degli esiti. Era la meta'
#: di `_REDO_SYSTEM`; l'altra meta' -- chi sei, cosa sai fare -- e' il
#: `SYSTEM` del proponente.
REDO_RULE = """Chi amministra la casa ti chiede di rifare una tua proposta da
fare a mano, in un altro modo. Non rifare la stessa cosa: cambia strada,
tenendo la domanda a cui la proposta risponde. Puoi rispondere con un'altra
cosa da fare a mano, o con un oggetto che Home Assistant sa tenere
(`propose`). Se con questa richiesta non c'e' niente di sensato da proporre,
l'esito e' «niente», col perche': non inventare qualcosa che non sta in
piedi."""


class InFlight(Exception):
    """Un rifacimento e' gia' in corso su quella proposta."""


class NoModel(Exception):
    """Nessun modello a cui chiedere."""


class NoAnswer(Exception):
    """Il turno e' partito e nessun modello ha risposto."""


def observation_of(store, proposal: dict) -> dict | None:
    """L'osservazione a cui la proposta rispondeva, per impronta, dalle
    analisi che l'archivio tiene. `None` se non c'e' piu'."""
    from .analyst import observation_key

    for analysis in store.analyses():
        for row in analysis.get("osservazioni") or []:
            if isinstance(row, dict) and observation_key(row) == proposal["impronta"]:
                return row
    return None


def round_lines(rounds) -> list[str]:
    """Il filo dei «Rifalla» come lo legge il proponente: la richiesta e, per
    esito, la forma scartata o il perche' di un giro che non ha proposto
    niente. Lo leggono questa domanda e quella di «Rendila automatica»
    (`automate_turn.build_question`): un giro «niente» non ha una forma
    scartata, e chiederla scriverebbe «None» (giro di revisione 68, G68-2)."""
    lines: list[str] = []
    for turn in rounds:
        lines.append(f"  la richiesta di allora: {turn.get('richiesta')}")
        if turn.get("esito") == proposer_turn.NOTHING:
            lines.append(f"  allora non avevi proposto niente: {turn.get('perche')}")
        elif turn.get("scartata") is not None:
            lines.append(f"  gia' scartata prima: {turn.get('scartata')}")
    return lines


def build_question(proposal: dict, request: str, observation: dict | None, *,
                   presence=None) -> str:
    """La domanda del rifacimento: l'osservazione col numero 0, la proposta di
    adesso, il filo dei giri e la richiesta. **Senza la forma scartata il
    modello potrebbe riproporla**, ed e' il motivo per cui il filo si accoda
    (spec dell'attuatore, §7)."""
    lines = [REDO_RULE, "", "L'osservazione a cui la proposta risponde:"]
    if observation is not None:
        lines.extend(proposer_turn.observation_lines(0, observation))
    else:
        lines.append("  [0] non e' piu' fra le analisi: hai la proposta e la "
                     f"prova su cui si reggeva ({proposal.get('prova')})")
    lines += ["", "La proposta di adesso, che non vuole cosi':",
              f"  {proposal['testo']}",
              f"  (il perche' che avevi scritto: {proposal['perche']})"]
    lines += round_lines(proposal.get("giri") or [])
    lines += ["", "Cosa ti chiede di cambiare:", f"  {request}", "",
              proposer_turn.ANSWER_CONTRACT]
    question = "\n".join(lines)
    return presence.mask(question) if presence is not None else question


def _presence(app):
    from ..home_space.house import House
    from ..home_space.privacy import PresenceMask

    home_space = app.get("home_space_store")
    return (PresenceMask(House.read(home_space, app.get("entity_cache")))
            if home_space is not None else None)


def _built_in(app, exchange: str | None) -> frozenset[str]:
    constructions = app.get("constructions")
    if constructions is None:
        return frozenset()
    return constructions.proposed_in(exchange, actor=PROPOSER_SPECIES)


async def redo(app, store, proposal: dict, request: str, *,
               subject: dict | None = None) -> dict:
    """Fa partire il rifacimento. Torna `{"strada", "ripiego", "esito"}`:
    sul ponte `esito` e' `None` (la risposta arriva in differita, la scrive
    `deliver`), sulla catena e' cio' che `settle` ha scritto.

    Solleva `InFlight`, `NoModel` o `NoAnswer`."""
    from . import automate_turn

    ident = proposal["id"]
    # «Rendila automatica» sulla stessa proposta (giro di revisione 68,
    # G68-2): due turni per una domanda darebbero due costruzioni, o un
    # rifacimento scartato da un'automazione arrivata prima.
    if redoing(app, proposal) or automate_turn.preparing(app) == ident:
        raise InFlight(ident)
    in_flight = app.setdefault(CHAIN_IN_FLIGHT, set())
    route, downgrade, runner = start(app, PROPOSER_SPECIES)
    observation = observation_of(store, proposal)
    if route == "ponte":
        job = {"history": [{"role": "user", "content": build_question(
                   proposal, request, observation, presence=_presence(app))}],
               "system_prompt": proposer_turn.SYSTEM,
               "istruzione": proposer_turn.ANSWER_CONTRACT}
        _job_id, deadline_min = enqueue_turn(
            app, PROPOSER_SPECIES, {WAKE_KEY: ident, "richiesta": request}, job,
            priority=PRIORITY_CHAT)
        logger.info("rifalla: turno accodato al piano per la proposta %s "
                    "(scadenza %d min)", ident, deadline_min)
        return {"strada": route, "ripiego": downgrade, "esito": None}
    if runner is None:
        raise NoModel(ident)
    in_flight.add(ident)
    try:
        declared = SPECIES[PROPOSER_SPECIES]
        exchange = secrets.token_urlsafe(9)
        dispatcher = await declared.guard(app, exchange)
        presence = getattr(dispatcher, "presence", None)
        answer, turn = await chain_turn(
            runner, PROPOSER_SPECIES, usage=app.get("usage"), soggetto=subject,
            max_tokens=proposer_turn.MAX_ANSWER_TOKENS,
            user_message=build_question(proposal, request, observation,
                                        presence=presence),
            system_prompt=proposer_turn.SYSTEM,
            tools=declared.catalog_for_turn(), dispatcher=dispatcher)
        # La frase del router quando nessun backend risponde non e' una
        # proposta illeggibile: e' il modello che non ha risposto (G29-1).
        if not turn.answered:
            raise NoAnswer(ident)
        occurrence = proposer_turn.apply_outcomes(
            [observation or {}], chain_answer(answer, turn),
            built=_built_in(app, exchange), truncated=turn.truncated,
            presence=presence)
        outcome = settle(app, store, ident, request, occurrence, turn=exchange)
    finally:
        in_flight.discard(ident)
    return {"strada": route, "ripiego": downgrade, "esito": outcome}


def deliver(app, job: dict, decision: dict) -> str | None:
    """La risposta del piano a un «Rifalla», dalla consegna del ponte
    (`reasoning/consegna.py`). Torna l'esito, o `None` se il turno non e' un
    rifacimento."""
    from ..reasoning.queue import turn_answer

    wake = job.get("wake") or {}
    ident = wake.get(WAKE_KEY)
    store = app.get("observations")
    if not ident or store is None:
        return None
    occurrence = proposer_turn.apply_outcomes(
        [{}], turn_answer({**job, "decision": decision}),
        built=_built_in(app, decision.get("exchange_id")), presence=_presence(app))
    return settle(app, store, ident, wake.get("richiesta") or "", occurrence,
                  turn=job["job_id"])


def settle(app, store, ident: str, request: str, occurrence: dict, *,
           turn: str) -> str:
    """Scrive l'esito del rifacimento nel filo della proposta, e torna la sua
    parola. **Una proposta che non e' piu' in attesa scarta la risposta**, in
    silenzio (scelta del proprietario del 06/10/2026): chi l'ha rifiutata
    mentre il turno era in volo ha gia' deciso."""
    row = next((p for p in store.proposals() if p["id"] == ident), None)
    if row is None or row["stato"] != store.PROPOSAL_PENDING:
        logger.info("rifalla: la proposta %s non e' piu' in attesa, la risposta "
                    "si scarta", ident)
        return DISCARDED
    if not occurrence["esiti"]:
        logger.warning("rifalla: risposta illeggibile per la proposta %s -- %s",
                       ident, " · ".join(occurrence["problemi"]))
        return UNREADABLE
    outcome = occurrence["esiti"][0]
    kind = outcome["esito"]
    if kind == proposer_turn.BY_HAND:
        store.add_proposal_round(ident, request=request, outcome=kind, turn=turn,
                                 text=outcome["testo"], why=outcome["perche"],
                                 now_ts=time.time())
    elif kind == proposer_turn.NOTHING:
        store.add_proposal_round(ident, request=request, outcome=kind, turn=turn,
                                 why=outcome["perche"], now_ts=time.time())
    else:
        built = outcome["proposta_id"]
        constructions = app.get("constructions")
        if constructions is not None:
            constructions.answers(built, actor=PROPOSER_SPECIES,
                                  fingerprint=row["impronta"], prova=row["prova"])
        store.add_proposal_round(ident, request=request, outcome=kind, turn=turn,
                                 built=built, now_ts=time.time())
        store.close_proposal(ident, "superata", why=proposer_turn.SUPERSEDED_WHY)
    return kind


def redoing(app, proposal: dict) -> bool:
    """Se un «Rifalla» su questa proposta e' in corso, sul ponte (`state`) o
    sulla catena (`CHAIN_IN_FLIGHT`). Lo leggono `redo` e il rifiuto di
    «Rendila automatica» (`automate_turn.refusal`), che non partono sopra un
    rifacimento (giro di revisione 68, G68-2)."""
    now = state(app, proposal)
    return ((now is not None and now["stato"] == RUNNING)
            or proposal["id"] in app.get(CHAIN_IN_FLIGHT, ()))


def state(app, proposal: dict) -> dict | None:
    """Il rifacimento sul ponte non ancora scritto nel filo, o `None`.

    `{"stato", "richiesta", "avvio_ts", "scadenza_ts"}`, con lo stato fra
    `RUNNING`, `EXPIRED`, `FAILED` e `UNREADABLE`. Lo dice la coda: e' l'ultimo
    turno con la sveglia di questa proposta, finche' nessun giro del filo
    porta il suo id."""
    from ..reasoning.queue import turn_answer

    queue, store = app.get("reasoning_queue"), app.get("observations")
    if queue is None or store is None \
            or proposal.get("stato") != store.PROPOSAL_PENDING:
        return None
    job = queue.latest(proposer_turn.PROPOSAL_TURN_KIND, wake_key=WAKE_KEY,
                       wake_value=proposal["id"])
    if job is None or any(g.get("turno") == job["job_id"]
                          for g in proposal.get("giri") or []):
        return None
    status = job.get("status")
    if status in ("pending", "claimed"):
        phase = RUNNING if job["deadline_ts"] > time.time() else EXPIRED
    elif status == "expired":
        phase = EXPIRED
    elif status == "failed" or not str(turn_answer(job) or "").strip():
        # Deciso ma vuoto: il piano non ha risposto, per chi preme il bottone
        # e' un fallimento come gli altri.
        phase = FAILED
    else:
        phase = UNREADABLE
    return {"stato": phase, "richiesta": (job.get("wake") or {}).get("richiesta"),
            "avvio_ts": job.get("created_ts"), "scadenza_ts": job.get("deadline_ts")}
