"""Il giro dell'**analista**, la parte che vive fuori da `server.py`.

Oggi ci sta solo la scrittura dell'analisi (`write_analysis`), spostata da
`server.py` senza una riga di logica cambiata (N65-2, 07/10/2026): la scrittura
e' il punto in cui il «rimetti» dell'analista si confronta con la casa, e la
regola del proprietario del 06/10/2026 vieta codice nuovo dentro `server.py`.
Il resto del giro (`analyst_round`, il raccoglitore del ponte) ci arriva alla
Chiusura dello sprint, quando `server.py` si spezza in commit di solo
spostamento (`analisi/2026-10-06-file-monolitici-proposta.md`, passo 2).
"""
from __future__ import annotations

import logging
import time

from ..home_space import historian
from ..home_space.historian import house_timezone
from ..home_space.house import House
from ..home_space.privacy import PresenceMask
from ..reasoning.queue import turn_answer
from ..steering import (
    ANALYST_SPECIES,
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
from . import analyst, analyst_turn, report
from .view import mind_view

logger = logging.getLogger(__name__)

#: Quanti giorni di misure si consegnano all'analista. Trenta e' il numero
#: della spec §9 -- «trenta giorni di misure stanno in un prompt» -- e
#: misurato sulla casa vera sono ~35.000 token.
ANALYST_DAYS = 30


def analyst_inputs(store, day: str, *, device_names: dict) -> tuple[dict, list[dict]]:
    """La serie dell'analista e la sua memoria, composte dall'archivio di
    adesso: le stesse all'accodamento (`analyst_round`) e alla raccolta
    (`_collect_analyst_turn`), che fino al 14/10/2026 le componevano ognuna
    da se', riga per riga (D-34).

    I nomi dei dispositivi li porta chi chiama (`MindView.device_names`, il
    loro posto solo): cosi' `mind/` non importa una rotta (N161-1).
    La memoria e' cio' che l'analista ha gia' detto nella sua finestra, dagli
    archivi (D4 del piano degli attori, `analyst.previous_observations`)."""
    series = analyst.with_deviation(
        report.series_of_measures(store.reports(limit=ANALYST_DAYS), names=device_names))
    return series, analyst.previous_observations(
        store.analyses(limit=ANALYST_DAYS), store.proposals(), today=day, series=series)


def write_analysis(app, store, day: str, occurrence: dict) -> None:
    """Scrive l'analisi, o dice perche' non l'ha scritta.

    **Una risposta rifiutata non si archivia**: un'analisi con dentro dei
    problemi non e' un'analisi, e scriverla direbbe che quel giorno e' stato
    analizzato. Il giro dopo riprova, perche' `analysis(giorno)` resta `None`.

    **Il «rimetti» si confronta con la casa di adesso** (N65-2): `app` serve
    solo a leggerla, dagli stessi archivi vivi da cui la legge l'osservatore.
    """
    analysis = occurrence.get("analisi")
    if analysis is None:
        if occurrence.get("problemi"):
            logger.warning("analista: risposta rifiutata per %s -- %s",
                           day, " \u00b7 ".join(occurrence["problemi"]))
        return
    # **Il fondamento si legge QUI**, non da chi chiama: e' lo stato dei
    # resoconti nel momento in cui l'analisi viene scritta, e le due strade --
    # il turno diretto e la risposta raccolta dal ponte -- devono registrarlo
    # allo stesso modo. Il ponte rilegge le serie adesso (vedi
    # `_collect_analyst_turn`), quindi «adesso» e' il fondamento giusto per
    # entrambe.
    analysis = {**analysis,
                "fondamento": analyst_turn.fondamento(
                    store.report_stamps(limit=ANALYST_DAYS))}
    house = House.read(app.get("home_space_store"), app.get("entity_cache"))
    # Un istante solo per la scrittura (G-14): le decisioni del «rimetti
    # dentro» e l'analisi che le porta nascono nello stesso momento.
    now = time.time()
    store.replace_analysis(day, analyst.bring_back(store, analysis, house, when_ts=now),
                           when_ts=now)
    logger.info("analista: analisi di %s scritta (%d osservazioni)",
                day, len(analysis.get("osservazioni") or []))


async def analyst_round(app) -> dict | None:
    """L'anello dell'analista: **«leggi le misure di molti giorni e di' cosa si
    potrebbe fare»** (spec §10).

    Torna il resoconto del giro, o `None` se non c'era da farlo.

    **Una volta al giorno, e non e' prudenza generica.** Misurato sulla casa
    vera il 15/09/2026, con venti giorni archiviati e 146 serie: la domanda
    pesa **~35.000 token** -- tre volte il giro dell'osservatore. Farla a ogni
    giro dello schedulatore svuoterebbe il tetto giornaliero del piano da sola.
    Un giorno ha una analisi sola, e quando ce l'ha il giro non fa niente.

    **Il silenzio si archivia**, e non e' un giro sprecato: «ho guardato e non
    c'era niente da dire» e «non ho guardato» sono due cose diverse, ed e' la
    stessa legge del resoconto vuoto.

    **Dalla stessa porta dello scope e delle ricette**: chi risponde lo decide
    `steering.who_answers`.

    Non solleva mai: gira per sempre, e un giro andato storto non deve fermare
    lo schedulatore.
    """
    store = app.get("observations")
    if store is None:
        return None
    try:
        timezone = house_timezone(app.get("home_space_store"))
        today = historian.today(timezone).isoformat()

        collected = _collect_analyst_turn(app, store, today)
        # **Chiude il giro solo un'analisi SCRITTA** (06/10/2026). Fino a
        # qui bastava `risposta`: una risposta rifiutata non si archivia, il
        # turno restava l'ultimo della sua specie, e il giro lo rileggeva e
        # rifiutava a ogni passaggio senza accodarne mai uno nuovo -- dal
        # 05/10 13:32 al 06/10 14:05 sulla casa vera, su un turno fallito dal
        # ponte. Sesta occorrenza della forma del 22/09 (sopra
        # `_collect_analyst_turn`). Un rifiuto o un vuoto aspettano il freno
        # delle ricette, poi si richiede: accodato il turno nuovo, quello
        # vecchio non e' piu' l'ultimo e non si rilegge.
        if collected is not None and collected.get("analisi") is not None:
            return collected
        if collected is not None and too_soon_to_ask_again(
                app, analyst_turn.ANALYSIS_TURN_KIND):
            return collected
        # **Non «c'e' gia' un'analisi per oggi?», ma «ce n'e' gia' una su
        # QUESTO fondamento?»** (difetto trovato dal proprietario il
        # 20/09/2026). I resoconti che l'analista legge possono cambiare
        # durante la giornata -- un giorno recuperato da `backfill_one_report`,
        # o rifatto dopo una correzione di giudizio -- e col vecchio confronto
        # quel giorno non entrava in nessuna analisi, mai: l'analisi restava
        # quella delle 14:00 e l'indomani si analizzava l'indomani.
        #
        # Ventitre' giri su ventiquattro il fondamento e' identico e qui non
        # succede niente, come prima.
        fondamento = analyst_turn.fondamento(store.report_stamps(limit=ANALYST_DAYS))
        scritta = store.analysis(today)
        if scritta is not None and scritta.get("fondamento") == fondamento:
            return None
        if turn_in_flight(app, analyst_turn.ANALYSIS_TURN_KIND):
            return None

        series, previous = analyst_inputs(store, today,
                                          device_names=mind_view(app).device_names())
        if not (series.get("serie") or []):
            return None

        # I problemi della risposta di prima, se e' stata rifiutata (D10):
        # dal registro dei turni, la stessa riga sulle due strade.
        refused = refused_problems(app.get("usage"), ANALYST_SPECIES)
        route, _downgrade, runner = start(app, ANALYST_SPECIES)
        if route == "ponte":
            return _enqueue_analyst_turn(app, series, today, previous,
                                         refused=refused)
        if runner is None:
            logger.info("analista: nessun modello collegato, si riprova al giro dopo")
            return None

        # Gli strumenti e il guardiano li dice la dichiarazione del mestiere
        # (D5, Task 3.6): gli stessi che il ponte serve da `/api/mcp`. Il
        # guardiano porta la maschera dei nomi, che copre anche la domanda.
        declared = SPECIES[ANALYST_SPECIES]
        dispatcher = await declared.guard(app) if declared.guard else None
        presence = getattr(dispatcher, "presence", None)
        question = analyst_turn.build_question(series, previous, refused=refused,
                                               presence=presence)
        if question is None:
            return None
        answer, turn = await chain_turn(
            runner, ANALYST_SPECIES, usage=app.get("usage"),
            max_tokens=analyst_turn.MAX_ANSWER_TOKENS,
            user_message=question, system_prompt=analyst_turn.SYSTEM,
            tools=declared.catalog_for_turn() or None, dispatcher=dispatcher)
        esito = analyst_turn.apply_analysis(
            series, chain_answer(answer, turn), truncated=turn.truncated,
            previous=previous, tool_calls=turn.tool_calls, presence=presence)
        if _was_refused(esito) and not turn.truncated:
            declare_refused(app.get("usage"), turn.turn_id, esito["problemi"])
        write_analysis(app, store, today, esito)
        return esito
    except Exception as error:
        logger.warning("analista: giro fallito (%s: %s) -- si riprova al giro "
                       "dopo", type(error).__name__, error)
        return None


def _was_refused(esito: dict) -> bool:
    """Se il modello ha risposto e la risposta non e' passata (D10): non un
    silenzio, non un guasto del ponte -- un'analisi rifiutata coi suoi
    problemi."""
    return bool(esito.get("risposta")) and esito.get("analisi") is None


def _analyst_presence(app):
    """La maschera dei nomi sulla casa di adesso (decisione 12 estesa): quella
    che il raccoglitore rifa' per riportare i segnaposto agli id."""
    casa = app.get("home_space_store")
    return (PresenceMask(House.read(casa, app.get("entity_cache")))
            if casa is not None else None)


def _enqueue_analyst_turn(app, series: dict, day: str,
                          previous: list[dict] | None = None, *,
                          refused: list[str] | None = None) -> dict | None:
    """Accoda al piano la domanda dell'analista, e torna subito."""
    job = analyst_turn.bridge_turn(series, previous, refused=refused,
                                   presence=_analyst_presence(app))
    if job is None:
        return None
    # **Nella sveglia va il giorno**: il ponte risponde minuti dopo, da un
    # altro processo, e chi raccoglie deve sapere di QUALE giorno era la
    # domanda -- e con quali serie confrontarla.
    _job_id, deadline_min = enqueue_turn(app, ANALYST_SPECIES, {"giorno": day}, job)
    logger.info("analista: turno accodato al piano per %s (scadenza %d min)",
                day, deadline_min)
    return {"accodata": True, "giorno": day}


def _collect_analyst_turn(app, store, today: str) -> dict | None:
    """La risposta che il piano ha dato alla domanda dell'analista.

    **Un turno gia' letto non si rilegge**, e la traccia e' l'analisi stessa:
    se quel giorno ne ha gia' una, la risposta e' gia' stata applicata.

    **Le serie si rileggono adesso, non si conservano.** Il ponte risponde
    minuti dopo e potrebbe averlo fatto dopo un'aggregazione: i numeri che
    l'osservazione portera' devono essere quelli che l'archivio ha ORA, o
    direbbero una cosa che nessuno puo' piu' verificare.

    **I problemi di una risposta rifiutata si chiedono qui**: con `risposta`
    vera e `analisi` `None`, `esito["problemi"]` sono i motivi del rifiuto.
    Vivono nel turno stesso -- la risposta resta nella coda, e si rivalida a
    ogni lettura -- finche' quel turno e' l'ultimo della sua specie, cioe'
    fino all'accodamento del turno nuovo. Con `risposta` falsa (vuota, o un
    turno che il ponte ha fallito: `turn_answer`) non c'e' nessuna risposta da
    correggere.
    """
    queue = app.get("reasoning_queue")
    if queue is None:
        return None
    turn = queue.latest_if_decided(analyst_turn.ANALYSIS_TURN_KIND)
    if turn is None:
        return None
    # **Le due guardie che i fratelli avevano e questo no** (difetto misurato
    # sulla casa vera il 22/09/2026, sei giorni di silenzio).
    #
    # `status` (la fa `latest_if_decided`, qui sopra): un turno ancora
    # `pending` non ha niente da raccogliere, e provarci produce l'esito finto
    # «il modello non ha risposto» -- che a valle si legge come un giro gia'
    # fatto.
    #
    # `giorno`: una risposta per un altro giorno non dice niente su oggi.
    # Il giro del proponente lo pretende da sempre.
    #
    # Perche' insieme costavano sei giorni: il turno del 17/09 era `decided`
    # con una risposta che la validazione **non poteva accettare**; una
    # risposta rifiutata non si archivia (giusto), quindi `analysis(giorno)`
    # restava `None` per sempre, quindi il raccoglitore la riapplicava a ogni
    # giro tornando `risposta: True` -- e `analyst_round` usciva li'. L'analisi
    # di oggi non veniva mai nemmeno tentata.
    #
    # **Quinta occorrenza della stessa forma**: la porta salta chi ha gia' una
    # risposta, anche quando la risposta e' rotta.
    day = (turn.get("wake") or {}).get("giorno")
    if day != today or store.analysis(day) is not None:
        return None
    from ..agent.runner import _bare_tool_name

    decision = turn.get("decision") or {}
    reply = turn_answer(turn)
    # Le letture del turno, come sulla catena: `{tool, input}` col nome NUDO
    # -- il prefisso `mcp__hiris__` e' del trasporto, e si toglie al confine
    # (`runner._bare_tool_name`).
    calls = [{"tool": _bare_tool_name(c.get("tool")), "input": c.get("input")}
             for c in decision.get("tools_called") or [] if isinstance(c, dict)]
    series, previous = analyst_inputs(store, day,
                                      device_names=mind_view(app).device_names())
    # I segnaposto che il modello ha letto sul ponte tornano id dalla stessa
    # numerazione, sulla casa di adesso (come l'osservatore, decisione 12).
    esito = analyst_turn.apply_analysis(series, reply, previous=previous,
                                        tool_calls=calls,
                                        presence=_analyst_presence(app))
    if _was_refused(esito):
        # L'esito sulla riga del turno del ponte (D10): il runner l'ha messa
        # nella decisione. Il raccoglitore rilegge lo stesso turno finche' non
        # ne parte un altro, e riscrivere lo stesso esito non cambia niente.
        declare_refused(app.get("usage"), decision.get("turn_id"), esito["problemi"])
    if not esito.get("risposta"):
        # Il ponte ha restituito una decisione vuota: non e' una risposta, e
        # non si scrive niente. Il giro successivo richiede.
        return esito
    write_analysis(app, store, day, esito)
    return esito
