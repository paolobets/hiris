"""I **giri della casa**: le riletture che tengono l'anagrafe, lo specchio e il
comportamento allineati a Home Assistant, e gli ascoltatori che le fanno
partire.

Spostati da `server.py` senza una riga di logica cambiata (Chiusura dello
sprint, F8 passo 6, 14/10/2026): `server.py` registra e avvia, non ospita.
"""
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from aiohttp import web

from ..background import spawn as _spawn
from ..live_value import LiveValue
from .behavior import reread, reread_dashboards
from .reader import HOME_SPACE_KEY
from .redaction import home_assistant_folder
from .topology import (
    AREAS_PER_ROUND,
    choose_sample,
    compare_with_home_assistant,
    hierarchy,
    tree_areas,
)

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
HA_INTEGRATIONS_KEY = web.AppKey("ha_integrations", LiveValue)
HA_PROBLEMS_KEY = web.AppKey("ha_problems", LiveValue)
TREE_COMPARISON_KEY = web.AppKey("tree_comparison", LiveValue)

logger = logging.getLogger(__name__)


async def reload_entity_inventory(cache, ha_client) -> bool:
    """Ritenta la rilettura dello specchio delle entita' quando l'ultima non e'
    riuscita: il caricamento iniziale, o la rilettura dopo una riconnessione
    (`EntityCache.stale`, A-09). Ritorna True se questo giro l'ha rimesso in
    piedi.

    `_on_startup` logga e prosegue quando `EntityCache.load` fallisce (Home
    Assistant che parte dopo l'addon, riavvio del core, rete che balbetta):
    da li' in poi la cache resta `loaded is False` e gli strumenti che
    la leggono rispondono "non ancora pronto". Onesto, ma senza qualcuno che
    riprovi resterebbe cosi' fino al riavvio dell'addon: piu' onesto di prima
    e piu' scomodo. Questo e' quel qualcuno.

    **Anche la rilettura della riconnessione, dal 03/10/2026** (A-09): dopo un
    riavvio di Home Assistant lo specchio rilegge la casa (`reload`), e se in
    quel momento Home Assistant non risponde ancora lo specchio resta quello
    di prima -- leggibile, ma senza gli eventi di quando la connessione era
    giu'. Fino a quel giorno questo giro guardava solo `loaded`, ed era vero:
    lo specchio restava vecchio fino alla riconnessione successiva.

    Non tocca una cache viva e fresca: da quel momento la mantengono
    aggiornata gli eventi di stato, e rileggere tutta la casa a ogni giro
    sarebbe traffico inutile verso Home Assistant. Modulo-level (non chiuso dentro
    `_on_startup`) per essere unit-testabile con un semplice dict al posto
    di `app`: si prova senza avviare l'applicazione.

    Non solleva mai: gira nello scheduler, e un Home Assistant ancora giu' e'
    il caso previsto, non un errore da propagare -- il giro successivo
    riprovera'.
    """
    if cache is None or ha_client is None:
        return False
    if cache.loaded and not cache.stale:
        return False
    try:
        await cache.load(ha_client)
    except Exception as exc:
        logger.warning("Ricarica dell'inventario entita' non riuscita: %s", exc)
        return False
    logger.info(
        "Inventario entita' ricaricato: %d entita' (l'ultima lettura era fallita)",
        len(cache.all_states()) if hasattr(cache, "all_states") else -1,
    )
    # Qui c'erano due chiamate WebSocket per ricostruire una mappa area->entita'
    # che nessuno leggeva, e che sbagliava (per nome invece che per id, senza
    # l'area ereditata dal dispositivo). Le aree le ricostruisce
    # `home_space.topology.rebuild`, che le legge per id e dichiara i registri
    # caduti.
    return True


async def reread_ha_problems(app, ha_client) -> dict | None:
    """Rilegge i guasti che Home Assistant ha gia' diagnosticato e li mette in
    `app["ha_problems"]`. Ritorna cio' che ha scritto (`None` senza client).

    DOVE VIVONO I PROBLEMI, e perche' qui e non dentro l'anagrafe
    (`HomeSpace`, `home_space/reader.py`).

    Un `repair` e' momentaneo. L'utente apre Home Assistant, clicca «ripara»,
    e quel problema non esiste piu': un'anagrafe riletta solo quando i
    registri cambiano continuerebbe ad annunciarlo per ore -- e un falso
    allarme ripetuto in ogni prompt e' precisamente il rumore che questa
    lettura esiste per non produrre. E' lo stesso ragionamento, sullo stesso
    genere di dato, per cui `state` non entra nel sistema di riferimento della
    casa (`home_space.topology.reference_frame`: «in un archivio che si
    rilegge di rado mentirebbe poche ore dopo, ed e' peggio che non saperlo»).

    C'e' anche una ragione meccanica, e da sola basterebbe: l'anagrafe si
    ricostruisce sugli eventi dei REGISTRI (`TOPOLOGY_EVENTS`), e il registro
    dei problemi non ne emette nessuno. Messo nell'anagrafe, nessun innesco lo
    aggiornerebbe: sarebbe un dato letto all'avvio e vecchio da li' in poi.

    Quindi in `app`, accanto a `entity_cache` -- che e' l'altra fotografia
    momentanea del prodotto -- e riletta da un lavoro periodico
    (`hiris_ha_problems`): il costo e' un solo comando WebSocket, e un guasto
    riparato sparisce dal nucleo entro il giro successivo invece che al
    riavvio dell'add-on.

    La strada migliore esisterebbe: Home Assistant emette
    `repairs_issue_registry_updated`, e ascoltarlo renderebbe il numero esatto
    invece che fresco di cinque minuti. Sottoscriverlo pero' vuol dire toccare
    `proxy/ha_client.py` (le sottoscrizioni si aprono tutte li', in `_ws_loop`),
    che questa fetta non possiede. Resta la prima cosa da fare quando quel file
    si riapre; la lettura periodica non andra' buttata, e' il ripiego che copre
    un HA che si riavvia e perde le sottoscrizioni.

    Non solleva mai: `HAClient.problems()` restituisce gia' `{"errore": ...}`
    sui guasti, e quell'errore e' un'informazione da portare al modello, non
    un'eccezione da propagare in uno schedulatore.
    """
    if ha_client is None:
        return None
    reader = getattr(ha_client, "problems", None)
    if reader is None:
        # Un client vecchio o un finto di prova che non dichiara `problemi`:
        # non si scrive niente, cosi' `app["ha_problems"]` resta `None` e il
        # nucleo tace invece di affermare che la casa e' sana.
        return None
    try:
        report = await reader()
    except Exception as exc:  # non previsto: `problems()` cattura gia' da se'
        logger.warning("lettura dei problemi diagnosticati da HA fallita: %s", exc)
        report = {"errore": "Home Assistant non ha risposto"}
    app[HA_PROBLEMS_KEY].set(report)
    return report


def integration_follower(app):
    """Restituisce l'ascoltatore dell'iscrizione alle integrazioni
    (`HAClient.add_integration_listener`, Task 7 della Tappa 2): riceve i
    cambi cosi' come Home Assistant li manda e tiene le voci in
    `app["ha_integrations"]` -- le righe grezze, la stessa forma di
    `config_entries/get` (`ConfigEntry.as_json_fragment`, vedi
    `CONFIG_ENTRIES_SUBSCRIPTION` in `proxy/ha_client.py`) -- e nell'anagrafe,
    con lo stesso costruttore della ricostruzione
    (`HomeSpace.hold_integrations`).

    **Dove vivono, e perche' due posti.** `app["ha_integrations"]` e' il
    grezzo che il giro delle condizioni passa all'osservatore
    (`Watcher.watch_system` legge `state`, `source`, `domain`, `title` di
    Home Assistant), accanto ad `app["ha_problems"]` che e' la stessa specie
    di dato; l'anagrafe ne tiene la forma di HIRIS (`dominio`, `stato`,
    `motivo`), come per ogni altra tabella. L'ascoltatore non ha una memoria
    sua: il suo stato E' `app["ha_integrations"]`.

    **L'elenco intero sostituisce, i cambi si applicano.** Un messaggio con
    voci a `type` nullo -- o vuoto: una casa senza integrazioni -- e' l'elenco
    iniziale, che l'iscrizione manda a ogni connessione: sostituisce cio' che
    si sapeva, cosi' una voce tolta mentre la connessione era giu' sparisce
    alla riconnessione. `added`/`updated` mettono la voce al suo posto per
    `entry_id`, `removed` la toglie. Un cambio arrivato prima di un elenco
    (Home Assistant non lo fa: conferma, poi manda l'elenco) si ignora: un
    elenco fatto di soli cambi direbbe che la casa ha una integrazione sola.

    **Cosa NON copre, dichiarato.** Anche la ricostruzione dell'anagrafe
    (`topology.rebuild`) legge le integrazioni, con tutti i registri; se un
    annuncio arriva fra la sua lettura e la sua consegna, l'anagrafe tiene la
    lettura fino al prossimo annuncio. `app["ha_integrations"]` no: lo scrive
    solo l'iscrizione.
    """
    def follow(changes) -> None:
        if not isinstance(changes, list):
            return
        listing = not changes or any(
            isinstance(change, dict) and change.get("type") is None for change in changes)
        if not listing and app[HA_INTEGRATIONS_KEY].value is None:
            logger.debug("integrazioni: un cambio prima dell'elenco iniziale, ignorato")
            return
        entries = {} if listing else {
            row.get("entry_id"): row for row in app[HA_INTEGRATIONS_KEY].value}
        for change in changes:
            entry = change.get("entry") if isinstance(change, dict) else None
            if not isinstance(entry, dict) or not entry.get("entry_id"):
                continue
            if change.get("type") == "removed":
                entries.pop(entry["entry_id"], None)
            else:
                entries[entry["entry_id"]] = entry
        rows = list(entries.values())
        app[HA_INTEGRATIONS_KEY].set(rows)
        home_space_store = app.get(HOME_SPACE_KEY)
        if home_space_store is not None:
            home_space_store.hold_integrations(rows)

    return follow


def tree_comparison_round(app, ha_client, count: int = AREAS_PER_ROUND):
    """Restituisce `giro()`: confronta un CAMPIONE di aree con Home Assistant
    e scrive l'esito in `app["tree_comparison"]`.

    **Cosa fa, in una riga.** `home_space/topology.hierarchy()` e' una replica che
    HIRIS costruisce dai registri, cioe' un'affermazione sulla casa che niente
    verificava. Qui la stessa domanda va all'originale --
    `HAClient.extract_from_target({"area_id": [...]}) `, che e' Home Assistant
    a risolvere -- e le due liste si mettono una accanto all'altra
    (`topology.compare_with_home_assistant`, pura).

    **OGNI QUANTO, e perche' non a ogni ricostruzione dell'anagrafe.** La
    strada ovvia sarebbe agganciarsi alla ricostruzione. Sarebbe anche il
    momento sbagliato: subito dopo una ricostruzione la replica e' fresca di
    secondi, cioe' esattamente quando una divergenza e' meno probabile. Il
    caso che questa verifica esiste per prendere e' l'opposto -- un evento di
    registro perso, un Home Assistant riavviato senza che HIRIS se ne
    accorgesse, una replica che INVECCHIA -- e per vederlo bisogna guardare
    mentre la copia invecchia, non appena e' stata rifatta. Quindi un lavoro
    periodico, indipendente dalla ricostruzione: quindici minuti (vedi la
    registrazione nello schedulatore), che con `AREAS_PER_ROUND` a rotazione
    coprono una casa da sedici aree in poco piu' di un'ora.

    **DOVE VIVE L'ESITO.** In RAM, in `app["tree_comparison"]`, accanto a
    `app["ha_problems"]` e per la stessa ragione, gia' scritta per esteso su
    `reread_ha_problems`: un confronto e' momentaneo -- la casa cambia e la
    replica si rifa' da sola al primo evento di registro -- e un archivio
    riletto di rado continuerebbe ad annunciare per ore una divergenza gia'
    rientrata. E' lo stesso ragionamento per cui `state` non entra nel sistema
    di riferimento della casa (`home_space.topology.reference_frame`).

    Si tiene SOLO l'ultimo giro, non un archivio di verdetti che si accumula:
    cosi' ogni verdetto che il nucleo legge e' vecchio al massimo quanto la
    cadenza, e nessuna area resta marchiata da una divergenza riparata mezz'ora
    fa. Il prezzo -- si vedono tre aree per volta -- e' dichiarato dentro
    l'esito stesso (`aree_totali`) e detto in ogni frase che il nucleo scrive.

    **Non solleva mai**: `extract_from_target` risponde gia' `{"errore": ...}`
    sui guasti, e un'area che non si e' potuta leggere e' un'informazione da
    portare al modello -- non un'eccezione da propagare in uno schedulatore, e
    soprattutto non un'area che combacia.

    Lo stato della rotazione (`dopo`) vive in una chiusura e non in `app`: e'
    un dettaglio di questo lavoro, non un fatto sulla casa, e nessun altro ha
    motivo di leggerlo. Stessa forma di `behavior_reader` e di
    `schedule_registry_rebuild`.
    """
    state: dict[str, str | None] = {"dopo": None}

    async def run_round() -> dict | None:
        if ha_client is None:
            return None
        reader = getattr(ha_client, "extract_from_target", None)
        if reader is None:
            # Un client vecchio o un finto di prova che non dichiara il
            # comando: non si scrive niente, cosi' la chiave resta assente e
            # il nucleo tace invece di affermare che l'albero e' verificato.
            return None
        store = app.get(HOME_SPACE_KEY)
        if store is None:
            return None

        # Una lettura sola, e l'albero costruito una volta: il campione, le
        # domande a HA e il verdetto guardano tutti la STESSA fotografia della
        # replica. Ricostruirlo dopo le risposte vorrebbe dire confrontare un
        # albero con le risposte a domande fatte su un altro.
        home_space = store.read()
        piani = hierarchy(home_space, tuple(store.unavailable()))
        areas = tree_areas(piani)
        sample = choose_sample(areas, count, state["dopo"])

        answers: dict[str, dict] = {}
        for area in sample:
            try:
                answers[area["id"]] = await reader({"area_id": [area["id"]]})
            except Exception as exc:  # non previsto: il client cattura gia'
                logger.warning("confronto dell'area %s non riuscito: %s", area["id"], exc)
                answers[area["id"]] = {"errore": "Home Assistant non ha risposto"}
        if sample:
            state["dopo"] = sample[-1]["id"]

        report = compare_with_home_assistant(piani, home_space, answers)
        # La data la mette il chiamante: `compare_with_home_assistant` e'
        # pura, e una funzione pura che leggesse l'orologio non sarebbe piu'
        # confrontabile con se stessa. Serve a chi disegna l'albero
        # (`/api/home-space`) per dire quanto e' fresco il verdetto che sta
        # mostrando.
        report["letto_il"] = datetime.now(UTC).isoformat(timespec="seconds")
        app[TREE_COMPARISON_KEY].set(report)
        divergenti = sum(1 for g in report["guardate"] if g.get("mancanti") or g.get("in_piu")
                         or g.get("assente_in_ha"))
        if divergenti:
            logger.warning("confronto dell'albero: %d aree su %d guardate divergono da "
                           "Home Assistant", divergenti, len(report["guardate"]))
        return report

    return run_round


def schedule_dashboards_reread(client, store, delay: float = 3.0):
    """Restituisce `trigger(event_data)`: rilegge le plance, una volta sola.

    Gemello di `schedule_registry_rebuild` — stesso antirimbalzo,
    stessa tolleranza ai guasti — ma per un innesco DIVERSO (DASHBOARD_EVENT,
    non i registri): le plance non stanno in `reader.TABLES` e non vanno confuse con
    l'anagrafe, che questa funzione non tocca.
    """
    state: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(delay)
            await reread_dashboards(client, store)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("rilettura delle plance fallita: %s", exc)

    def trigger(event_data: dict) -> None:
        pending = state["attesa"]
        if pending is not None and not pending.done():
            pending.cancel()
        state["attesa"] = _spawn(_fra_poco(), name="rilettura_plance")

    return trigger


def behavior_reader(client, mirror, home_space, ha_folder: Path | None, find_folder=None):
    """Restituisce `look()`: rilegge il comportamento da Home Assistant.

    `mirror` e' lo specchio dello stato: dice QUALI automazioni e script ci
    sono, e il loro stato (A-03, 03/10/2026); a Home Assistant si chiede solo
    il corpo.

    **Non c'e' piu' niente da sorvegliare, e per questo non e' piu' una
    sentinella.** Fino al 10/09/2026 il comportamento veniva dai due file, e
    l'unico segnale di cambiamento era il loro `mtime`: per gli script Home
    Assistant non emette ALCUN evento di ricarica, quindi due `stat()` per giro
    erano il modo piu' economico di non rileggere a vuoto. Adesso la fonte e'
    Home Assistant, e l'impronta di quei file non dice piu' niente su cio' che
    HA ha caricato -- un'automazione dentro un pacchetto non li tocca affatto.

    Quindi si rilegge e basta: **misurato il 10/09/2026, venti configurazioni
    costano 66 ms** su una connessione sola. A cinque minuti di cadenza sono
    venti secondi di traffico al giorno -- lo stesso rumore di fondo dei
    registri, che si rileggono per intero in 80 ms.

    **La cartella si cerca ancora, e per una ragione sola**: `secrets.yaml`.
    E' la dichiarazione del proprietario su cosa sia segreto, non la espone
    nessuna API, e senza di essa i corpi non si archiviano (vedi
    `home_space/redaction.py`). Finche' non c'e' la si ricerca a ogni giro:
    l'add-on puo' partire prima che il Supervisor l'abbia montata, e
    risolverla una volta sola all'avvio significherebbe restare convinti per
    sempre che non ci sia niente da leggere.

    Restituisce `True` se ha riletto, `False` se la rilettura e' fallita.
    """
    found: dict[str, Path | None] = {"folder": ha_folder}
    _find = find_folder if find_folder is not None else home_assistant_folder

    def _folder() -> Path | None:
        if found["folder"] is None:
            appeared = _find()
            if appeared:
                found["folder"] = Path(appeared)
                logger.info("cartella di Home Assistant comparsa dopo l'avvio: %s",
                            found["folder"])
        return found["folder"]

    async def look() -> bool:
        """I due inneschi -- la cadenza e l'evento di registro -- rileggono
        entrambi allo stesso modo: non c'e' un confronto da scavalcare."""
        try:
            await reread(client, mirror, home_space, _folder())
        except Exception as exc:
            logger.warning("rilettura del comportamento fallita: %s", exc)
            return False
        return True

    return look


def schedule_behavior_reread(look, delay: float = 3.0):
    """Restituisce `trigger(event_type)`: rilegge il comportamento, una
    volta sola per raffica.

    Gemello di `schedule_registry_rebuild` -- stesso antirimbalzo,
    stessa tolleranza ai guasti, stesso evento (TOPOLOGY_EVENTS, via
    `add_topology_listener`: nessun meccanismo nuovo). Aggiungere o togliere
    un'automazione cambia il registro delle entita', e questo innesco fa
    rileggere subito invece di aspettare i cinque minuti della cadenza. Non
    e' un doppione di quella: e' la differenza fra vedere la propria
    automazione nuova adesso e vederla fra cinque minuti.
    """
    state: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(delay)
            await look()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("rilettura forzata del comportamento fallita: %s", exc)

    def trigger(event_type: str) -> None:
        pending = state["attesa"]
        if pending is not None and not pending.done():
            pending.cancel()
        state["attesa"] = _spawn(_fra_poco(), name="rilettura_comportamento")

    return trigger
