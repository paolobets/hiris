"""I **giri delle condizioni**: le condizioni di sistema e gli esiti delle
automazioni, letti da Home Assistant e consegnati al `watcher`.

Spostati da `server.py` senza una riga di logica cambiata (Chiusura dello
sprint, F8 passo 6, 14/10/2026): `server.py` registra e avvia, non ospita.
"""
import logging
import time

from aiohttp import web

from ..home_space.historian import instant_epoch
from ..home_space.house import House
from ..home_space.house_history import read_log, read_traces
from ..home_space.reader import HOME_SPACE_KEY
from ..home_space.rounds import HA_INTEGRATIONS_KEY, HA_PROBLEMS_KEY, reread_ha_problems
from ..keeper.delivery import align_notices, notify_admins
from ..proxy.entity_cache import ENTITY_CACHE_KEY, automation_config_id
from ..steering import OBSERVER_SPECIES
from . import stopped_integrations
from .store import OBSERVATIONS_KEY
from .watcher import WATCHER_KEY

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
TRACE_CURSORS_KEY = web.AppKey("automation_trace_cursors", dict)
TRACE_UNRESOLVED_KEY = web.AppKey("automation_trace_unresolved", set)
TRACES_BOOT_TS_KEY = web.AppKey("automation_traces_boot_ts")

logger = logging.getLogger(__name__)


async def watch_system_conditions(app, ha_client) -> int | None:
    """Le condizioni di sistema (problemi diagnosticati + integrazioni non
    caricate + voci del registro di errori) verso
    `app[WATCHER_KEY].watch_system` (fetta «l'osservatore», Task 5; il registro
    di errori e' Task 2 di «le tracce e il log»), e poi l'avviso delle
    integrazioni ferme (`mind/stopped_integrations.py`). Torna quante
    condizioni ha scritto, o `None` se il giro e' stato saltato.

    **I problemi NON si rileggono qui** (A-02, 03/10/2026): li legge gia' il
    giro dei cinque minuti (`reread_ha_problems`, `hiris_ha_problems`) verso
    `app[HA_PROBLEMS_KEY]`, e questo giro, ogni dieci, prende quelli -- vecchi
    al piu' cinque minuti dentro una cadenza di dieci. Fino a quel giorno
    `repairs/list_issues` si chiedeva due volte, ed era scritto qui sotto
    come «doppione tollerato». Se la chiave non c'e' ancora (un giro partito
    prima della prima lettura) si fa quella lettura, una volta, e resta in
    `app[HA_PROBLEMS_KEY]` per tutti.

    **Le integrazioni NON si leggono qui** (Task 7 della Tappa 2, decisione di
    Paolo del 03/10/2026, «avviso»): arrivano per evento, dall'iscrizione
    `config_entries/subscribe` (`integration_follower`), in
    `app[HA_INTEGRATIONS_KEY]` e nell'anagrafe. Fino a quel giorno questo giro le
    rileggeva (`read_registry("integrazioni")`, Task 5) e le consegnava
    all'anagrafe ogni dieci minuti: una seconda lettura della stessa cosa,
    vecchia fino a un giro. Se l'elenco non e' ancora arrivato (l'iscrizione
    non ha ancora risposto), il giro si salta come per una lettura fallita.

    **Se una delle TRE letture fallisce, il giro si salta INTERAMENTE**
    (`task-5-correzioni.md`, punto A.1 -- la stessa disciplina, estesa al
    registro di errori). `HAClient.problems()` torna la busta del guasto
    quando Home Assistant non risponde, e il suo docstring dice perche' un
    elenco vuoto non e' un ripiego accettabile: significherebbe «non c'e'
    niente che non va». `HAClient.system_log()` dichiara la stessa cosa per la
    stessa ragione (vedi il suo docstring). `Watcher.watch_system` chiude una
    condizione dopo DUE giri consecutivi in cui non la trova piu' nell'elenco
    che riceve (l'isteresi contro i buchi di un giro solo, misurati il 03/09)
    -- quindi un errore letto come lista vuota, ripetuto per due giri di
    fila, scriverebbe comunque «chiuso» su OGNI guasto aperto (una voce di
    log compresa): l'archivio registrerebbe che tutto si e' risolto nel
    momento esatto in cui abbiamo smesso di poterlo vedere.
    Vale identico per le integrazioni: un elenco che l'iscrizione non ha
    ancora mandato manca, non e' un elenco vuoto che direbbe «va tutto bene».
    Meglio un buco nella storia che una bugia nella storia.

    Chiamata una volta all'avvio (subito dopo `rebuild_conditions`) e
    ogni dieci minuti dal lavoro periodico registrato piu' sotto in
    `_on_startup` -- stessa funzione, due chiamanti, come
    `tree_comparison_round`/`watch_behavior` qui accanto.

    Non solleva mai per le tre letture (i client la dichiarano gia' cosi'):
    puo' sollevare da `watch_system` stesso, se `record` fallisce a meta' --
    e in quel caso deve propagare, per il motivo scritto sul suo docstring.
    """
    watcher = app.get(WATCHER_KEY)
    if watcher is None:
        return None
    problems_report = app[HA_PROBLEMS_KEY].value
    if problems_report is None:
        problems_report = await reread_ha_problems(app, ha_client)
    if not isinstance(problems_report, dict) or "errore" in problems_report:
        logger.warning(
            "cervello: condizioni di sistema non lette, i problemi non sono "
            "stati letti (%s) -- giro saltato",
            problems_report.get("errore") if isinstance(problems_report, dict)
            else "nessun lettore")
        return None
    integrations = app[HA_INTEGRATIONS_KEY].value
    if integrations is None:
        logger.warning(
            "cervello: condizioni di sistema non lette, l'elenco delle "
            "integrazioni non e' ancora arrivato dall'iscrizione "
            "(config_entries/subscribe) -- giro saltato")
        return None
    log_report = await read_log(ha_client)
    if "errore" in log_report:
        logger.warning(
            "cervello: condizioni di sistema non lette, il registro degli errori ha "
            "fallito (%s) -- giro saltato", log_report["errore"])
        return None
    written = watcher.watch_system(
        problems=problems_report.get("problemi") or [],
        integrations=list(integrations),
        log_entries=log_report.get("voci") or [])
    # L'avviso delle integrazioni ferme (16/10/2026): sulle stesse righe che
    # l'osservatore ha appena annotato, dopo di lui -- se `record` solleva a
    # meta', non si avvisa di cio' che l'archivio non ha scritto.
    store = app.get(OBSERVATIONS_KEY)
    if store is not None:
        await stopped_integrations.tell(
            store, House.read(app.get(HOME_SPACE_KEY), app.get(ENTITY_CACHE_KEY)),
            list(integrations),
            notify=lambda text: notify_admins(app, text, actor=OBSERVER_SPECIES),
            show=lambda wanted: align_notices(app, stopped_integrations.NOTICE_ID,
                                              wanted, actor=OBSERVER_SPECIES),
            now=time.time())
    return written


async def watch_automation_outcomes(app, ha_client) -> int | None:
    """La cadenza BREVE (due minuti -- vedi il commento sul lavoro in
    `_on_startup` per il perche' di questo numero) verso
    `app[WATCHER_KEY].watch_automation_outcome` (Task 4 di «le tracce e il
    log»): rilegge le tracce di ogni automazione che l'evento ha SEGNATO
    (`Watcher.mark_automation`, sottoscritto piu' sopra in `_on_startup`) e
    scrive un cambio quando un'esecuzione e' in errore o quando un'esecuzione
    riuscita chiude un errore aperto in precedenza. Torna quante ne ha
    scritte, o `None` se il giro e' stato saltato per intero (nessun
    `watcher` -- boot non ancora arrivato li').

    **L'evento porta un `entity_id`, Home Assistant archivia le tracce per
    id di CONFIGURAZIONE: la risoluzione avviene qui.** `automation_
    triggered` nomina l'automazione con il suo `entity_id`, ed e' quello che
    `Watcher.marked_automations()` restituisce; ma la chiave con cui HA
    archivia le tracce e' `automation.<id della configurazione>`
    (`config_block.get(CONF_ID)`, catena verificata sui tag `2024.7.0` e
    `2026.9.0` nel docstring di `HAClient.traces()`). Su una casa
    vera i due valori non coincidono quasi mai -- l'interfaccia di HA genera
    id numerici come `"1771346155970"` -- e chiedere le tracce con
    l'`object_id` non ne sbaglia una: non ne legge MAI nessuna, per nessuna
    automazione. La traduzione sta QUI e non dentro il client (che resta
    «legge e non giudica», senza dipendere dallo stato): la fa
    `proxy/entity_cache.automation_config_id`, che legge lo specchio gia'
    cablato in `app[ENTITY_CACHE_KEY]` -- nessuna lettura nuova verso Home
    Assistant, nessun secondo rubinetto.

    **Un id che non si risolve NON e' «non ha mai girato».** Se lo specchio
    non e' pronto, o l'automazione e' scritta in YAML senza `id:` (allora
    `attributes["id"]` non esiste proprio, e le sue tracce vivono sotto la
    chiave condivisa `"automation.None"`, non indirizzabile per automazione),
    questa funzione **salta quell'automazione senza toccarne il cursore e
    senza scrivere nessun fatto**, e lo dice. Scrivere sarebbe
    un'affermazione su una casa che non abbiamo potuto guardare -- la stessa
    disciplina del «meglio un buco nella storia che una bugia nella storia»
    gia' applicata alle tracce anteriori all'avvio.

    **Lo dice UNA volta per entita' a voce alta, poi sottovoce.**
    `Watcher.marked_automations()` non si svuota mai: un'automazione YAML
    senza `id:` che e' scattata una volta resta segnata per tutta la vita del
    processo, e un WARNING a ogni cadenza sarebbero 720 avvisi al giorno per
    una condizione che non puo' cambiare a caldo. Il primo giro che non
    risolve una certa entita' logga WARNING, i successivi DEBUG
    (`app[TRACE_UNRESOLVED_KEY]`, l'insieme delle entita' gia'
    segnalate). Il fatto non si tace: cambia di livello. L'insieme e'
    limitato da quello dei segnati, quindi non cresce da solo, e un'entita'
    che torna a risolversi ne ESCE -- cosi' un guasto nuovo, dopo un periodo
    di normalita', si fa sentire di nuovo invece di restare muto per sempre.

    **Una raffica sola per tutte, e ogni automazione fallisce da sola.**
    Ogni `entity_id` segnato si risolve nel proprio id di configurazione
    (vedi il blocco qui sopra), e gli id risolti partono insieme in
    `HAClient.traces()` -- una connessione per giro, non una per
    automazione (A-21 e A-32, Tappa 2, Task 8: fino al 04/10/2026 ogni
    automazione segnata era una connessione sua, ogni due minuti). Al
    client non arriva mai un `entity_id`. Una chiave che Home Assistant
    rifiuta, o che non risponde in tempo, sta in `non_letti` e non deve
    impedire di leggere le altre: si salta QUELLA automazione, si continua
    con le prossime -- il "parziale tollerato", non il "tutto o niente"
    delle tre letture di sistema di `watch_system_conditions`. Se non parte
    la raffica intera, il giro si salta tutto, senza toccare nessun
    cursore.

    **Il cursore per automazione, e perche' esiste (giro di correzioni,
    rilievo 1 -- CRITICO, dimostrato dal revisore col `Watcher` vero).**
    `HAClient.traces()` non toglie mai una traccia dalla sua
    risposta finche' HA non la espelle da solo (tetto `stored_traces`):
    senza un cursore, OGNI giro di due minuti rivedrebbe ancora una volta
    OGNI traccia ancora conservata, e `watch_automation_outcome` decide
    solo «e' aperto adesso?» -- non «l'ho gia' vista?». Misurato dal
    revisore su tre finestre fisse: `[finished, error]` scrive 1 alla
    prima lettura e **2 a OGNI lettura successiva** (il `finished` non
    aveva niente da chiudere la prima volta -- l'errore non era ancora
    aperto -- ma lo richiude e lo riapre a ogni giro dopo, perche'
    rivisto sempre nello stesso ordine); un'automazione rotta una volta e
    guarita produce un episodio di guasto NUOVO ogni due minuti (720 al
    giorno), «una bugia nella storia» ripetuta. Il cursore
    (`app[TRACE_CURSORS_KEY]`, `entity_id -> {run_id gia'
    processati}`) **si sostituisce** con l'insieme del giro corrente, non
    si accumula: resta quindi limitato dal tetto che HA stesso impone
    alle tracce conservate, non cresce mai da solo.

    Due cautele, entrambe verificate alla fonte:

    - **una traccia ANCORA IN CORSO non entra nel cursore.**
      `ActionTrace._script_execution` (`trace/models.py`, tag `2026.9.0`)
      resta `None` finche' `finished()` non viene chiamato: una lettura
      che arriva a meta' esecuzione vede `script_execution: None` (non una
      stringa) e non ha ancora un esito da giudicare. Se la marcassimo
      "vista" comunque, il giro in cui si conclude troverebbe il suo
      `run_id` gia' nel cursore e il suo esito vero non arriverebbe MAI.
    - **una traccia con `timestamp.start` precedente all'avvio di questo
      processo non produce un fatto** (ma ENTRA nel cursore: e'
      permanentemente fuori scope, non "da riconsiderare"). E' scattata
      mentre HIRIS era spento, o in un avvio precedente -- non si
      recupera, stessa disciplina di `watch_system_conditions` ("meglio un
      buco nella storia che una bugia nella storia"). `timestamp.start` e'
      un `datetime` di HA serializzato ISO-8601 (`helpers/json.py`,
      `JSONEncoder.default`: `datetime.datetime -> o.isoformat()`) --
      `instant_epoch` lo legge gia' cosi'. **Conseguenza dichiarata**: se
      un'automazione era rotta prima del riavvio dell'add-on, il suo
      episodio resta APERTO finche' non gira bene di nuovo -- un buco
      nella storia, non una bugia.

    Una traccia il cui `script_execution` non e' una stringa (l'unico
    caso vero e' quello in corso qui sopra: **non** `not_triggered`, che
    da HA 2026.7.0 in poi vale la stringa `"not_triggered"` -- verificato
    alla fonte, `automation/__init__.py::_handle_not_triggered`,
    `script_execution_set("not_triggered")`, assente prima di quel tag --
    e su una `not_triggered` questa funzione la inoltra comunque a
    `watch_automation_outcome`, che la ignora perche' non e' ne' `"error"`
    ne' `"finished"`) si scarta senza processarla.

    **L'ordine delle tracce dentro `tracce` conta, ed e' gia' quello
    giusto.** Verificato alla fonte (`homeassistant/util/limited_size_
    dict.py`, `LimitedSizeDict._check_size_limit`: evizione FIFO via
    `popitem(last=False)`; `trace/util.py::async_store_trace`:
    `bucket[trace.run_id] = trace`, che in un `OrderedDict` appende in
    coda) -- la lista che `traces()` restituisce per una chiave e' dal PIU'
    VECCHIO al piu' recente. Processarla in quest'ordine, chiamando
    `watch_automation_outcome` una volta per traccia NUOVA (secondo il
    cursore), fa si' che l'ultima chiamata rifletta sempre l'esito piu'
    recente -- se un'automazione ha fallito e poi e' guarita nella STESSA
    finestra di due minuti, l'errore apre e il successo lo richiude nello
    stesso giro, nell'ordine vero.

    `outcome` e' `script_execution` cosi' come HA lo scrive (`"finished"`,
    `"error"`, `"failed_conditions"`, ...): questa funzione non lo giudica,
    lo passa cosi' com'e' -- il giudizio (quale valore apre, quale chiude,
    quale non fa niente) vive tutto in `Watcher.watch_automation_outcome`.
    `title` e' il nome che la casa da' all'automazione ADESSO (`House.name`,
    D1: quello che si vede in Home Assistant; A-18, Tappa 3, Task 12) --
    fino al 04/10/2026 era quello che l'evento portava al primo scatto, e
    non seguiva le rinomine. Un'automazione che la casa sa nominare solo con
    l'id viaggia senza titolo, come prima senza nome. Viaggia identico a
    ogni chiamata per la stessa automazione: e' il metodo che decide se
    scriverlo (solo sull'apertura), non questa funzione.

    Non solleva mai per la lettura delle tracce (`traces()` la dichiara
    gia' cosi', vedi il suo docstring): un guasto di rete per
    un'automazione diventa un WARNING e un `continue`, non un'eccezione che
    fermerebbe le altre. Se la lettura fallisce, il cursore di
    QUELL'automazione non si tocca -- resta quello dell'ultimo giro
    riuscito, invece di essere azzerato da una risposta che non e' mai
    arrivata.
    """
    watcher = app.get(WATCHER_KEY)
    if watcher is None:
        return None
    boot_ts = app.get(TRACES_BOOT_TS_KEY, 0.0)
    cursors = app[TRACE_CURSORS_KEY]
    cache = app.get(ENTITY_CACHE_KEY)
    unresolved = app[TRACE_UNRESOLVED_KEY]
    written = 0
    # Prima si risolvono tutte, poi si chiede UNA volta (A-21, Tappa 2, Task
    # 8): fino al 04/10/2026 ogni automazione segnata era una lettura sua,
    # cioe' una connessione WebSocket nuova ogni due minuti per ognuna.
    resolved: list[tuple[str, str]] = []
    for entity_id in watcher.marked_automations():
        automation_id = automation_config_id(cache, entity_id)
        if automation_id is None:
            # NON si tocca il cursore, e NON si scrive nessun fatto: un id
            # irrisolto non e' «non ha mai girato», e' «non ho potuto
            # guardare». Si salta questa automazione come si salta una
            # lettura fallita, e le altre proseguono.
            #
            # WARNING la PRIMA volta per entita', poi DEBUG. `_marked_
            # automations` non si svuota mai, quindi un'automazione YAML
            # senza `id:` che e' scattata una volta resterebbe segnata per
            # tutta la vita del processo: un avviso ogni due minuti, 720 al
            # giorno, per una condizione che non puo' cambiare a caldo. La
            # legge del prodotto -- «se una cosa funziona non va segnalata,
            # il rumore sano seppellisce la rotta» -- vale anche per i log:
            # un WARNING ripetuto per sempre smette di essere un avviso e
            # diventa lo sfondo davanti a cui gli avvisi veri spariscono.
            # Il fatto non si tace, cambia di livello.
            (logger.debug if entity_id in unresolved else logger.warning)(
                "cervello: l'id di configurazione di %s non si risolve dallo "
                "specchio (automazione senza `id:` in YAML, oppure inventario "
                "non ancora pronto) -- le sue tracce non si possono chiedere, "
                "questo giro la salta", entity_id)
            unresolved.add(entity_id)
            continue
        # Risolta: si dimentica di averla mai segnalata. Cosi' il WARNING e'
        # «la prima volta di OGNI tratto di irrisolvibilita'», non «la prima
        # volta in assoluto» -- un'automazione risolta oggi e irrisolvibile
        # domani (inventario ricaricato male, HA riavviato) torna a farsi
        # sentire una volta, invece di restare muta per sempre.
        unresolved.discard(entity_id)
        resolved.append((entity_id, automation_id))
    if not resolved:
        return written
    report = await read_traces(ha_client, list(dict.fromkeys(
        ("automation", automation_id) for _entity_id, automation_id in resolved)))
    # La casa di questo giro, per i nomi (A-18): letta una volta.
    house = House.read(app.get(HOME_SPACE_KEY), cache)
    if "errore" in report:
        # La raffica intera non e' partita: nessuna automazione si e' potuta
        # guardare, e nessun cursore si tocca.
        logger.warning("cervello: tracce delle automazioni segnate non lette "
                       "(%s) -- il giro si salta", report["errore"])
        return written
    for entity_id, automation_id in resolved:
        key = f"automation.{automation_id}"
        if key not in report["tracce"]:
            logger.warning(
                "cervello: tracce di %s (id di configurazione %s) non lette "
                "(%s) -- questa automazione si salta, le altre proseguono",
                entity_id, automation_id,
                report["non_letti"].get(key, "nessuna risposta"))
            continue
        already_seen = cursors.get(entity_id) or set()
        seen_this_round: set[str] = set()
        name = house.name("automazione", entity_id)
        title = None if name == entity_id else name
        for trace in report["tracce"][key]:
            if not isinstance(trace, dict):
                continue
            outcome = trace.get("script_execution")
            if not isinstance(outcome, str):
                # Ancora in corso (vedi il docstring): NON entra nel
                # cursore, o il suo esito vero non arriverebbe mai.
                continue
            run_id = trace.get("run_id")
            if not isinstance(run_id, str):
                continue
            seen_this_round.add(run_id)
            if run_id in already_seen:
                continue  # gia' processata in un giro precedente
            start_ts = instant_epoch((trace.get("timestamp") or {}).get("start"))
            if start_ts is not None and start_ts < boot_ts:
                continue  # prima dell'avvio: buco dichiarato, non si recupera
            if watcher.watch_automation_outcome(entity_id, outcome, title=title):
                written += 1
        cursors[entity_id] = seen_this_round
    return written
