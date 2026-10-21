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

from aiohttp import web

from ..action.construction.revisions import CONSTRUCTIONS_KEY
from ..action.construction.stakes import HIGH
from ..home_space import historian
from ..home_space.reader import HOME_SPACE_KEY, house_timezone_of
from ..keeper.delivery import NOTICE_HINT, align_notices, arrived, notify_admins
from ..keeper.promise import DELIVERY_TITLE
from ..live_value import LiveValue
from ..proxy.entity_cache import ENTITY_CACHE_KEY
from ..reasoning.queue import REASONING_QUEUE_KEY, turn_answer, turn_truncated
from ..states import SUPERSEDED
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
from ..usage.store import USAGE_KEY
from . import proposer_turn
from .analyst import evidence_of, observation_key
from .store import OBSERVATIONS_KEY

logger = logging.getLogger(__name__)

#: La chiave di `app` che dice che un giro e' in corso. Lo schedulatore ha
#: mezz'ora di `misfire_grace_time`: due giri possono partire insieme dopo una
#: sosta dell'add-on, e senza questa guardia si pagherebbero due turni.
IN_FLIGHT = web.AppKey("proponente_in_volo", LiveValue)

#: La chiave della sveglia che fa di un turno del proponente un turno del
#: GIRO: la porta ogni accodamento di `_enqueue`. Nella stessa specie stanno
#: anche i «Rifalla» (`mind/proposal_redo.py`), che portano `proposta`: il
#: giro guarda solo i suoi.
ROUND_KEY = "giorno"

#: Il giro e' SPENTO nella 3.78.0 (il proprietario, 12/10/2026: «Fermo»): si
#: accende dopo la misura dal vivo dello strato 3, come vuole il piano degli
#: attori («Il proponente ... dopo lo strato 3»). Accenderlo e' un commit che
#: scrive `True` qui, non un'opzione: un'impostazione che nessuna pagina
#: mostra sarebbe configurabile solo a parole. Spento vuol dire che lo
#: schedulatore non chiede niente al modello e non accoda niente; il
#: «Rifalla» della pagina (`mind/proposal_redo.py`) resta, perche' parte da
#: una persona.
ENABLED = False


async def proposer_beat(app) -> dict | None:
    """Cio' che lo schedulatore chiama ogni ora: il giro, se e' acceso
    (`ENABLED`); altrimenti niente, e non lo dice a ogni battito.

    **Gli avvisi delle proposte `alto` partono anche a giro spento** (N141-1,
    giro 141): il «Rifalla» resta acceso e firma come il proponente, quindi
    una proposta su una serratura puo' nascere `alto` anche oggi, e la regola
    del proprietario (D14, 06/10/2026: «si ritenta finche' arriva») vuole
    l'avviso. Il ritentare lo fa questo battito."""
    if not ENABLED:
        await _alert_high_safely(app)
        return None
    return await proposer_round(app)


async def proposer_round(app) -> dict | None:
    """Il giro: raccoglie la risposta del ponte, poi chiede per le
    osservazioni ancora aperte. Torna il resoconto, o `None` se non c'era da
    farlo."""
    store = app.get(OBSERVATIONS_KEY)
    if store is None or app[IN_FLIGHT].value:
        return None
    app[IN_FLIGHT].set(True)
    try:
        # Prima di tutto gli avvisi che non sono arrivati: si ritentano a ogni
        # battito, anche nei giorni senza analisi (D14, «Ritenta»).
        await _alert_high_safely(app)
        today = historian.today(
            house_timezone_of(app)).isoformat()
        if store.analysis(today) is None:
            return None
        # **La risposta del ponte si raccoglie PRIMA di chiedere di nuovo**:
        # il ponte risponde minuti dopo, e senza questo passo il giro
        # accoderebbe una domanda a ogni battito e non ne leggerebbe nessuna.
        collected = await _collect(app, store, today)
        pending = _open(app, store, today, report=True)
        if not pending:
            return collected
        # Un turno in volo, o finito da meno di un'ora (`RETRY_HOLD_S`): si
        # aspetta, come l'analista e le ricette.
        if turn_in_flight(app, proposer_turn.PROPOSAL_TURN_KIND, wake_key=ROUND_KEY) \
                or too_soon_to_ask_again(app, proposer_turn.PROPOSAL_TURN_KIND,
                                         wake_key=ROUND_KEY):
            return collected
        refused = refused_problems(app.get(USAGE_KEY), PROPOSER_SPECIES)
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
        app[IN_FLIGHT].set(False)


async def _chain(app, store, day: str, pending, refused, runner) -> dict:
    """Il turno sulla catena: gli strumenti e il guardiano dalla dichiarazione
    del mestiere, l'identita' del turno coniata qui (sul ponte la conia il
    runner)."""
    declared = SPECIES[PROPOSER_SPECIES]
    exchange = secrets.token_urlsafe(9)
    dispatcher = await declared.guard(app, exchange)
    presence = getattr(dispatcher, "presence", None)
    question = proposer_turn.build_question(pending, refused=refused,
                                            presence=presence,
                                            unbound=_unbound(app))
    answer, turn = await chain_turn(
        runner, PROPOSER_SPECIES, usage=app.get(USAGE_KEY),
        max_tokens=proposer_turn.MAX_ANSWER_TOKENS,
        user_message=question, system_prompt=proposer_turn.SYSTEM,
        tools=declared.catalog_for_turn(), dispatcher=dispatcher)
    occurrence = proposer_turn.apply_outcomes(
        pending, chain_answer(answer, turn), built=_built_in(app, exchange),
        truncated=turn.truncated, presence=presence)
    if occurrence["risposta"] and occurrence["problemi"] and not turn.truncated:
        declare_refused(app.get(USAGE_KEY), turn.turn_id, occurrence["problemi"])
    _settle(app, store, day, occurrence)
    await _alert_high_safely(app)
    return occurrence


def _enqueue(app, day: str, pending, refused) -> dict | None:
    """Accoda al piano la domanda, e torna subito. **Nella sveglia vanno il
    giorno e le impronte, in ordine**: chi raccoglie minuti dopo deve
    rinumerare le STESSE osservazioni, anche se nel frattempo alcune hanno
    avuto un esito."""
    from ..home_space.house import House
    from ..home_space.privacy import PresenceMask

    home_space = app.get(HOME_SPACE_KEY)
    presence = (PresenceMask(House.read(home_space, app.get(ENTITY_CACHE_KEY)))
                if home_space is not None else None)
    job = proposer_turn.bridge_turn(pending, refused=refused, presence=presence,
                                    unbound=_unbound(app))
    if job is None:
        return None
    wake = {ROUND_KEY: day, "impronte": [observation_key(o) for o in pending]}
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
    queue = app.get(REASONING_QUEUE_KEY)
    turn = (queue.latest_if_decided(proposer_turn.PROPOSAL_TURN_KIND, wake_key=ROUND_KEY)
            if queue else None)
    if turn is None:
        return None
    wake = turn.get("wake") or {}
    if wake.get(ROUND_KEY) != today:
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
    home_space = app.get(HOME_SPACE_KEY)
    presence = (PresenceMask(House.read(home_space, app.get(ENTITY_CACHE_KEY)))
                if home_space is not None else None)
    occurrence = proposer_turn.apply_outcomes(
        pending, reply, built=_built_in(app, decision.get("exchange_id")),
        truncated=turn_truncated(turn),
        presence=presence)
    if occurrence["problemi"]:
        declare_refused(app.get(USAGE_KEY), decision.get("turn_id"), occurrence["problemi"])
    _settle(app, store, today, occurrence)
    await _alert_high_safely(app)
    return occurrence


def _open(app, store, day: str, *, report: bool = False) -> list[dict]:
    """Le osservazioni di `day` ancora senza esito, contro le proposte gia'
    fatte dai due archivi. Con `report`, chi salta lo scrive nel registro
    (S-26): una riga per giro, non una per osservazione."""
    constructions = app.get(CONSTRUCTIONS_KEY)
    decided = proposer_turn.latest_decided(
        store.decided_proposals(),
        constructions.decided_proposals(now=time.time())
        if constructions is not None else {})
    skipped: list = []
    pending = proposer_turn.open_observations(store.analysis(day), decided, skipped)
    if report and skipped:
        logger.info("proponente: %d osservazioni non si richiedono -- %s",
                    len(skipped),
                    " · ".join(f"{key}: {why}" for key, why in skipped))
    return pending


def _unbound(app) -> list[dict]:
    """Le proposte del proponente in attesa e senza domanda: costruite in un
    turno la cui risposta non le ha citate (revisione, giro 61)."""
    constructions = app.get(CONSTRUCTIONS_KEY)
    if constructions is None:
        return []
    return constructions.unbound(actor=PROPOSER_SPECIES, now=time.time())


def _built_in(app, exchange: str | None) -> frozenset[str]:
    """Gli id che un «costruita» puo' citare: le proposte nate nel turno,
    dall'archivio delle costruzioni, e quelle gia' costruite che nessun esito
    ha citato -- citarle e' cio' che evita una seconda bozza per la stessa
    domanda (revisione, giro 61)."""
    constructions = app.get(CONSTRUCTIONS_KEY)
    if constructions is None:
        return frozenset()
    return constructions.proposed_in(exchange, actor=PROPOSER_SPECIES) \
        | {row["id"] for row in _unbound(app)}


def _settle(app, store, day: str, occurrence: dict) -> None:
    """Scrive gli esiti buoni, uno per osservazione, accanto all'analisi; la
    proposta da fare a mano nell'archivio gemello con l'impronta e la prova;
    sulla riga di una costruita l'impronta e la prova della sua domanda
    (D24-2). Un esito per un'osservazione che ne ha gia' uno non si
    riscrive: e' cio' che rende innocua una seconda lettura dello stesso turno.

    Con una proposta a mano ancora in attesa sulla stessa domanda (D24-1):
    una costruita la chiude `superata`; un secondo «a mano» non la duplica,
    e l'esito accanto cita quella che aspetta gia'.
    """
    if occurrence["problemi"]:
        logger.warning("proponente: esiti rifiutati per %s -- %s",
                       day, " · ".join(occurrence["problemi"]))
    analysis = store.analysis(day)
    if analysis is None or not occurrence["esiti"]:
        return
    # Un istante solo per gli esiti di questo turno (G-14): le proposte a
    # mano che nascono e l'analisi che le cita si scrivono nello stesso momento.
    now = time.time()
    still_open = {observation_key(o) for o in _open(app, store, day)}
    waiting = {key: entry for key, entry in store.decided_proposals().items()
               if entry["aperta"]}
    constructions = app.get(CONSTRUCTIONS_KEY)
    beside = proposer_turn.outcomes_of(analysis)
    for outcome in occurrence["esiti"]:
        key = outcome["impronta"]
        if key not in still_open:
            continue
        still_open.discard(key)
        observation = outcome.get("osservazione")
        earlier = waiting.get(key)
        if outcome["esito"] == proposer_turn.BY_HAND:
            if earlier is not None:
                logger.info("proponente: la proposta a mano su %s aspetta gia' "
                            "(%s), non si duplica", key, earlier["id"])
                ident = earlier["id"]
            else:
                ident = store.add_proposal(
                    text=outcome["testo"], perche=outcome["perche"],
                    fingerprint=key, prova=evidence_of(observation),
                    # Il livello di una proposta da fare a mano non lo impone
                    # nessuno: una frase in prosa non porta i domini su cui il
                    # codice imporrebbe `alto` (D13).
                    stakes=None, now_ts=now)
            outcome = {"impronta": key, "esito": outcome["esito"],
                       "proposta_id": ident}
        elif outcome["esito"] == proposer_turn.BUILT:
            if constructions is not None:
                constructions.answers(outcome["proposta_id"], actor=PROPOSER_SPECIES,
                                      fingerprint=key, prova=evidence_of(observation))
            if earlier is not None:
                store.close_proposal(earlier["id"], SUPERSEDED,
                                     why=proposer_turn.SUPERSEDED_WHY)
                logger.info("proponente: la proposta a mano su %s e' superata "
                            "dalla costruita %s", key, outcome["proposta_id"])
        beside.append({k: v for k, v in outcome.items() if k != "osservazione"})
    store.replace_analysis(day, {**analysis, proposer_turn.OUTCOMES_KEY: beside},
                           when_ts=now)

#: Il testo della push agli amministratori. Lo scrive il codice, non il
#: modello: il nome dell'oggetto e' l'unica parte che viene dalla proposta.
#: Non nomina i domini: quali sono `alto` lo dice `stakes.HIGH_STAKES_DOMAINS`,
#: e una frase che li ricopiasse mentirebbe il giorno in cui la lista cambia.
ALERT_TEXT = ("HIRIS ha una proposta di livello alto: «{name}». "
              "Decidi tu, nella pagina Proposte.")

#: Le notifiche persistenti delle proposte `alto`, una per proposta: l'id
#: viaggia verso Home Assistant, e porta il suo nome in inglese.
NOTICE_FAMILY = "hiris_proposal_"
NOTICE_TITLE = f"{DELIVERY_TITLE} · proposta di livello alto"


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

    **E una notifica persistente per proposta** (scelta del proprietario,
    21/10/2026): `NOTICE_FAMILY` + id della proposta, finche' la proposta
    aspetta, avvisata o no; decisa o scaduta, il battito dopo la toglie
    (`keeper/delivery.align_notices`). Viene prima della push, cosi' la push
    dice `NOTICE_HINT` solo se la notifica c'e' davvero.
    """
    constructions = app.get(CONSTRUCTIONS_KEY)
    if constructions is None:
        return
    now = time.time()
    shown = await align_notices(app, NOTICE_FAMILY, {
        f"{NOTICE_FAMILY}{row['id']}": (NOTICE_TITLE, _alert_text(row))
        for row in constructions.waiting(actor=PROPOSER_SPECIES, stakes=HIGH, now=now)},
        actor=PROPOSER_SPECIES)
    for row in constructions.to_alert(actor=PROPOSER_SPECIES, stakes=HIGH, now=now):
        text = _alert_text(row)
        if f"{NOTICE_FAMILY}{row['id']}" in (shown.get("allineate") or ()):
            text = f"{text}\n{NOTICE_HINT}"
        report = await notify_admins(app, text, actor=PROPOSER_SPECIES)
        if arrived(report):
            constructions.mark_alerted(row["id"])


def _alert_text(row: dict) -> str:
    body = row.get("dopo") or row.get("prima") or {}
    name = body.get("alias") if isinstance(body, dict) else None
    return ALERT_TEXT.format(name=name or row.get("chiave"))
