"""Il giro dell'**osservatore**: la riconsiderazione dello scope, i suoi
turni sul ponte e l'elenco delle statistiche consegnato al `watcher`.

Spostato da `server.py` senza una riga di logica cambiata (Chiusura dello
sprint, F8 passo 2, 14/10/2026): la regola del proprietario del 06/10/2026
vuole che `server.py` registri e avvii, non che ospiti i giri.
"""
from __future__ import annotations

import logging
import time

from ..home_space.house import House
from ..home_space.house_history import statistic_ids_for_round
from ..providers import SUBSCRIPTION
from ..reasoning.queue import turn_answer
from ..steering import OBSERVER_SPECIES, enqueue_turn, start, turn_in_flight
from ..version import read_version
from . import store as mind_store
from .cadence import cadence_from, measure_memory_window, reason_to_reconsider
from .observer import SCOPE_TURN_KIND
from .observer import apply_answer as observer_apply_answer
from .observer import bridge_turn as observer_bridge_turn
from .observer import reconsider as observer_reconsider

logger = logging.getLogger(__name__)


async def reconsideration_round(app, ha_client) -> dict | None:
    """L'anello dell'osservatore: **«è ora di ripensare la casa? e allora
    fallo»**. Torna il resoconto del giro, o `None` se non c'era da farlo.

    I quattro inneschi della spec §5.1 -- il primo avvio, l'obiettivo cambiato,
    qualcosa di nuovo in casa, la cadenza di riconsiderazione -- li pone tutti
    `cadence.reason_to_reconsider`: qui non se ne decide nessuno, o sarebbero
    due posti da cui dimenticarne uno.

    **La domanda «è ora?» deve costare zero.** Questo giro scatta ogni
    minuto; misurare la memoria di Home Assistant a ogni passaggio sarebbe
    traffico speso per rispondere «no». Quindi si
    usa la cadenza **dell'ultimo giro**, scritta accanto a quello, e la finestra
    si **rimisura solo quando si gira davvero**: e' anche piu' giusta, perche'
    il proprietario puo' aver cambiato il recorder nel frattempo.

    **L'impronta si chiede sulle stesse entita' che si mostrano al modello.**
    L'osservatore non giudica le entita' di servizio e le nascoste (decisione
    del proprietario, 10/09/2026): nessuna di esse finisce mai nello scope,
    quindi chiederle all'impronta le farebbe risultare «nuove» a ogni giro --
    452 su questa casa -- e l'osservatore girerebbe a ogni passaggio, per
    sempre.

    **Il giro ha DUE tempi, e non e' una complicazione gratuita** (fetta
    «l'osservatore chiede a chi risponde davvero», 11/09/2026). Chi risponde
    lo decide `steering.who_answers`, la stessa funzione che lo decide per la
    chat e per le promesse; quando risponde «ponte», il turno si **accoda** e
    la risposta torna minuti dopo, da un altro processo. Quindi ogni
    passaggio prima guarda se c'e' una risposta da raccogliere, e solo dopo si
    chiede se sia ora di domandare ancora.

    Non solleva mai: gira per sempre, e un avvio a meta' -- il modello non
    ancora costruito, l'anagrafe non ancora letta -- non deve fermare lo
    schedulatore.
    """
    store = app.get("observations")
    home_space_store = app.get("home_space_store")
    if store is None or home_space_store is None:
        return None
    try:
        # La casa di questo giro (R13): l'anagrafe e lo specchio di adesso,
        # una volta. Vale il giro e basta.
        house = House.read(home_space_store, app.get("entity_cache"))
        collected, letto = _collect_scope_turn(app, store, house)
        if collected is not None:
            return collected
        if letto:
            # **Una raccolta fallita chiude il passaggio: non si richiede
            # subito.** Riaccodando nello stesso giro, un guasto stabile
            # produrrebbe un turno a ogni scadenza del ponte.
            # `count_exchanges_today` conta ogni specie contro il tetto
            # giornaliero del piano: un osservatore rotto lo svuoterebbe da
            # solo, e da li' in poi ogni turno -- chat compresa -- passerebbe
            # ai provider a pagamento.
            return None
        if turn_in_flight(app, SCOPE_TURN_KIND):
            # Questo giro scatta ogni minuto e un turno del piano ne dura
            # parecchi: senza questa guardia la casa accodarebbe un turno al
            # minuto, ciascuno col suo lotto di casa dentro, e il tetto
            # giornaliero del piano si svuoterebbe in mezz'ora.
            return None
        if _retry_hold(store, now=time.time()):
            return None

        # Chi l'osservatore guarda lo dice la casa (Task 12): la stessa
        # scelta di `observer.watched_ids`, non una seconda lettura.
        candidates = sorted(house.visible_entities())
        last = store.last_reconsideration()
        objective = store.objective()
        # **Una riconsiderazione e' una CAMPAGNA di piu' lotti.** La domanda
        # si spezza perche' 381 giudizi in un turno solo uccidono la CLI del
        # piano (misurato l'11/09/2026, vedi `SCOPE_BATCH`), e la campagna
        # prosegue ai giri successivi finche' la casa e' coperta -- **senza
        # riaspettare la cadenza**, che altrimenti sarebbe gia' soddisfatta e
        # i lotti dal secondo in poi non partirebbero mai.
        restano = _to_judge(store, candidates, last)
        in_corso = last is not None and bool(restano)
        if in_corso:
            why = (f"la campagna prosegue: restano {len(restano)} soggetti "
                   "da giudicare")
        else:
            why = reason_to_reconsider(
                last=last,
                cadence_s=last["cadenza_s"] if last else None,
                objective_ts=objective.get("scritto_ts"),
                undecided=store.undecided(candidates),
                now=time.time())
            if why is None:
                return None
            # La campagna comincia ADESSO: i soggetti da rigiudicare sono
            # tutti, e l'istante si prende PRIMA delle decisioni cosi' che
            # quelle del primo lotto risultino gia' dentro la campagna.
            restano = list(candidates)
        lotto = set(restano[:SCOPE_BATCH])

        # **La stessa domanda che si fanno la chat e le promesse, dalla stessa
        # funzione.** Fino all'11/09/2026 questo giro non se la faceva affatto
        # e andava dritto al router -- dove il ponte non e' un anello
        # (`providers.chain_members()`). Misurato sulla casa vera l'11/09
        # alle 11:00:44: l'osservatore cadeva su un modello OpenRouter
        # «batch-only» (404) e su una chiave Claude senza credito (400) mentre
        # l'abbonamento, li' accanto, serviva la chat. E' il difetto che
        # `steering.py` dichiara chiuso il 22/08 per le promesse, con la frase
        # «una terza porta che nascesse domani non potrebbe inventarsene una
        # terza senza accorgersene»: la terza porta era questa.
        # **Il passaggio dal forfait al consumo si annuncia ogni volta**
        # (decisione del proprietario, 13/08/2026, che `steering.py` dichiara
        # nel suo docstring): un prelievo silenzioso si scopre a fine mese. Lo
        # dichiara la partenza (`steering.start`). Il motivo e' una chiave di
        # `model_resolution._DOWNGRADE_REASONS`, e finisce anche nel
        # tentativo, cosi' la pagina puo' dire da quale porta e' passato quel
        # giro.
        route, downgrade, runner = start(app, OBSERVER_SPECIES)
        if route == "catena" and runner is None:
            # **Anche il silenzio si annota.** Senza token del piano e senza
            # nessun provider in catena l'osservatore taceva per sempre, con
            # la faccia di «nessuno ha ancora provato» (rilievo della review
            # indipendente, 11/09/2026).
            store.record_attempt(
                outcome=mind_store.ATTEMPT_FAILED,
                detail=f"non c'era nessun modello a cui chiedere ({downgrade})"
                if downgrade else "non c'era nessun modello a cui chiedere",
                version=read_version())
            return None

        logger.info("osservatore: riconsidero la casa (%s), lotto di %d -- %s",
                    route, len(lotto), why)
        campagna_ts = time.time()
        # **La finestra si misura solo per il lotto che la annota** (A-19,
        # Tappa 2, Task 8): la riconsiderazione la scrive solo il primo lotto
        # della campagna (`apply_answer` con `record=True`, il turno del ponte
        # con `annota`). I lotti successivi la misuravano su tutte le entita'
        # -- dieci sonde, piu' sette se la memoria cade dentro la scala -- e
        # la buttavano.
        # **L'insieme e' quello del registratore, non quello dell'osservatore**
        # (Task 12): la memoria e' di Home Assistant, e la provano anche le
        # entita' che nessuno guarda. Ogni entita' del registro, come prima.
        window_s = None if in_corso else await measure_memory_window(
            ha_client, sorted(house.entity_ids()))
        if route == "ponte":
            return _enqueue_scope_turn(app, store, house, reason=why,
                                       window_s=window_s, lotto=lotto,
                                       annota=not in_corso,
                                       campagna_ts=campagna_ts)
        outcome = await observer_reconsider(
            runner, store, house, reason=why,
            window_s=window_s, cadence_s=cadence_from(window_s),
            only=lotto, record=not in_corso, campaign_ts=campagna_ts,
            measurements=app.get("usage"))
        _record_attempt(store, outcome, route="catena", downgrade=downgrade)
        logger.info("osservatore: giro finito -- %s", outcome)
        return outcome
    except Exception as exc:
        logger.warning("osservatore: giro di riconsiderazione fallito (%s: %s)",
                       type(exc).__name__, exc)
        return None


async def hold_watcher_statistic_ids(app, ha_client) -> None:
    """L'elenco delle entita' con statistiche consegnato al watcher (B-12,
    Tappa 3, Task 7, 04/10/2026), dalla stessa lettura condivisa dei giri
    (`statistic_ids_for_round`): il watcher decide su ogni evento se una
    lettura la tiene gia' Home Assistant, e non puo' chiederlo evento per
    evento. Lo fa il giro delle condizioni, ogni dieci minuti; prima del primo
    giro il watcher usa la regola del sorgente (`ha_vocabulary.has_statistics`).
    Una lettura fallita non tocca l'ultima buona (`Watcher.hold_statistic_ids`).
    """
    watcher = app.get("watcher")
    if watcher is None or ha_client is None:
        return
    watcher.hold_statistic_ids(await statistic_ids_for_round(app, ha_client))


def _record_attempt(store, outcome: dict, *, route: str = "ponte",
                    downgrade: str = "") -> None:
    """Annota com'e' andato il tentativo, **riuscito o no**.

    Prima dell'11/09/2026 un giro fallito non lasciava traccia da nessuna
    parte: la pagina dello scope mostrava «non e' mai stata fatta», che era
    vero alla lettera -- nessuna riconsiderazione era avvenuta -- e falso come
    racconto, perche' ci si era provato quattro volte in quaranta minuti
    mentre HIRIS non registrava piu' una riga sulla casa. Un guasto non si
    appiattisce su un'assenza.

    Non si scrive in `reconsideration`: un tentativo fallito non e' una
    riconsiderazione, e metterlo li' farebbe scadere la cadenza come se la
    casa fosse stata ripensata davvero.
    """
    # **Da quale porta e' passato il giro**, e se e' stato un ripiego: senza,
    # la pagina non puo' distinguere un giro servito dal piano da uno pagato a
    # consumo, e il prelievo resta invisibile (rilievo della review
    # indipendente, 11/09/2026; regola del proprietario del 13/08/2026).
    porta = f" [{route}{', ripiego: ' + downgrade if downgrade else ''}]"
    error = outcome.get("errore")
    if error:
        store.record_attempt(outcome=mind_store.ATTEMPT_FAILED, detail=error + porta,
                             version=read_version())
    else:
        # Il riassunto di un giro riuscito, nella lingua della pagina.
        summary = (f"{outcome.get('decise', 0)} decisioni su "
                   f"{outcome.get('candidate', 0)} entita' guardate")
        store.record_attempt(outcome=mind_store.ATTEMPT_DONE, detail=summary + porta,
                             version=read_version())


#: Quante entita' si chiedono in un turno solo. **Misurato dal vivo
#: l'11/09/2026**: 381 giudizi in una domanda sola producono ~30 KB di
#: risposta (~8.000 token) e la CLI del piano viene uccisa dal tetto di 300
#: secondi del sottoprocesso -- `claude non eseguibile: TimeoutExpired`, due
#: volte, l'ultima alle 15:44:12 esatte, 300 secondi netti dopo
#: l'accodamento. Nessun consumo registrato, perche' il turno non finisce mai.
#:
#: **Cento righe, misurate dal vivo l'11/09/2026 alle 18:13:27**: 15.852 token
#: in uscita e **2 minuti e 5 secondi** di CLI -- il primo turno
#: dell'osservatore arrivato in fondo su questa casa. Sono ~158 token a
#: entita', non i ~20 che avevo stimato: su 381 sarebbero stati ~60.000 token,
#: cioe' non un turno lento ma un muro. Il lotto non e' prudenza, e' la
#: condizione perche' la domanda abbia una risposta.
#:
#: Restano due minuti e mezzo di margine sul tetto. Non e' molto, e il numero
#: giusto dipende da quanto e' prolisso il modello: se una casa lo vedesse
#: scadere, questo e' il primo valore da abbassare.
SCOPE_BATCH = 100


#: Quanto si aspetta prima di riprovare, dopo un fallimento: `RETRY_BASE_S`,
#: che raddoppia a ogni fallimento di fila e si ferma a `RETRY_MAX_S` (vedi
#: `_retry_hold`).
RETRY_BASE_S = 600.0


RETRY_MAX_S = 6 * 3600.0


def _retry_hold(store, *, now: float) -> bool:
    """Se il freno e' tirato: **si e' appena fallito, e si aspetta**.

    Senza, un osservatore che fallisce stabilmente chiede al piano a ogni
    passaggio, per sempre -- e siccome `count_exchanges_today` conta ogni
    specie contro lo stesso tetto (`ponte.tetto_giornaliero`), **svuota
    da solo il tetto giornaliero**: da li' in poi anche la chat scende ai
    provider a pagamento. Il freno non spegne niente, rallenta: un guasto che
    passa da solo dev'essere comunque scoperto.

    Si legge dai tentativi, che sono gia' l'archivio di questo fatto: un
    contatore a parte sarebbe un doppione che il primo riavvio azzera.
    """
    # **Un aggiornamento e' un fatto nuovo.** I fallimenti di una versione
    # precedente riguardavano un altro programma, e contarli fa ritardare la
    # verifica della riparazione che li ha tolti: misurato l'11/09/2026,
    # quattro fallimenti sulla 3.27.0 hanno tenuto fermo l'osservatore per
    # ottanta minuti dopo l'aggiornamento alla 3.27.1. Le righe piu' vecchie
    # della colonna portano `None` e non contano: e' vero, non si sa su quale
    # versione siano avvenute.
    versione = read_version()
    attempts = [a for a in store.recent_attempts() if a["versione"] == versione]
    consecutive = 0
    for attempt in attempts:
        if mind_store.attempt_out(attempt)["in_attesa"]:
            continue
        if mind_store.attempt_out(attempt)["guasto"]:
            consecutive += 1
            continue
        break
    if not consecutive:
        return False
    wait = min(RETRY_BASE_S * 2 ** (consecutive - 1), RETRY_MAX_S)
    return now - attempts[0]["quando_ts"] < wait


def _to_judge(store, candidates: list[str], last: dict | None) -> list[str]:
    """I soggetti che questa campagna deve ancora giudicare, **dal piu'
    vecchio**: prima quelli su cui nessuno ha mai deciso, poi quelli decisi
    prima che la campagna cominciasse.

    L'ordine non e' estetico: e' cio' che garantisce che quattro lotti da cento
    coprano la casa invece di ripescare sempre gli stessi.
    """
    scope = store.scope()
    mai = [c for c in candidates if c not in scope]
    vecchi = [c for c in candidates
              if c in scope and last is not None
              and (scope[c]["quando"] or 0) <= last["quando_ts"]]
    vecchi.sort(key=lambda c: scope[c]["quando"] or 0)
    return mai + vecchi


def _collect_scope_turn(app, store, house: House) -> tuple[dict | None, bool]:
    """La risposta che il piano ha dato al turno di scope, e **se si e'
    letta**: `(esito, letto)`.

    Il secondo valore non e' una comodita': distingue «non c'era niente da
    raccogliere» da «si e' raccolto e non si e' potuto usare». Il secondo caso
    chiude il passaggio -- si riprova al giro dopo, col freno -- e senza questa
    distinzione il chiamante riaccodarebbe subito, che e' il difetto che la
    review indipendente ha misurato in turni al giorno.

    **La misura viaggia nella sveglia del job.** La sonda della memoria di
    Home Assistant si cala quando la domanda parte; la riconsiderazione si
    scrive quando la risposta torna, e fra i due momenti ci sono minuti e un
    altro processo. `submit` azzera il contesto (che porta la casa intera) e
    **non** la sveglia: e' li' che il numero aspetta, invece di essere
    rimisurato -- pagando due volte una cosa che non e' cambiata -- o perso,
    lasciando una finestra «non misurata» indistinguibile da una casa che non
    ricorda niente.

    **Un turno gia' letto non si rilegge**, e il confronto e' con **due**
    tracce, non una: la riconsiderazione, che una raccolta riuscita scrive, e
    il tentativo, che si scrive in ogni caso. La seconda serve proprio quando
    la prima manca -- una risposta inservibile non produce nessuna
    riconsiderazione, quindi guardando solo quella lo stesso turno storto
    verrebbe riletto e riannotato a ogni giro, gonfiando il «sta fallendo da...»
    con tentativi fantasma tutti sulla stessa risposta (rilievo della review
    indipendente, 11/09/2026).
    """
    queue = app.get("reasoning_queue")
    if queue is None:
        return None, False
    turn = queue.latest_if_decided(SCOPE_TURN_KIND)
    if turn is None:
        return None, False
    last = store.last_reconsideration()
    if last is not None and last["quando_ts"] >= turn["created_ts"]:
        return None, False
    # Si guarda l'ultimo tentativo che **non** sia un accodamento: «accodata»
    # si scrive quando la domanda parte, cioe' sempre PRIMA della risposta, e
    # confrontarlo con l'istante della risposta direbbe sempre di no. Cio' che
    # risponde davvero a «questa risposta l'ho gia' letta?» e' l'esito della
    # lettura.
    decided_ts = turn.get("decided_ts")
    letti = [a for a in store.recent_attempts() if a["esito"] != mind_store.ATTEMPT_QUEUED]
    if decided_ts is not None and letti and letti[0]["quando_ts"] >= decided_ts:
        return None, False
    reply = turn_answer(turn)
    wake = turn.get("wake") or {}
    lotto = wake.get("lotto")
    outcome = observer_apply_answer(
        store, house, reply,
        reason=wake.get("motivo") or "il piano ha risposto",
        window_s=wake.get("finestra_s"), cadence_s=wake.get("cadenza_s"),
        asked=set(lotto) if lotto else None,
        record=bool(wake.get("annota", True)),
        campaign_ts=wake.get("campagna_ts"))
    _record_attempt(store, outcome)
    # **Il registro degli esiti e' il solo posto in cui HIRIS osserva come si
    # comporta un fornitore davvero**, e la terza strada del piano non ci
    # finiva: la pagina Modelli non avrebbe mai saputo che l'abbonamento ha
    # servito -- o mancato -- un turno dell'osservatore (rilievo della review
    # indipendente, 11/09/2026). La chat lo fa in `_submit_chat_reply`, la
    # promessa nella rotta MCP.
    registry = app.get("occurrence_registry")
    if registry is not None:
        if "errore" in outcome:
            registry.fallimento(SUBSCRIPTION.id, family="altro", code=None,
                                message=outcome["errore"], durata_s=0.0)
        else:
            registry.successo(SUBSCRIPTION.id)
    if "errore" in outcome:
        logger.warning("osservatore: la risposta del piano non si e' potuta "
                       "usare (%s) -- si riprova al giro dopo", outcome["errore"])
        return None, True
    logger.info("osservatore: giro finito dal piano -- %s", outcome)
    return outcome, True


def _enqueue_scope_turn(app, store, house: House, *, reason: str,
                        window_s: float | None, lotto: set[str],
                        annota: bool, campagna_ts: float) -> dict:
    """Accoda al piano il turno dell'osservatore, e torna subito.

    La scadenza viene dall'ARCHIVIO (`ponte.scadenza_min`), come per la chat e
    per le promesse: quella che l'utente cambia dev'essere quella che il turno
    subisce, e una terza fonte per lo stesso numero sarebbe la terza che
    diverge.
    """
    now = time.time()
    _job_id, deadline_min = enqueue_turn(
        app, OBSERVER_SPECIES,
        # **La sveglia porta anche il LOTTO e se questo turno apre la
        # campagna.** Il ponte risponde minuti dopo, da un altro processo: chi
        # raccoglie deve sapere di che cosa era stata fatta la domanda, o non
        # potrebbe ne' accorgersi delle omissioni ne' decidere se annotare la
        # riconsiderazione. `submit` azzera il contesto e **non** la sveglia.
        {"motivo": reason, "finestra_s": window_s,
         "cadenza_s": cadence_from(window_s),
         "lotto": sorted(lotto), "annota": annota, "campagna_ts": campagna_ts},
        observer_bridge_turn(store, house, lotto, opening=annota), now=now)
    # **«Ho chiesto e sto aspettando» e' il terzo stato**, e la pagina deve
    # poterlo dire: senza, qualche minuto di attesa legittima e'
    # indistinguibili da un guasto -- che e' precisamente la confusione da cui
    # questa fetta nasce.
    store.record_attempt(when_ts=now, outcome=mind_store.ATTEMPT_QUEUED,
                         detail=f"chiesto al piano: {reason}",
                         version=read_version())
    logger.info("osservatore: turno accodato al piano (scadenza %d min) -- %s",
                deadline_min, reason)
    return {"accodata": True}
