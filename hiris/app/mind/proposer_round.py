"""Il giro del **proponente** (piano degli attori, strato 4, Task 4.2; D12).

Sostituisce il giro dell'attuatore, in pausa dal 01/10/2026 perche' partiva
senza strumenti di lettura. Vive fuori da `server.py` per la regola del
proprietario del 06/10/2026 («niente codice nuovo dentro server.py»): li'
resta solo la riga che lo mette nello schedulatore.

**Un'analisi, un giro del proponente** (la regola della spec §4 resta): si
aggancia allo stesso battito orario dell'analista e non fa niente finche' non
trova l'analisi di oggi con osservazioni aperte. Quando ogni osservazione ha
il suo esito, tace.

Non solleva mai: gira per sempre, e un giro andato storto non deve fermare lo
schedulatore.
"""
from __future__ import annotations

import logging
import secrets
import time

from ..action.construction.stakes import HIGH
from ..home_space import historian
from ..keeper.delivery import notify_admins
from ..reasoning.queue import turn_answer
from ..steering import (
    PROPOSER_SPECIES,
    SPECIES,
    chain_answer,
    chain_turn,
    declare_refused,
    enqueue_turn,
    refused_problems,
    start,
    too_soon_to_ask_again,
    turn_in_flight,
)
from . import proposer_turn
from .analyst import evidence_of, observation_key

logger = logging.getLogger(__name__)

#: La chiave di `app` che dice che un giro e' in corso. Lo schedulatore ha
#: mezz'ora di `misfire_grace_time`: due giri possono partire insieme dopo una
#: sosta dell'add-on, e senza questa guardia si pagherebbero due turni.
IN_FLIGHT = "proponente_in_volo"


async def proposer_round(app) -> dict | None:
    """Il giro: raccoglie la risposta del ponte, poi chiede per le
    osservazioni ancora aperte. Torna il resoconto, o `None` se non c'era da
    farlo."""
    store = app.get("observations")
    if store is None or app.get(IN_FLIGHT):
        return None
    app[IN_FLIGHT] = True
    try:
        # Prima di tutto gli avvisi che non sono arrivati: si ritentano a ogni
        # battito, anche nei giorni senza analisi (D14, «Ritenta»).
        await _alert_high_safely(app)
        today = historian.today(
            historian.house_timezone(app.get("home_space_store"))).isoformat()
        if store.analysis(today) is None:
            return None
        # **La risposta del ponte si raccoglie PRIMA di chiedere di nuovo**:
        # il ponte risponde minuti dopo, e senza questo passo il giro
        # accoderebbe una domanda a ogni battito e non ne leggerebbe nessuna.
        collected = await _collect(app, store, today)
        pending = _open(store, today)
        if not pending:
            return collected
        # Un turno in volo, o finito da meno di un'ora (`RETRY_HOLD_S`): si
        # aspetta, come l'analista e le ricette.
        if turn_in_flight(app, proposer_turn.PROPOSAL_TURN_KIND) \
                or too_soon_to_ask_again(app, proposer_turn.PROPOSAL_TURN_KIND):
            return collected
        refused = refused_problems(app.get("usage"), PROPOSER_SPECIES)
        route, _downgrade, runner = start(app, PROPOSER_SPECIES)
        if route == "ponte":
            return _enqueue(app, today, pending, refused)
        if runner is None:
            logger.info("proponente: nessun modello collegato, si riprova al "
                        "giro dopo")
            return None
        return await _chain(app, store, today, pending, refused, runner)
    except Exception as error:
        logger.warning("proponente: giro fallito (%s: %s) -- si riprova al "
                       "giro dopo", type(error).__name__, error)
        return None
    finally:
        app[IN_FLIGHT] = False


async def _chain(app, store, day: str, pending, refused, runner) -> dict:
    """Il turno sulla catena: gli strumenti e il guardiano dalla dichiarazione
    del mestiere, l'identita' del turno coniata qui (sul ponte la conia il
    runner)."""
    declared = SPECIES[PROPOSER_SPECIES]
    exchange = secrets.token_urlsafe(9)
    dispatcher = await declared.guard(app, exchange)
    presence = getattr(dispatcher, "presence", None)
    question = proposer_turn.build_question(pending, refused=refused,
                                            presence=presence)
    answer, turn = await chain_turn(
        runner, PROPOSER_SPECIES, usage=app.get("usage"),
        max_tokens=proposer_turn.MAX_ANSWER_TOKENS,
        user_message=question, system_prompt=proposer_turn.SYSTEM,
        tools=declared.catalog_for_turn(), dispatcher=dispatcher)
    occurrence = proposer_turn.apply_outcomes(
        pending, chain_answer(answer, turn), built=_built_in(app, exchange),
        truncated=turn.truncated, presence=presence)
    if occurrence["risposta"] and occurrence["problemi"] and not turn.truncated:
        declare_refused(app.get("usage"), turn.turn_id, occurrence["problemi"])
    _settle(store, day, occurrence)
    await _alert_high_safely(app)
    return occurrence


def _enqueue(app, day: str, pending, refused) -> dict | None:
    """Accoda al piano la domanda, e torna subito. **Nella sveglia vanno il
    giorno e le impronte, in ordine**: chi raccoglie minuti dopo deve
    rinumerare le STESSE osservazioni, anche se nel frattempo alcune hanno
    avuto un esito."""
    from ..home_space.house import House
    from ..home_space.privacy import PresenceMask

    home_space = app.get("home_space_store")
    presence = (PresenceMask(House.read(home_space, app.get("entity_cache")))
                if home_space is not None else None)
    job = proposer_turn.bridge_turn(pending, refused=refused, presence=presence)
    if job is None:
        return None
    wake = {"giorno": day, "impronte": [observation_key(o) for o in pending]}
    _job_id, deadline_min = enqueue_turn(app, PROPOSER_SPECIES, wake, job)
    logger.info("proponente: turno accodato al piano per %s (scadenza %d min)",
                day, deadline_min)
    return {"accodata": True, "giorno": day}


async def _collect(app, store, today: str) -> dict | None:
    """La risposta che il piano ha dato alla domanda del proponente.

    **Rileggere lo stesso turno non cambia niente**: un esito si scrive solo
    per un'osservazione ancora aperta, quindi la seconda lettura trova tutto
    gia' fatto e tace. I problemi si rivalidano a ogni lettura, finche' quel
    turno e' l'ultimo della sua specie.
    """
    queue = app.get("reasoning_queue")
    turn = queue.latest(proposer_turn.PROPOSAL_TURN_KIND) if queue else None
    if not turn or turn.get("status") != "decided":
        return None
    wake = turn.get("wake") or {}
    if wake.get("giorno") != today:
        return None
    analysis = store.analysis(today)
    by_key = {observation_key(o): o
              for o in (analysis or {}).get("osservazioni") or []
              if isinstance(o, dict)}
    pending = [by_key[k] for k in wake.get("impronte") or [] if k in by_key]
    reply = turn_answer(turn)
    if not pending or not str(reply).strip():
        return None
    from ..home_space.house import House
    from ..home_space.privacy import PresenceMask

    decision = turn.get("decision") or {}
    home_space = app.get("home_space_store")
    presence = (PresenceMask(House.read(home_space, app.get("entity_cache")))
                if home_space is not None else None)
    occurrence = proposer_turn.apply_outcomes(
        pending, reply, built=_built_in(app, decision.get("exchange_id")),
        presence=presence)
    if occurrence["problemi"]:
        declare_refused(app.get("usage"), decision.get("turn_id"), occurrence["problemi"])
    _settle(store, today, occurrence)
    await _alert_high_safely(app)
    return occurrence


def _open(store, day: str) -> list[dict]:
    """Le osservazioni di `day` ancora senza esito, contro le proposte da
    fare a mano di adesso."""
    waiting = {p["impronta"] for p in store.proposals(pending_only=True)}
    return proposer_turn.open_observations(store.analysis(day),
                                           store.decided_proposals(), waiting)


def _built_in(app, exchange: str | None) -> frozenset[str]:
    """Gli id delle proposte nate nel turno, dall'archivio delle costruzioni."""
    constructions = app.get("constructions")
    if constructions is None:
        return frozenset()
    return constructions.proposed_in(exchange, actor=PROPOSER_SPECIES)


def _settle(store, day: str, occurrence: dict) -> None:
    """Scrive gli esiti buoni: «da fare a mano» nell'archivio gemello con
    l'impronta e la prova; «costruita» e «niente» accanto all'osservazione,
    nell'analisi. Un esito per un'osservazione che ne ha gia' uno non si
    riscrive: e' cio' che rende innocua una seconda lettura dello stesso turno.
    """
    if occurrence["problemi"]:
        logger.warning("proponente: esiti rifiutati per %s -- %s",
                       day, " · ".join(occurrence["problemi"]))
    analysis = store.analysis(day)
    if analysis is None or not occurrence["esiti"]:
        return
    still_open = {observation_key(o) for o in _open(store, day)}
    beside = proposer_turn.outcomes_of(analysis)
    for outcome in occurrence["esiti"]:
        if outcome["impronta"] not in still_open:
            continue
        still_open.discard(outcome["impronta"])
        if outcome["esito"] == proposer_turn.BY_HAND:
            store.add_proposal(
                text=outcome["testo"], perche=outcome["perche"],
                fingerprint=outcome["impronta"],
                prova=evidence_of(outcome["osservazione"]),
                # Il livello di una proposta da fare a mano non lo impone
                # nessuno: una frase in prosa non porta i domini su cui il
                # codice imporrebbe `alto` (D13), e una cosa che fa una
                # persona non e' HIRIS che tocca la casa (D14 avvisa per
                # quelle).
                stakes=None, now_ts=time.time())
            continue
        beside.append({k: v for k, v in outcome.items() if k != "osservazione"})
    store.replace_analysis(day, {**analysis, proposer_turn.OUTCOMES_KEY: beside})


#: Il testo della push agli amministratori. Lo scrive il codice, non il
#: modello: il nome dell'oggetto e' l'unica parte che viene dalla proposta.
#: Non nomina i domini: quali sono `alto` lo dice `stakes.HIGH_STAKES_DOMAINS`,
#: e una frase che li ricopiasse mentirebbe il giorno in cui la lista cambia.
ALERT_TEXT = ("HIRIS ha una proposta di livello alto: «{name}». "
              "Decidi tu, nella pagina Proposte.")


async def _alert_high_safely(app) -> None:
    """`_alert_high` che non solleva: un guasto dell'avviso non toglie il
    turno al proponente (revisione, giro 58). Si ritenta al giro dopo."""
    try:
        await _alert_high(app)
    except Exception as error:
        logger.warning("proponente: avviso per le proposte alto non riuscito "
                       "(%s: %s) -- si ritenta al giro dopo",
                       type(error).__name__, error)


async def _alert_high(app) -> None:
    """L'avviso per una proposta `alto` (D14, approvata il 06/10/2026): una
    push agli amministratori, dal recapito delle promesse e dalla porta dei
    servizi (`keeper/delivery.notify_admins`). Le altre proposte vanno fra le
    Proposte e basta (D13: nel cervello cambia solo `alto`).

    **Si ritenta finche' arriva** (scelta del proprietario, 06/10/2026): le
    proposte da avvisare le dice l'archivio delle costruzioni -- `alto`, del
    proponente, in attesa, senza un avviso arrivato -- e il giro le guarda a
    ogni battito. Smette quando almeno una push e' arrivata, o quando la
    proposta non e' piu' in attesa: nessun numero di tentativi scelto da noi.
    Il livello l'ha scritto l'officina; qui non si ricalcola.
    """
    constructions = app.get("constructions")
    if constructions is None:
        return
    for row in constructions.to_alert(actor=PROPOSER_SPECIES, stakes=HIGH,
                                      now=time.time()):
        body = row.get("dopo") or row.get("prima") or {}
        name = body.get("alias") if isinstance(body, dict) else None
        report = await notify_admins(
            app, ALERT_TEXT.format(name=name or row.get("chiave")),
            actor=PROPOSER_SPECIES)
        if report.get("push", 0) > len(report.get("mancate") or ()):
            constructions.mark_alerted(row["id"], now=time.time())
