import asyncio
import logging
import re
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import quote

import aiohttp

# La forma di un entity_id (dominio.oggetto) vive una volta sola, nel
# vocabolario di Home Assistant (`ha_vocabulary.is_entity_id`): qui serve a
# rifiutare un entity_id ostile PRIMA di comporlo in un URL, ed e' una GUARDIA.
# Chi volesse allargarla per riconoscere di piu' altrove si fa la propria
# espressione: allentare questa e' una decisione di sicurezza.
from ..home_space.ha_vocabulary import LINK_NAME, domain_of, is_entity_id
from ._sanitize import sanitize_ha_value
from ._sanitize import truncate_with_marker as _truncate

# I registri che HIRIS replica. Prima se ne ascoltava UNO — quello delle
# entita' — e per giunta solo con action="create": rinomini, cambi d'area,
# disabilitazioni e cancellazioni passavano inosservati, e la casa che HIRIS
# credeva di conoscere si allontanava da quella vera in silenzio.
TOPOLOGY_EVENTS = (
    "area_registry_updated",
    "device_registry_updated",
    "entity_registry_updated",
    "floor_registry_updated",
    "label_registry_updated",
    "category_registry_updated",
    # Il sistema di riferimento della casa (unita', fuso, valuta, lingua) e'
    # una proprieta' della casa quanto le sue aree: sta qui, non in una quarta
    # famiglia di ascoltatori tutta per un evento solo. Chi cambia il fuso
    # orario o passa da metrico a imperiale cambia il significato di OGNI
    # valore che HIRIS legge -- senza questa riga HIRIS continuerebbe a
    # ragionare col riferimento di quando e' partito.
    "core_config_updated",
)

# I due eventi dei SERVIZI. Terza famiglia, separata dalle altre due per la
# stessa ragione per cui le plance sono separate dall'anagrafe: innescano una
# rilettura diversa. Un servizio nuovo non cambia la casa, e un'entita' nuova
# non cambia i servizi.
#
# Perche' esistono: `ServiceRegistry` si ricaricava SOLO a scadenza (300s), e
# per cinque minuti dopo l'installazione di un'integrazione HIRIS rifiutava i
# suoi servizi dicendo «non esiste in questa casa» -- una frase falsa detta con
# sicurezza. I nomi e i campi (`domain`, `service`) sono quelli dichiarati da
# Home Assistant su home-assistant.io/docs/configuration/events/.
SERVICE_EVENTS = ("service_registered", "service_removed")

# L'evento delle plance (Task 5): porta il PERCORSO di quella cambiata, ma
# innesca comunque una rilettura completa (sono poche, e la replica si rifa'
# invece di rattopparsi — vedi `behavior.reread_dashboards`). Deliberatamente FUORI da
# TOPOLOGY_EVENTS: quello innesca la ricostruzione dei *registri*, che e'
# un'altra cosa — le plance hanno un proprio ascoltatore.
DASHBOARD_EVENT = "lovelace_updated"

# L'evento che segna l'INIZIO delle azioni di un'automazione scattata (Task 4
# di «le tracce e il log»). Verificato alla fonte sui tag RILASCIATI che
# delimitano la finestra che `hiris/config.yaml:22` dichiara supportata
# (`2024.7.0`, il minimo) e la piu' recente vista finora (`2026.9.0`) --
# stesso corpo su entrambi, in `homeassistant/components/automation/
# __init__.py`: `EVENT_AUTOMATION_TRIGGERED = "automation_triggered"`,
# sparato da `started_action()`, una callback passata a
# `self.action_script.async_run(...)` ed eseguita quando le AZIONI
# COMINCIANO -- non quando finiscono. In quell'istante la traccia
# (`trace/get`) non e' ancora completa: l'evento non porta e non puo'
# portare un esito.
#
# Non scatta MAI per un'esecuzione le cui condizioni sono false: sulla stessa
# fonte, `script_execution_set("failed_conditions")` e il `return None` che
# la segue arrivano PRIMA che `event_data` sia costruito e prima che
# `started_action` sia definita -- una condizione falsa non genera l'evento,
# non solo non genera un fatto. Coerente con la legge del prodotto (spec §8,
# la spazzata larga uscita dal piano il 05/09): una condizione falsa e'
# funzionamento, non un guasto.
#
# `event_data` porta `{ATTR_NAME: self.name, ATTR_ENTITY_ID: self.entity_id}`
# (piu' `ATTR_SOURCE`, non usato qui) -- identico sui due tag: l'`entity_id`
# c'e' sempre, ed e' sempre quello dell'automazione che e' scattata.
AUTOMATION_TRIGGERED_EVENT = "automation_triggered"

# L'iscrizione alle integrazioni (Tappa 2, Task 7, decisione di Paolo del
# 03/10/2026, «avviso»): lo stato di ogni voce di integrazione arriva per
# evento invece di rileggersi ogni dieci minuti. Letto il 03/10/2026 nel
# sorgente di Home Assistant al tag `2026.9.4`:
# `components/config/config_entries.py`, `config_entries_subscribe` (righe
# 660-711): conferma (`send_result`), poi UN evento con l'elenco intero,
# `[{"type": None, "entry": voce}]`, e da li' un evento per ogni cambio,
# `[{"type": "added" | "removed" | "updated", "entry": voce}]`
# (`ConfigEntryChange`, `homeassistant/config_entries.py` righe 224-229). La
# voce e' `ConfigEntry.as_json_fragment` (stesso file, righe 658-685): la
# STESSA forma delle righe di `config_entries/get`, che servono lo stesso
# frammento (`_async_matching_config_entries_json_fragments`). Nessun
# `require_admin` sul comando. L'evento porta una LISTA in `event`, non un
# evento del bus: si smista per id dell'iscrizione, non per `event_type`.
CONFIG_ENTRIES_SUBSCRIPTION = "config_entries/subscribe"

# Le attese del websocket di lunga vita, in secondi. Dopo una caduta si
# riprova dopo `RECONNECT_DELAY_S`. Dopo un gettone RIFIUTATO (S-04) l'attesa
# parte da `AUTH_RETRY_FIRST_S` e raddoppia fino a `AUTH_RETRY_CEILING_S`:
# ogni rifiuto e' una notifica «Login attempt failed» fra quelle di Home
# Assistant (`components/http/ban.py`, `process_wrong_login`, righe 115-145
# al tag 2026.9.4) -- l'indirizzo del Supervisor non viene mai bandito
# (righe 153-155), ma un tentativo ogni dieci secondi riempirebbe le notifiche.
RECONNECT_DELAY_S = 10
AUTH_RETRY_FIRST_S = 10
AUTH_RETRY_CEILING_S = 300

# Cap espliciti: questi dati finiscono nel prompt di un LLM, quindi la loro
# dimensione va limitata alla fonte.
# Cap sui punti di storico dettagliato riportati per SINGOLA entita' -- non
# per chiamata: con N entita' nella lista la risposta puo' portarne fino a
# N x MAX_HISTORY_POINTS. Due giorni di un sensore chiacchierone ne producono
# migliaia: il cap protegge la memoria di QUESTO processo per ogni singola
# serie, non la leggibilita' della risposta (di quella si occupa
# `home_space/house_history.py`, che non ne da' mai piu' di 50). Chi legge
# deve poter sapere che e' scattato, quindi la risposta lo dichiara invece
# di tacere -- la stessa regola che il diario di Home Assistant aveva
# insegnato (uscito il 30/09/2026).
MAX_HISTORY_POINTS = 5000
#: Quanti byte di identificatori (gia' codificati per l'URL, virgole
#: comprese) vanno in UNA richiesta a `/api/history/period`. Il server aiohttp
#: di Home Assistant, e il proxy del Supervisor che gli sta davanti, rifiutano
#: una riga di richiesta oltre 8.190 byte (`max_line_size`); il resto della
#: riga -- metodo, percorso, i due istanti, i parametri fissi -- sta sotto i
#: 200. 6.000 lascia margine anche a un percorso di base piu' lungo di
#: `/core`. Scelto, non misurato: la misura dal vivo e' la verifica
#: (30/09/2026, ~300 entita' vere superano il tetto in un pezzo solo).
_HISTORY_FILTER_MAX = 6000
# Cap sugli eventi restituiti da UNA chiamata a `calendar_events()`.
# Misurato sulla casa vera il 06/09/2026: 297 eventi in tutto, su una
# finestra di QUATTRO ANNI (91 nel calendario `personale`, 206 in
# `famiglia`). Il tetto sta molto sopra qualunque uso vero. Non limita ne'
# la scansione che Home Assistant fa (governata da `start`/`end`, quindi
# da chi chiama), ne' cio' che attraversa la rete -- il JSON intero arriva
# comunque: limita solo cio' che QUESTO processo tiene e passa a valle, la
# stessa cosa che protegge `MAX_HISTORY_POINTS` qui sopra. Stessa regola
# del troncamento di `history()`: chi legge deve poter sapere
# che e' scattato, la risposta lo dichiara invece di tacere.
MAX_CALENDAR_EVENTS = 2000

logger = logging.getLogger(__name__)

# Le cause di un guasto di lettura (decisione D3 del 03/10/2026, A-29/A-30).
# Prima «Home Assistant non ha risposto» si diceva in nove modi e otto forme:
# un'eccezione, `{}`, `None`, «risposta in forma inattesa» per una connessione
# caduta. Adesso la causa e' un campo, e ogni lettore la legge allo stesso modo.
#: La domanda non ha avuto risposta: connessione caduta, autenticazione
#: rifiutata, tempo scaduto.
SILENCE = "silenzio"
#: Home Assistant ha risposto di no: il motivo e il codice sono i suoi.
REFUSAL = "rifiuto"
#: Home Assistant ha risposto di si', con una forma che il client non sa leggere.
SHAPE = "forma"
#: La domanda non e' partita: HIRIS l'ha fermata prima della rete (un
#: identificatore malformato, un tipo che Home Assistant non conosce).
REQUEST = "richiesta"

#: Il motivo di un comando rimasto senza risposta.
_HA_SILENT = "Home Assistant non ha risposto"


def _failure(cause: str, text: str, code=None) -> dict:
    """La busta di un guasto: L'UNICO costruttore.

    `{"errore": testo, "causa": una delle quattro qui sopra, "codice": il
    codice di Home Assistant (`error.code` del WebSocket), lo stato HTTP, o
    `None`}`. Le tre chiavi ci sono sempre: un lettore che le trova da una
    porta le trova da tutte (fondamenta 3). Il successo di una lettura NON
    passa di qui: tiene la sua forma.

    **Dove la promessa non vale ancora** (canale della configurazione, Tappa
    7): il rifiuto di Home Assistant a `save_configuration` e
    `delete_configuration` e' ancora il solo `{"errore": motivo}`, e le tre
    primitive della configurazione (con `read_configuration`) sollevano sul
    trasporto invece di rendere il silenzio. Il rifiuto prima della rete
    (`_config_route`) e il rifiuto di HA a `read_configuration` hanno gia' la
    busta intera.
    """
    return {"errore": text, "causa": cause, "codice": code}


class HAReadError(Exception):
    """Una lettura non riuscita, per chi DEVE sollevare: lo specchio al primo
    caricamento, la rilettura del comportamento, il registro dei servizi mai
    caricato. Il client non solleva (D3); chi ha un contratto che solleva
    trasforma la busta in questa eccezione, e la busta intera resta in
    `failure`."""

    def __init__(self, failure: dict) -> None:
        super().__init__(f"{failure.get('errore')} ({failure.get('causa')})")
        self.failure = failure


def _instant_from_ha(raw):
    """Un istante come lo manda Home Assistant -> ISO-8601 con fuso.

    **Misurato sulla casa il 24/08/2026**, non dedotto:
    `recorder/statistics_during_period` risponde
    `{"start": 1787342400000, "end": ..., "max": .., "mean": .., "min": ..}`
    -- `start` e' un INTERO in millisecondi. Prima di questa misura il
    traduttore lo lasciava passare cosi' com'era, e `home_space/historian.py` rifiutava
    di rispondere perche' non sapeva leggerlo: l'intero ramo delle statistiche
    era fermo, ed e' il difetto che la prima domanda vera ha rivelato.

    Regge anche una stringa gia' ISO (le versioni di HA non sono tutte
    uguali) e i secondi invece dei millisecondi: la soglia 1e11 separa i due
    senza ambiguita' -- 1e11 secondi e' l'anno 5138, 1e11 millisecondi il
    1973, e nessuna casa ha dati la'.

    Cio' che NON si sa leggere torna **invariato**, non convertito a caso: chi
    lo riceve lo rifiuta rumorosamente, ed e' meglio di un istante inventato.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return raw
    seconds = raw / 1000.0 if abs(raw) > 1e11 else float(raw)
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return raw


def _translate_statistics(raw: dict) -> dict[str, list[dict]]:
    """`{statistic_id: [fascia HA, ...]}` -> lo stesso, in italiano.

    **L'UNICO punto che traduce le chiavi di `recorder/statistics_during_
    period`** (`HAClient._request_statistics`, l'UNICO chiamante):
    `hourly_statistics()` passa di li', e una
    seconda entrata userebbe questa invece di una propria copia -- una seconda tabella di
    traduzione sarebbe il doppione che questo progetto ha gia' pagato altrove
    (fondamenta 2).

    `stato`/`cambio` (mandato «il bilancio dell'energia», 27/08/2026): prima
    di questa correzione il traduttore leggeva solo `min`/`max`/`mean`/`sum`
    -- **`state` era gia' nella risposta di HA** (misurato: senza `types`
    esplicito HA manda tutto cio' che sa calcolare) e veniva scartato in
    silenzio. Stessa regola di `somma`: si omette quando HA non lo manda
    (una misura senza contatore, es. la potenza istantanea), non si mette a
    `None`.
    """
    series: dict[str, list[dict]] = {}
    for ident, bands in raw.items():
        if not isinstance(bands, list):
            continue
        translated = []
        for f in bands:
            if not isinstance(f, dict):
                continue
            entry = {"inizio": _instant_from_ha(f.get("start")),
                     "fine": _instant_from_ha(f.get("end")),
                     "minimo": f.get("min"),
                     "massimo": f.get("max"), "media": f.get("mean")}
            if f.get("sum") is not None:
                entry["somma"] = f.get("sum")
            if f.get("state") is not None:
                entry["stato"] = f.get("state")
            if f.get("change") is not None:
                entry["cambio"] = f.get("change")
            translated.append(entry)
        series[ident] = translated
    return series


# ── La risposta di POST /api/services, che nessuno aveva mai misurata ──────
#
# Home Assistant risponde a una chiamata di servizio con **gli stati che sono
# cambiati durante l'esecuzione**, calcolati da lui mentre il servizio girava.
# Doveva essere il dato che chiudeva il difetto misurato sulla prima casa vera
# (il proprietario spegne due abat-jour, si spengono, e HIRIS risponde «nulla
# e' cambiato ... probabile problema di comunicazione col dispositivo»): lo
# specchio interno non poteva saperlo ancora, questa risposta si'. **Su quella
# casa non lo sapeva nemmeno lei**, ed e' scritto qui sotto.
#
# Era stata scartata di proposito, e l'argomento era serio -- «una seconda
# forma non misurata della stessa risposta», della stessa specie dei due
# difetti di `fields` in `action/registry.py`. L'argomento non e' stato
# ignorato: e' stato applicato. Questa e' la forma non misurata **trattata
# come tale**, cioe' esattamente come `registry.py` tratta `fields`:
#
#   - difensiva -- ogni forma che non si sa leggere diventa «nessun
#     cambiamento riportato», mai un'eccezione e mai un dato indovinato;
#   - **dichiarata al primo uso** nel log, cosi' la prossima prova sulla casa
#     ci dice com'e' fatta davvero invece di farcelo indovinare. E' la stessa
#     disciplina della prova 1 del foglio (`docs/prova-azione.md`).
#
# Le due forme note. Quella storica e' una **lista** di stati completi
# (`entity_id`, `state`, `attributes`, ...). Da HA 2023.7, quando si chiede
# `?return_response` per un servizio che risponde dei dati, la risposta e'
# invece una **mappa** `{"changed_states": [...], "service_response": {...}}`.
# HIRIS non chiede `return_response` e quindi si aspetta la lista -- ma
# accettare anche la mappa costa tre righe, ed e' il caso in cui il codice di
# prima (`isinstance(cambiati, list) else []`) avrebbe buttato via in silenzio
# proprio gli stati cambiati.
#
# **La misura e' arrivata, ed e' il motivo per cui questa riga di log
# esisteva.** Sull'impianto del proprietario, con le luci che si accendevano
# davvero: «la risposta di Home Assistant e' list, 0 voci utilizzabili, chiavi
# della prima: None». La forma e' quella attesa -- una lista -- ma su quella
# casa e' VUOTA anche a comando riuscito. Il lettore qui sotto e' corretto e
# non cambia; cio' che e' cambiato e' chi ci si appoggia: `action/actuator.py`
# non fonda piu' l'esito su questo ritorno da solo, e aspetta l'annuncio degli
# eventi con una scadenza.
_changed_form_declared = False


def _changed_states(payload) -> list[dict]:
    """Gli stati che HA dichiara cambiati, da qualunque delle forme note.

    Restituisce sempre una lista di dizionari che hanno un `entity_id`: cio'
    che non ha quella chiave non e' uno stato e non serve a nessuno dei suoi
    lettori. Non solleva mai.
    """
    global _changed_form_declared

    raw = payload
    if isinstance(payload, dict):
        # forma `?return_response` (HA >= 2023.7)
        raw = payload.get("changed_states")
    if not isinstance(raw, list):
        raw = []

    states = [v for v in raw if isinstance(v, dict) and v.get("entity_id")]

    if not _changed_form_declared:
        _changed_form_declared = True
        # `sorted(...)` di una sola voce: basta a riconoscere la forma, e non
        # versa nel log gli attributi di mezza casa.
        first_entry = sorted(states[0].keys()) if states else None
        logger.info(
            "call_service: la risposta di Home Assistant e' %s, %s voci "
            "utilizzabili, chiavi della prima: %s -- prima misura di questa "
            "forma su questo impianto",
            type(payload).__name__,
            len(states),
            first_entry)
    return states


def cost(*, ws: int = 0, rest: int = 0):
    """Il costo DICHIARATO di un metodo del client: quante connessioni apre
    verso Home Assistant per rispondere (R16), sulla strada piu' lunga.

    `ws` sono le connessioni WebSocket (ognuna e' una chiamata a `_ws_send`,
    che manda N comandi su UNA connessione), `rest` le richieste HTTP. La
    dichiarazione si chiede al metodo -- `HAClient.get_states.cost` -- e
    `tests/test_ha_client_invio.py` la confronta con cio' che il metodo apre
    davvero su un trasporto che conta. Un costo che non si dichiara non si
    vede, e quello che non si vede cresce: tre metodi ne aprono oggi DUE
    (`add_label_to`, `read_dashboards`, `read_registries`), ed e' scritto qui
    sotto invece di essere nascosto.
    """
    def declare(method):
        method.cost = {"ws": ws, "rest": rest}
        return method
    return declare


def _history_chunks(entity_ids: list[str]) -> list[list[str]]:
    """Gli identificatori in pezzi che stanno ognuno sotto
    `_HISTORY_FILTER_MAX`, nell'ordine dato. Il costo di ognuno e' quello che
    `HAClient.history` gli fa pagare nell'URL: `quote(..., safe="")`, e `%2C`
    per la virgola che lo separa dal precedente. Un identificatore da solo piu'
    lungo del tetto fa un pezzo suo: rifiutarlo qui sarebbe tacerlo."""
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for ident in entity_ids:
        cost = len(quote(ident, safe=""))
        if current and size + len("%2C") + cost > _HISTORY_FILTER_MAX:
            chunks.append(current)
            current, size = [], 0
        size += cost + (len("%2C") if current else 0)
        current.append(ident)
    if current:
        chunks.append(current)
    return chunks


def _identifiers(raw) -> list[str]:
    """Un insieme di identificatori di Home Assistant, letto come una lista.

    Dall'altra parte del websocket quei campi sono `set` di Python
    (`SelectedEntities` in homeassistant/helpers/target.py) e arrivano qui
    serializzati come liste, in ordine ARBITRARIO: si ordinano, o la stessa
    domanda fatta due volte darebbe due anteprime diverse senza che in casa
    sia cambiato niente. Cio' che non e' una stringa si salta: non e' un
    identificatore, e indovinare cosa sia costerebbe piu' di ignorarlo.
    """
    if not isinstance(raw, list):
        return []
    return sorted(v for v in raw if isinstance(v, str) and v)


class HAClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None
        self._ws_task: asyncio.Task | None = None
        self._state_listeners: list[Callable[[dict], None]] = []
        self._topology_listeners: list[Callable[[str], None]] = []
        self._dashboard_listeners: list[Callable[[dict], None]] = []
        self._service_listeners: list[Callable[[str], None]] = []
        self._automation_listeners: list[Callable[[dict], None]] = []
        self._integration_listeners: list[Callable[[list], None]] = []
        #: Acceso mentre il WebSocket di lunga vita e' su: si accende quando
        #: Home Assistant conferma l'iscrizione agli stati, si spegne quando la
        #: connessione cade o il gettone e' rifiutato (S-04, 03/10/2026; prima
        #: si accendeva una volta e non si spegneva mai). E' il segno che il
        #: nucleo di Home Assistant risponde: lo aspetta l'avvio prima di
        #: leggere la casa (D2 della Tappa 2), e chi deve fare UNA chiamata
        #: all'avvio (`panel_visibility`) -- l'add-on parte prima del nucleo
        #: (`startup: services`).
        self.ws_ready = asyncio.Event()
        #: Le connessioni autenticate finora: la prima non avvisa «riconnessione».
        self._connections = 0
        self._reread_at_first_connection = False

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(headers=self._headers)

    async def stop(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
        if self._session:
            await self._session.close()

    async def _rest_get(self, path: str) -> dict:
        """L'UNICA lettura REST verso Home Assistant: `GET <base><path>` sulla
        sessione del client. Rende `{"corpo": json}` oppure la busta del
        guasto, e non solleva: uno stato diverso da 200 e' un rifiuto (col suo
        numero in `codice`), un corpo che non e' JSON e' una forma, ogni altro
        guasto del trasporto e' un silenzio.

        Le tre primitive della configurazione (`read_configuration`,
        `save_configuration`, `delete_configuration`) e `call_service` non
        passano di qui: sono il canale delle scritture (Tappa 7)."""
        try:
            async with self._session.get(f"{self._base_url}{path}") as resp:
                if resp.status != 200:
                    return _failure(REFUSAL, f"Home Assistant ha risposto {resp.status}",
                                    resp.status)
                try:
                    return {"corpo": await resp.json()}
                except (aiohttp.ContentTypeError, ValueError):
                    return _failure(SHAPE, "Home Assistant ha risposto con un corpo "
                                           "che non e' JSON")
        except Exception as exc:
            logger.debug("lettura REST %s non riuscita: %s", path.split("?")[0], exc)
            return _failure(SILENCE,
                            f"{_HA_SILENT}: {_truncate(str(exc) or type(exc).__name__, 200)}")

    @cost(rest=1)
    async def get_states(self, entity_ids: list[str]) -> list[dict] | dict:
        """Gli stati della casa, tutti (`[]`) o quelli chiesti: una lista, o la
        busta del guasto. Non solleva (D3, 03/10/2026: prima sollevava, unico
        con `get_services` fra le letture)."""
        reply = await self._rest_get("/api/states")
        if "errore" in reply:
            return reply
        all_states = reply["corpo"]
        if not isinstance(all_states, list):
            return _failure(SHAPE, "gli stati non sono arrivati come elenco")
        if entity_ids:
            return [s for s in all_states
                    if isinstance(s, dict) and s.get("entity_id") in entity_ids]
        return all_states

    @cost(rest=1)
    async def get_services(self) -> list[dict] | dict:
        """Il registro dei servizi di QUESTA installazione.

        E' la fonte del «meccanismo» (spec dell'azione, §1): cosa e'
        tecnicamente possibile qui dentro, dichiarato da Home Assistant e non
        indovinato da noi. Include le integrazioni installate dall'utente, che
        nessun catalogo scritto a mano potrebbe conoscere.

        Legge e basta: nessuna scrittura verso HA vive in questo metodo.

        Una lista, o la busta del guasto: non solleva (D3). Un guasto non deve
        diventare un registro vuoto -- «nessun servizio» e' un'affermazione
        sulla casa, «non ho letto» no.
        """
        reply = await self._rest_get("/api/services")
        if "errore" in reply:
            return reply
        if not isinstance(reply["corpo"], list):
            return _failure(SHAPE, "i servizi non sono arrivati come elenco")
        return reply["corpo"]

    @cost(rest=1)
    async def call_service(self, domain: str, service: str, data: dict) -> list[dict]:
        """Chiama un servizio di Home Assistant. La primitiva che ATTUA.

        Era uscita con la fetta E3 -- «in un HIRIS che conosce e non agisce la
        primitiva che agisce non deve esistere» -- e torna adesso con la fetta
        «comandare» dell'azione. Il commento che ne raccontava la rimozione e'
        stato tolto: descriveva un fatto che non e' piu' vero.

        **Non chiamarla direttamente.** L'unico chiamante di produzione e'
        `action/actuator.py`, che verifica prima e legge il suo ritorno. Questa
        funzione non verifica NIENTE: se le si passa un servizio inesistente,
        la richiesta parte e Home Assistant risponde 400. E' voluto -- la
        verifica e' un pezzo separato e testabile senza rete, e questa e' la
        primitiva nuda.

        **Restituisce gli stati che Home Assistant dichiara cambiati durante
        l'esecuzione del servizio**, misurati da lui mentre il servizio gira.

        **Su una casa vera e' risultata VUOTA anche a comando riuscito**, ed
        e' la misura che ha smontato la correzione precedente: il log di
        produzione dice «la risposta di Home Assistant e' list, 0 voci
        utilizzabili» mentre le luci si accendevano davvero. Questo ritorno
        resta utile -- dove c'e', e' la misura piu' economica, perche' non
        costa nessuna attesa -- ma non e' una fonte su cui si possa fondare
        l'esito da solo, e chi lo legge deve saperlo.

        Cio' che nessuna delle due misure sincrone sa dire lo dicono gli
        **eventi**: `add_state_listener` (sotto) e' il rubinetto da cui la
        porta aspetta l'annuncio delle entita' che ha comandato, con una
        scadenza (`action/actuator.py`). Lo specchio interno (`EntityCache`) e'
        alimentato dagli stessi eventi, quindi rileggerlo nella riga dopo
        questa `await` legge quasi sempre lo stato di PRIMA: non e' una fonte
        del «dopo», e' l'ultimo valore noto.

        Vuota significa «HA non ha riportato cambiamenti in questa risposta»,
        mai «il dispositivo e' guasto» e nemmeno «non e' cambiato niente».
        """
        url = f"{self._base_url}/api/services/{domain}/{service}"
        async with self._session.post(url, json=data) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        return _changed_states(payload)

    # I tre domini che l'API di configurazione governa. Sono i VALORI delle
    # rotte di `components/config/` (automation.py, script.py, scene.py),
    # verificati alla fonte: `/api/config/{component}/{config_type}/{config_key}`
    # di `components/config/view.py`. Non c'e' una quarta rotta: le plance si
    # scrivono su un altro canale (WS `lovelace/config/save`), che riscrive
    # TUTTO -- vedi la spec §1.1 -- e non passa di qui.
    CONFIGURABLE_DOMAINS = ("automation", "script", "scene")

    # La chiave finisce dentro un URL. Per automazioni e scene e' l'`id`
    # (cifre), per gli script uno slug (`cv.slug`): questa forma li copre
    # entrambi e RIFIUTA tutto il resto. E' una GUARDIA, e come quella su
    # `entity_id` va tenuta STRETTA: allargarla per far passare una chiave
    # esotica e' una decisione di sicurezza, non una pulizia.
    _KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

    def _config_route(self, domain: str, key: str) -> tuple[str | None, dict | None]:
        """L'URL della rotta di configurazione, oppure la busta del rifiuto:
        una domanda fermata prima della rete (`causa: richiesta`), la stessa
        per le tre primitive che passano di qui."""
        if domain not in self.CONFIGURABLE_DOMAINS:
            return None, _failure(REQUEST, (
                f"il dominio «{domain}» non si configura da qui. "
                f"Domini configurabili: {', '.join(self.CONFIGURABLE_DOMAINS)}."))
        if not self._KEY_RE.match(key or ""):
            return None, _failure(REQUEST, (
                f"la chiave «{key}» non ha una forma ammessa "
                "(lettere, cifre, trattino e trattino basso, max 64)."))
        return f"{self._base_url}/api/config/{domain}/config/{key}", None

    @staticmethod
    async def _http_reason(resp) -> str:
        """Il motivo vero che Home Assistant manda nel corpo, non solo il numero.

        L'editor di HA mostra all'utente esattamente questa stringa: e' la
        frase che dice PERCHE' la configurazione e' stata rifiutata, ed e' il
        valore di prodotto della spec §2.5. Se il corpo non e' leggibile resta
        il codice, che e' comunque piu' di «non posso».
        """
        with suppress(aiohttp.ContentTypeError, ValueError):
            body = await resp.json()
            if isinstance(body, dict) and body.get("message"):
                return str(body["message"])
        try:
            text = (await resp.text()) or ""
        except Exception:
            text = ""
        return f"Home Assistant ha risposto {resp.status}. {text}".strip()

    # Punto 6 (residuo, ondata finale punto 1): queste tre primitive sollevano
    # quello che rompe il trasporto -- non catturano niente da sole. Il loro
    # UNICO chiamante (`action/construction/workshop.py::Workshop._rete`) le
    # avvolge apposta: quella guardia e' cio' che trasforma un guasto di rete
    # in `{"errore": ..., "guasto_rete": True}` invece di lasciarlo risalire
    # come eccezione fuori dall'officina. Chi aggiunge un chiamante nuovo a
    # queste tre non deve aggirarla.
    @cost(rest=1)
    async def read_configuration(self, domain: str, key: str) -> dict:
        """Il corpo scritto di un oggetto, letto dalla stessa rotta dell'editor.

        Serve al «prima» di una modifica e di una cancellazione (spec §6): HA
        non tiene storico, e questa e' la fonte di cio' che c'era. NON si usa
        `home_space/behavior.py` al suo posto: quello e' l'archivio di HIRIS,
        aggiornato a cadenza propria, e potrebbe essere vecchio di minuti.

        Un rifiuto di Home Assistant e una domanda fermata prima della rete
        hanno la busta di ogni altra lettura (`_failure`). Solleva solo cio'
        che rompe il trasporto: il silenzio lo fa busta `guasto_rete` il suo
        unico chiamante (`Workshop._rete`), con le due scritture (Tappa 7).
        """
        url, rejection = self._config_route(domain, key)
        if url is None:
            return rejection
        async with self._session.get(url) as resp:
            if resp.status == 404:
                # «Non c'e'» e' un FATTO, non un guasto, ed e' anche il modo
                # con cui si verifica che un id nuovo sia libero. Confonderlo
                # con un errore di rete significherebbe, il giorno in cui HA
                # risponde male, dichiarare libero un id occupato e far
                # SOSTITUIRE l'automazione che c'era.
                return {"assente": True}
            if resp.status != 200:
                return _failure(REFUSAL, await self._http_reason(resp), resp.status)
            return {"corpo": await resp.json()}

    @cost(rest=1)
    async def save_configuration(self, domain: str, key: str, body: dict) -> dict:
        """Scrive un oggetto di configurazione. La primitiva che COSTRUISCE.

        **Non chiamarla direttamente.** L'unico chiamante di produzione e'
        `action/construction/workshop.py`, che compone il corpo dai parametri,
        lo valida, archivia il «prima» e rilegge dopo.

        **Non solleva sul rifiuto**, ed e' la differenza voluta con
        `call_service` qui sopra: un `400` di Home Assistant su questa rotta
        non e' un guasto di rete, e' il **validatore vero del dominio**
        (`async_validate_config_item`) che dice cosa non va. Quella frase deve
        arrivare al modello perche' si corregga su un fatto di questa
        installazione. Solleva solo cio' che rompe il trasporto.

        **Chi scrive il file e' Home Assistant**, e lo fa trovando la voce per
        `id` e SOSTITUENDOLA (`components/config/view.py::_write_value`). E'
        questa proprieta' che rende impossibile ripetere il danno misurato su
        `automations.yaml` -- la voce accodata quattro volte, nascosta dalle
        ancore YAML. HIRIS non serializza nessuno YAML, e non deve iniziare.
        """
        url, rejection = self._config_route(domain, key)
        if url is None:
            return rejection
        async with self._session.post(url, json=body) as resp:
            if resp.status != 200:
                return {"errore": await self._http_reason(resp)}
            return {"salvato": True}

    @cost(rest=1)
    async def delete_configuration(self, domain: str, key: str) -> dict:
        """Cancella un oggetto di configurazione.

        Il `post_write_hook` di Home Assistant toglie anche l'entita' dal
        registro: dopo questa chiamata l'automazione non esiste piu' ne' nel
        file ne' fra le entita'. Il «prima» deve gia' essere archiviato PRIMA
        di chiamarla (spec §6): dopo, non c'e' piu' nessuna fonte da cui
        rileggerlo.

        Solleva solo cio' che rompe il trasporto.
        """
        url, rejection = self._config_route(domain, key)
        if url is None:
            return rejection
        async with self._session.delete(url) as resp:
            if resp.status != 200:
                return {"errore": await self._http_reason(resp)}
            return {"cancellato": True}

    @cost(ws=1)
    async def validate_config(self, *, triggers=None, conditions=None,
                              actions=None) -> dict:
        """La prova a vuoto: valido o no, secondo QUESTA casa, senza salvare.

        E' il comando WS `validate_config` (`components/websocket_api/
        commands.py`): accetta `triggers`, `conditions`, `actions` e risponde
        per ciascuna chiave `{"valid": bool, "error": str|None}`. **Non scrive
        niente.**

        E' cio' che permette al giro della spec (§3) di mostrare un'anteprima
        gia' verificata: un tentativo sbagliato non costa una scrittura, e il
        modello si corregge su un fatto invece che su un ricordo.

        Si mandano SOLO le chiavi presenti: mandarne una vuota significherebbe
        chiedere a HA di validare una lista vuota, che e' valida -- e un
        «valido» su una cosa che non abbiamo chiesto e' una frase falsa detta
        con sicurezza.

        Un guasto di comunicazione torna come `{"errore": ...}` e **mai** come
        un esito valido: il silenzio di Home Assistant non e' un permesso.
        """
        extra: dict = {}
        if triggers is not None:
            extra["triggers"] = triggers
        if conditions is not None:
            extra["conditions"] = conditions
        if actions is not None:
            extra["actions"] = actions
        if not extra:
            return _failure(REQUEST, "niente da validare")
        (msg,) = await self._ws_send([("validate_config", extra)])
        occurrence = self._ws_occurrence(msg, "risultato")
        if "errore" in occurrence:
            return occurrence
        result = occurrence["risultato"]
        if not isinstance(result, dict):
            return _failure(SHAPE, "risposta in forma inattesa dalla validazione")
        return result

    # Gli helper che questa fetta sa creare. Sono collezioni gestite da
    # `StorageCollectionWebsocket` di Home Assistant, che espone per ognuna
    # `{domain}/create`, `{domain}/update`, `{domain}/delete` -- e la
    # chiave del delete porta il NOME DEL DOMINIO (`input_boolean_id`), non
    # `id`. Non e' un dettaglio estetico: con `id` il comando viene rifiutato.
    HELPER_DOMAINS = ("input_boolean", "input_number", "input_select",
                      "input_text", "input_datetime", "timer", "counter",
                      "schedule")

    @staticmethod
    def _ws_occurrence(msg: dict | None, key: str) -> dict:
        """Il `result` di un comando WS come `{key: result}`, oppure la busta
        del guasto -- mai un successo muto.

        `None` (il comando non ha avuto risposta: `_ws_send` non solleva) e'
        un silenzio; un `error` di Home Assistant e' un rifiuto, col SUO
        motivo e il SUO codice. La forma del `result` la giudica chi chiama:
        il client non sa, qui, cosa ogni comando dovrebbe rispondere.
        """
        if msg is None:
            return _failure(SILENCE, _HA_SILENT)
        error = msg.get("error")
        if error:
            error = error if isinstance(error, dict) else {}
            return _failure(REFUSAL,
                            error.get("message") or error.get("code") or "rifiutato",
                            error.get("code"))
        # `success: false` senza `error` e' un rifiuto senza motivo; un
        # messaggio che `success` non lo porta affatto si legge dal suo
        # `result` (Home Assistant lo porta sempre: le finte non sempre).
        if msg.get("success") is False:
            return _failure(REFUSAL, "Home Assistant ha rifiutato il comando")
        return {key: msg.get("result")}

    @cost(ws=1)
    async def create_helper(self, domain: str, data: dict) -> dict:
        """Crea un helper. Primitiva nuda: un solo chiamante, l'officina.

        Gli helper sono nel perimetro della fetta perche' meta' delle
        automazioni utili ne ha bisogno (spec §3.1): un'automazione che si puo'
        comporre ma non accendere perche' manca un `input_boolean` si ferma a
        un passo dalla fine.
        """
        if domain not in self.HELPER_DOMAINS:
            return _failure(REQUEST, f"«{domain}» non e' un helper che so creare. "
                                     f"Helper: {', '.join(self.HELPER_DOMAINS)}.")
        (msg,) = await self._ws_send([(f"{domain}/create", dict(data))])
        return self._ws_occurrence(msg, "helper")

    @cost(ws=1)
    async def delete_helper(self, domain: str, helper_id: str) -> dict:
        """Cancella un helper. Serve alla DISFATTA (spec §3.1): se l'automazione
        viene rifiutata dopo che gli helper sono nati, l'officina li toglie."""
        if domain not in self.HELPER_DOMAINS:
            return _failure(REQUEST, f"«{domain}» non e' un helper che so cancellare.")
        (msg,) = await self._ws_send([(f"{domain}/delete", {f"{domain}_id": helper_id})])
        occurrence = self._ws_occurrence(msg, "_")
        return occurrence if "errore" in occurrence else {"cancellato": True}

    #: I gruppi di sistema di Home Assistant. Verificato il 21/09/2026 sul
    #: sorgente (`components/config/auth.py`): `config/auth/list` restituisce
    #: `group_ids` e **non** `is_admin`, che si ricava di qui. Riverificato il
    #: 27/09/2026 su Core 2026.9.3 (`auth/const.py`) e sulla casa, dove il
    #: gruppo di sola lettura esiste.
    ADMIN_GROUP = "system-admin"
    USERS_GROUP = "system-users"
    READ_ONLY_GROUP = "system-read-only"

    @cost(ws=1)
    async def users(self) -> dict:
        """Chi sono le persone di questa casa, e chi comanda.

        Serve all'invariante I-1: l'ingress dice CHI sta chiedendo
        (`X-Remote-User-Id`), non cosa gli e' concesso. Il ruolo lo sa Home
        Assistant, e HIRIS puo' chiederglielo perche' il Supervisor proxa con la
        propria sessione privilegiata -- che e' poi la stessa ragione per cui
        oggi HIRIS **amplifica**, parlando con HA da amministratore qualunque sia
        la persona che ha scritto in chat.

        **Il verso del dubbio**: se la lettura non riesce si torna il motivo e
        **nessun elenco**. Un elenco vuoto accanto a un guasto si legge come «non
        ce n'erano», e a valle diventerebbe «nessuno e' amministratore» oppure --
        peggio, secondo come lo si scrive -- un ripiego su «lo e' chiunque». Un
        guasto di rete non deve poter cambiare un permesso.
        """
        (msg,) = await self._ws_send([("config/auth/list", None)])
        occurrence = self._ws_occurrence(msg, "utenti")
        if "errore" in occurrence:
            return occurrence
        rows = occurrence["utenti"]
        if not isinstance(rows, list):
            return _failure(SHAPE, "l’elenco degli utenti non è arrivato come elenco")
        return {"utenti": [self._user_row(r) for r in rows if isinstance(r, dict)]}

    @classmethod
    def _user_row(cls, r: dict) -> dict:
        """Una riga di `config/auth/list` nelle parole di HIRIS.

        **`amministratore` e' la regola di Home Assistant, non un suo pezzo**:
        verificato il 27/09/2026 su Core 2026.9.3,
        `auth/models.py::User.is_admin` = `is_owner or (is_active and
        system-admin nei gruppi)`. Fino a oggi qui contava solo il gruppo, e un
        proprietario fuori dal gruppo sarebbe stato chiuso fuori dal cancello
        al confine. Un `is_active` che manca non e' un «si'».

        `sola_lettura`: il gruppo `system-read-only` SENZA `system-users` --
        Core unisce le politiche dei gruppi (`auth/permissions/merge.py`), e chi
        e' in entrambi comanda. `senza_gruppi`: nessun gruppo, e per chi non e'
        il proprietario vuol dire nessun permesso (`merge_policies([])`). Il
        ruolo che ne segue lo decide `soffitto._role_of`.
        """
        groups = r.get("group_ids") or []
        admin = bool(r.get("is_owner")) or (
            r.get("is_active") is True and cls.ADMIN_GROUP in groups)
        return {"id": r.get("id"),
                "nome": r.get("name"),
                "amministratore": admin,
                "sola_lettura": (cls.READ_ONLY_GROUP in groups
                                 and cls.USERS_GROUP not in groups),
                "senza_gruppi": not groups,
                "proprietario": bool(r.get("is_owner")),
                "sistema": bool(r.get("system_generated"))}

    @cost(ws=1)
    async def update_panel(self, url_path: str, require_admin: bool | None) -> dict:
        """Scrive l'override di `require_admin` per UN pannello del menu.

        Verificato il 27/09/2026 sul sorgente di Core 2026.9.3
        (`components/frontend/__init__.py::websocket_update_panel`, dalla
        2026.3, `@require_admin`): `None` toglie la chiave dall'override,
        `not_found` per un pannello che non c'e'. Si manda SOLO
        `require_admin`: titolo, icona e barra laterale non sono decisioni di
        HIRIS. Il `codice` torna accanto al motivo perche' un HA piu' vecchio
        risponde `unknown_command`, e quel caso si dice con parole sue.
        """
        (msg,) = await self._ws_send([(
            "frontend/update_panel",
            {"url_path": url_path, "require_admin": require_admin})])
        occurrence = self._ws_occurrence(msg, "_")
        return occurrence if "errore" in occurrence else {"aggiornato": True}

    @cost(ws=1)
    async def panels(self) -> dict:
        """I pannelli del menu come li vede HIRIS: `{"pannelli": {url_path:
        {...}}}` oppure il motivo. `get_panels` applica gia' l'override di
        `frontend/update_panel` (`websocket_get_panels`, stesso sorgente e
        stessa data qui sopra): e' lo stato vero, non quello chiesto."""
        (msg,) = await self._ws_send([("get_panels", None)])
        occurrence = self._ws_occurrence(msg, "pannelli")
        if "errore" in occurrence:
            return occurrence
        if not isinstance(occurrence["pannelli"], dict):
            return _failure(SHAPE, "l'elenco dei pannelli non è arrivato come oggetto")
        return occurrence

    @cost(ws=1)
    async def create_label(self, name: str) -> dict:
        """Crea un'etichetta. La paternita' di cio' che HIRIS costruisce vive
        QUI, nel registro di Home Assistant, e non in una tabella nostra: e'
        un fatto che HA sa gia' tenere, e duplicarlo sarebbe la fondamenta 2
        violata (spec §5)."""
        (msg,) = await self._ws_send([("config/label_registry/create", {"name": name})])
        return self._ws_occurrence(msg, "etichetta")

    @cost(ws=2)
    async def add_label_to(self, entity_id: str, label_id: str) -> dict:
        """Aggiunge un'etichetta a un'entita', SENZA togliere le altre.

        `config/entity_registry/update` **sostituisce** la lista `labels`: chi
        manda solo la propria cancella quelle che l'utente aveva messo a mano.
        Si legge, si unisce, si riscrive.

        E se la lettura non riesce **non si scrive**: «non ho letto» non e'
        «non ce n'erano», e trattarli allo stesso modo cancellerebbe le
        etichette dell'utente proprio quando Home Assistant sta rispondendo
        male.
        """
        (msg,) = await self._ws_send([("config/entity_registry/get",
                                       {"entity_id": entity_id})])
        loaded = self._ws_occurrence(msg, "voce")
        if "errore" in loaded:
            return {**loaded, "errore": f"non ho potuto leggere le etichette di "
                                        f"{entity_id}: {loaded['errore']}"}
        entry = loaded["voce"] if isinstance(loaded["voce"], dict) else {}
        current_labels = entry.get("labels")
        current_labels = list(current_labels) if isinstance(current_labels, list) else []
        if label_id in current_labels:
            return {"applicata": True}
        (msg,) = await self._ws_send([(
            "config/entity_registry/update",
            {"entity_id": entity_id, "labels": current_labels + [label_id]})])
        occurrence = self._ws_occurrence(msg, "_")
        return occurrence if "errore" in occurrence else {"applicata": True}

    # I cinque campi con cui Home Assistant accetta un bersaglio: sono le
    # chiavi di `cv.TARGET_FIELDS` (homeassistant/helpers/config_validation.py),
    # verificate alla fonte. Qui ci sono i VALORI delle costanti, non i loro
    # nomi -- `ATTR_AREA_ID` vale "area_id", `ATTR_LABEL_ID` vale "label_id" --
    # perche' in questo progetto la differenza fra il nome di una costante di
    # Home Assistant e il suo valore e' gia' costata cara (`CO` vale
    # "carbon_monoxide", non "co").
    TARGET_FIELDS = ("entity_id", "device_id", "area_id", "floor_id", "label_id")

    @cost(ws=1)
    async def extract_from_target(self, target: dict) -> dict:
        """Cosa contiene un bersaglio -- e a dirlo e' HOME ASSISTANT, non HIRIS.

        E' il comando `extract_from_target` (websocket_api/commands.py):
        gli si passa un bersaglio nella forma di `cv.TARGET_FIELDS` (aree,
        piani, etichette, dispositivi, entita') e risponde con le entita' che
        quel bersaglio tocca davvero.

        **Perche' non lo deduce l'anagrafe.** L'albero di `hierarchy()` e' una
        replica che HIRIS costruisce dai registri: e' un'AFFERMAZIONE sulla
        casa, e niente la verifica. Qui la domanda va all'originale. E' anche
        la ragione per cui questa lettura non e' un doppione dell'anagrafe: e'
        il secondo parere che permette di accorgersi quando la replica e'
        vecchia -- vedi `docs/design/2026-08-17-piano-i-sette-che-mancano.md`.

        **I due parametri non sono valori di comodo: replicano cio' che fa una
        chiamata di servizio vera.** In `homeassistant/helpers/service.py`
        l'estrazione delle entita' di un servizio e'
        `async_extract_referenced_entity_ids(hass, target_selection, True)`,
        cioe' `expand_group=True` e `primary_entities_only` al suo default
        `True`, e le entita' su cui il servizio agisce sono l'unione di
        `referenced` e `indirectly_referenced` -- esattamente cio' che il
        comando restituisce in `referenced_entities`. Il comando WS ha invece
        `expand_group` predefinito a `False`: lasciarglielo avrebbe prodotto
        un'anteprima che NON coincide con cio' che si tocca, cioe' il difetto
        di questa fetta in una forma nuova. Si passano quindi entrambi
        espliciti.

        **Le due meta' contano entrambe.** `referenced_*` dice cosa si
        tocchera'; i `*_mancanti` dicono cosa il bersaglio nominava e non
        esiste -- la differenza fra «l'area e' vuota» e «quell'area non c'e'»,
        la stessa distinzione che l'anagrafe fa gia' ovunque.

        Restituisce le due meta' con i nomi italiani del resto della casa::

            {"entita": [...], "dispositivi": [...], "aree": [...],
             "dispositivi_mancanti": [...], "aree_mancanti": [...],
             "piani_mancanti": [...], "etichette_mancanti": [...]}

        oppure `{"errore": "..."}` -- mai un elenco ridotto in silenzio: un
        bersaglio che non si e' potuto risolvere non e' un bersaglio vuoto, e
        chi chiama deve poterlo dichiarare invece di toccare «quasi tutto».
        """
        if not isinstance(target, dict):
            return _failure(REQUEST, "il bersaglio non e' un oggetto")
        cleaned = {}
        for field in self.TARGET_FIELDS:
            entries = target.get(field)
            if isinstance(entries, str):
                entries = [entries]
            if not isinstance(entries, list):
                continue
            entries = [v for v in entries if isinstance(v, str) and v.strip()]
            if entries:
                cleaned[field] = entries
        if not cleaned:
            return _failure(REQUEST, "il bersaglio non nomina niente che Home "
                                     "Assistant sappia risolvere")

        (msg,) = await self._ws_send([("extract_from_target",
                                       {"target": cleaned,
                                        "expand_group": True,
                                        "primary_entities_only": True})])
        # Tre modi di non aver saputo, tre cause diverse: la connessione non
        # c'e' stata, Home Assistant ha detto di no (e allora si riporta cosa
        # ha detto, col suo codice: un `unknown_command` su una versione
        # vecchia si legge qui), la risposta non era leggibile. Un solo «non
        # lo so» li avrebbe confusi, e sono guasti con rimedi diversi.
        occurrence = self._ws_occurrence(msg, "bersaglio")
        if "errore" in occurrence:
            return occurrence
        result = occurrence["bersaglio"]
        if not isinstance(result, dict):
            return _failure(SHAPE, "la risposta di «extract_from_target» non e' un oggetto")

        # I dispositivi che non esistono arrivano ANCHE in
        # `referenced_devices`: `_resolve_referenced_devices`
        # (homeassistant/helpers/target.py) li aggiunge a entrambi gli
        # insiemi. Tenerli qui vorrebbe dire dire «questo dispositivo si
        # tocca» di un dispositivo che non c'e'; toglierli non nasconde
        # niente, perche' restano interi in `dispositivi_mancanti`.
        missing = _identifiers(result.get("missing_devices"))
        return {
            "entita": _identifiers(result.get("referenced_entities")),
            "dispositivi": [d for d in _identifiers(result.get("referenced_devices"))
                            if d not in set(missing)],
            "aree": _identifiers(result.get("referenced_areas")),
            "dispositivi_mancanti": missing,
            "aree_mancanti": _identifiers(result.get("missing_areas")),
            "piani_mancanti": _identifiers(result.get("missing_floors")),
            "etichette_mancanti": _identifiers(result.get("missing_labels")),
        }

    @cost(ws=2)
    async def read_dashboards(self) -> tuple[list[dict], list[str]]:
        """Le plance con la loro configurazione. Due connessioni, N comandi:
        prima l'elenco (`lovelace/dashboards/list`), poi — solo dopo, perche'
        e' li' che si scoprono i percorsi da interrogare — un'unica
        connessione batch per tutte le `lovelace/config`.

        La **predefinita** non compare in `lovelace/dashboards/list`: ha
        `url_path` nullo e si chiede a parte. E' la plancia che l'utente
        guarda tutti i giorni, ed e' l'unica che HIRIS non ha mai visto.

        Restituisce `(plance, non_disponibili)`: una plancia in modalita'
        YAML non sta nell'archivio interno di HA e la sua configurazione non
        si legge — `config` resta `None` e il suo percorso finisce fra i non
        disponibili, invece di sembrare una plancia senza viste.

        Un percorso duplicato nell'elenco, o uguale alla chiave sentinella
        della predefinita, finisce anche lui fra i `non_disponibili` (con una
        ragione leggibile) invece di entrare due volte nell'elenco.

        Se l'elenco stesso non arriva (timeout, disconnessione), lo si
        dichiara come `"elenco: ..."` in `non_disponibili` — invece di
        confonderlo con «l'elenco e' arrivato ed e' vuoto», che e' un fatto
        diverso sulla casa (nessuna plancia aggiuntiva, non «non lo so»). Per
        questo si guarda il messaggio intero, con `success`, e non il solo
        `result`: `result` e' `None` sia se il comando e' fallito sia se e'
        riuscito con `result: None`, le due cose non si distinguerebbero.
        """
        (got,) = await self._ws_send([("lovelace/dashboards/list", {})])
        listing_arrived = bool(got and got.get("success"))
        listing = got.get("result") if listing_arrived else None
        listing = listing if isinstance(listing, list) else []

        unavailable: list[str] = []
        if not listing_arrived:
            # La causa e' quella della busta (D3): «non ha risposto» e «ha
            # detto di no» non sono piu' la stessa frase.
            unavailable.append(
                f"elenco: lovelace/dashboards/list -- "
                f"{self._ws_occurrence(got, 'elenco')['errore']}"
                " — le plance aggiuntive potrebbero non essere tutte qui"
            )

        # `None` = la predefinita, sempre in testa. Un percorso vero entra
        # una volta sola: quello duplicato va dichiarato in
        # `non_disponibili`, non nascosto sovrascrivendo in silenzio.
        # `is not None` (non verita' booleana): un url_path vuoto ("") e'
        # falsy ma e' un percorso legittimo, non un'assenza.
        # `non_disponibili` non si ridichiara qui: gia' inizializzata sopra,
        # puo' gia' portare la dichiarazione "elenco" se l'elenco non e'
        # arrivato — ridichiararla la cancellerebbe.
        paths: list[str | None] = [None]
        seen: set[str] = set()
        for d in listing:
            p = d.get("url_path")
            if p is None:
                continue
            if p in seen:
                unavailable.append(f"{p} (duplicata nell'elenco, ignorata)")
                continue
            seen.add(p)
            paths.append(p)

        commands = [("lovelace/config", {} if p is None else {"url_path": p})
                    for p in paths]
        replies = await self._ws_send(commands)

        # setdefault, non un comprehension che sovrascrive: un percorso
        # duplicato deve accoppiarsi al PRIMO dizionario visto (coerente con
        # `seen` sopra), non all'ultimo — altrimenti la voce tenuta e quella
        # dichiarata scartata si scambierebbero i dati.
        by_path: dict[str | None, dict] = {}
        for d in listing:
            if isinstance(d, dict):
                by_path.setdefault(d.get("url_path"), d)
        dashboards: list[dict] = []
        for path, msg in zip(paths, replies):
            config = msg.get("result") if msg else None
            if not isinstance(config, dict):
                config = None
                unavailable.append(path or "principale")
            entry = dict(by_path.get(path) or {})
            entry.setdefault("url_path", path)
            entry.setdefault("title", "Principale" if path is None else path)
            entry["config"] = config
            dashboards.append(entry)
        return dashboards, unavailable

    @cost(rest=1)
    async def history(self, entities: list[str], from_iso: str, to_iso: str) -> dict:
        """Lo storico DETTAGLIATO -- ogni cambio di stato -- via
        GET /api/history/period/<da>, A PEZZI (`_history_chunks`), uniti.

        **Perche' a pezzi** (30/09/2026): gli identificatori stanno nell'URL,
        e con ~300 entita' vere la riga di richiesta supera gli 8.190 byte che
        il server aiohttp di Home Assistant (e del Supervisor) accetta. Un
        pezzo solo non e' una risposta lenta: e' nessuna risposta. Il taglio
        vive qui, non nel chiamante (A-27, Tappa 2): una lettura che si rompe
        oltre un certo numero di id non e' una porta, e' una trappola per chi
        la chiama. Il costo dichiarato (`rest=1`) e' quello di UN pezzo, non
        della chiamata: **una richiesta per pezzo di identificatori**
        (`_history_chunks`, uno ogni `_HISTORY_FILTER_MAX` byte di filtro),
        partite insieme. `@cost` non sa dire un costo variabile, e la prova
        (`tests/test_ha_client_invio.py`) chiama con un identificatore solo.
        Nessun identificatore, nessuna richiesta: le serie sono vuote.

        Ritorna `{"serie": {entity_id: [{"quando", "valore"}, ...]}, "troncato":
        bool}`. `troncato` c'e' SEMPRE (mai omesso quando falso) ed e' vero se il cap
        sui punti e' scattato su almeno un'entita'. In caso di guasto ritorna
        `{"errore": str}` e NON la chiave `serie`: una serie vuota afferma «il
        valore non e' mai cambiato», che e' una cosa che non sappiamo quando
        la domanda non e' nemmeno arrivata (spec §3.3). Un pezzo che non
        risponde e' il guasto di tutti: le serie di meta' casa si leggerebbero
        «l'altra meta' non e' cambiata». `troncato` e' vero se Home Assistant
        ha tagliato in ALMENO un pezzo.

        Non solleva mai: ogni guasto diventa `errore`.

        **Questa primitiva era gia' esistita ed e' uscita come orfana**
        (`get_history`, censimento del 17/08/2026: scriveva e nessuno
        leggeva). Torna con un chiamante vero: la storia (`ToolDispatcher._history`,
        genere stati e valori).

        `minimal_response` + `no_attributes`: senza, Home Assistant rimanda
        l'intero dizionario degli attributi a ogni cambio di stato. Il prezzo
        e' la forma della risposta -- solo il PRIMO elemento di ogni lista
        porta `entity_id`, gli altri no -- e questo metodo lo paga portando
        avanti l'identificatore.

        **Valida ogni `entity_id` PRIMA di fare rete** (F6, onda finale): era
        l'ultima asimmetria rimasta con il diario (uscito il 30/09/2026), che
        lo faceva gia'.
        Il percent-encoding chiude comunque l'iniezione nella URL -- non e'
        un buco di sicurezza -- ma un identificatore ostile o malformato deve
        fermarsi con un errore leggibile, non partire verso Home Assistant.
        `entities` e' una LISTA: tutti gli
        elementi devono avere una forma valida, o nessuna richiesta parte.
        """
        invalid = [e for e in entities if not is_entity_id(str(e))]
        if invalid:
            logger.warning("storico: entita' non valide: %r", invalid)
            return _failure(REQUEST, _truncate(f"entita' non valide: {invalid!r}", 200))
        answers = await asyncio.gather(*(self._history_piece(chunk, from_iso, to_iso)
                                         for chunk in _history_chunks(entities)))
        series: dict[str, list[dict]] = {}
        truncated = False
        for answer in answers:
            if "errore" in answer:
                return answer
            series.update(answer["serie"])
            truncated = truncated or answer["troncato"]
        return {"serie": series, "troncato": truncated}

    async def _history_piece(self, entities: list[str], from_iso: str, to_iso: str) -> dict:
        """UN pezzo di `history`: una richiesta, gia' validata e sotto il
        tetto della riga. Stessa forma di `history`."""
        entity_filter = quote(",".join(entities), safe="")
        # S-06: l'istante va nel PERCORSO, e il `+` del fuso non deve
        # arrivarci nudo. Codificato, Home Assistant risponde uguale:
        # misurato il 04/10/2026 sulla casa vera.
        path = (f"/api/history/period/{quote(from_iso, safe='')}"
                f"?end_time={quote(to_iso, safe='')}"
                f"&filter_entity_id={entity_filter}"
                f"&minimal_response&no_attributes")
        reply = await self._rest_get(path)
        if "errore" in reply:
            return reply
        data = reply["corpo"]
        if not isinstance(data, list):
            return _failure(SHAPE, "Home Assistant ha risposto in una forma non attesa")
        raw: dict[str, list[dict]] = {}
        for group in data:
            if not isinstance(group, list):
                continue
            current = None
            for entry in group:
                if not isinstance(entry, dict):
                    continue
                # Solo il primo elemento porta l'entita' (minimal_response):
                # si porta avanti. Un gruppo che non la porta affatto non e'
                # attribuibile a nessuno e si salta, invece di finire sotto
                # una chiave inventata.
                current = entry.get("entity_id") or current
                if not current:
                    continue
                when = entry.get("last_changed") or entry.get("last_updated")
                if when is None:
                    continue
                # I1 (review indipendente 25/08/2026): `valore` e' lo stato
                # GREZZO di QUALUNQUE entita' richiesta, non un numero per
                # costruzione -- un'affermazione contraria era finita anche
                # nel docstring di `_sanitize.py`, ed era falsa: si vede qui.
                # la storia chiede proprio gli stati («se una porta e' rimasta aperta»), e
                # L1-sicurezza.md elenca il sensore-messaggio (testo libero)
                # come il PRIMO vettore concreto -- si applica identico alla
                # storia quanto allo stato vivo.
                value = entry.get("state")
                raw.setdefault(current, []).append(
                    {"quando": when,
                     "valore": sanitize_ha_value(value) if value else value})
        # /api/history/period risponde in ordine cronologico ASCENDENTE: il
        # taglio tiene la CODA -- i punti piu' RECENTI -- e scarta la testa,
        # non il contrario. Per "com'e' andata" contano i dati di adesso; un
        # sensore chiacchierone che perdesse la coda ometterebbe lo stato
        # attuale mostrando solo ore vecchie della finestra chiesta.
        truncated = False
        series: dict[str, list[dict]] = {}
        for entity_id, points in raw.items():
            if len(points) > MAX_HISTORY_POINTS:
                truncated = True
            series[entity_id] = points[-MAX_HISTORY_POINTS:]
        return {"serie": series, "troncato": truncated}

    @cost(ws=1)
    async def recorded_changes(self, entity_ids: list[str],
                               windows: list[tuple[float, float]]) -> list[int | None] | dict:
        """Per ogni finestra, quante righe Home Assistant ha ancora REGISTRATO
        li' dentro. `None` dove la domanda non ha ricevuto risposta.

        Serve a una cosa sola: sapere **quanto indietro arriva la memoria di
        Home Assistant**, che nessuna porta dichiara. Verificato dal vivo
        l'11/09/2026: `recorder/info` risponde e non la contiene
        (`backlog`, `db_in_default_location`, `max_backlog`,
        `migration_in_progress`, `migration_is_live`, `recording`,
        `thread_running`); `recorder/config` e `recorder/statistics_info` non
        esistono affatto (`unknown_command`). Resta il modo diretto: calare una
        sonda e guardare se torna su con qualcosa.

        **Si contano solo le righe DENTRO la finestra.**
        `history/history_during_period` antepone per ogni entita' lo stato che
        aveva **all'inizio** della finestra -- una riga piu' vecchia della
        finestra stessa. Contarla direbbe «qui c'e' ancora memoria» proprio dove
        la memoria e' finita, e la cadenza di riconsiderazione (spec §5.2)
        diventerebbe piu' lunga della memoria che deve stare sotto.

        **`None` non e' zero**: zero afferma «Home Assistant qui non ricorda
        niente», e non lo si sa quando la domanda non e' arrivata. Stessa
        disciplina di `history()` qui sopra, che non rimanda una serie vuota
        quando e' la rete ad aver ceduto.

        Tutte le finestre partono in **una raffica sola**: sono la scala di una
        misura, non letture indipendenti (casa vera: dieci profondita' in
        264 ms). Se la raffica non parte affatto (nessuna risposta) il
        risultato e' la busta del silenzio, non una scala di `None` (D3).
        """
        if not windows:
            return []
        commands = [
            ("history/history_during_period", {
                "start_time": datetime.fromtimestamp(start, UTC).isoformat(),
                "end_time": datetime.fromtimestamp(end, UTC).isoformat(),
                "entity_ids": list(entity_ids),
                "minimal_response": True,
                "no_attributes": True,
                "significant_changes_only": True,
            })
            for start, end in windows
        ]
        replies = await self._ws_send(commands)
        if all(reply is None for reply in replies):
            # La raffica non e' partita: un guasto, non dieci finestre mute.
            return _failure(SILENCE, _HA_SILENT)
        counts: list[int | None] = []
        for (start, _end), msg in zip(windows, replies, strict=True):
            series = msg.get("result") if msg and msg.get("success") else None
            if not isinstance(series, dict):
                counts.append(None)
                continue
            counts.append(sum(
                1
                for points in series.values() if isinstance(points, list)
                for point in points if isinstance(point, dict)
                and isinstance(point.get("lu") or point.get("lc"), int | float)
                and (point.get("lu") or point.get("lc")) > start
            ))
        return counts

    @cost(rest=1)
    async def calendars(self) -> dict:
        """L'elenco dei calendari di questa casa, via GET /api/calendars.

        **Trasporto verificato alla fonte, non assunto.** I tre fratelli di
        questo metodo -- `system_log()`, `traces()`,
        `trace()` piu' sotto -- leggono via WebSocket; i calendari
        no. Verificato su `home-assistant/core`,
        `homeassistant/components/calendar/__init__.py`, classe
        `CalendarListView` (`url = "/api/calendars"`), sui tag RILASCIATI che
        delimitano la finestra che `hiris/config.yaml:22` dichiara
        supportata (`2024.7.0`, il minimo) e la piu' recente vista finora
        (`2026.9.0`): **REST su entrambi**, corpo identico -- per ogni
        entita' del dominio `calendar`,
        `calendar_list.append({"name": state.name, "entity_id":
        entity.entity_id})`, poi `self.json(sorted(calendar_list, key=...
        "name"))`. E' la stessa via di `get_states()` qui sopra: stessa
        sessione, stesse intestazioni.

        (Su 2026.9.0 la vista filtra anche per permesso dell'utente sul
        token -- `user.permissions.check_entity(..., POLICY_READ)`, assente
        su 2024.7.0 -- ma HIRIS parla col token del Supervisor, che le ha
        tutte: la differenza non cambia cosa questo metodo vede in pratica.)

        **La forma e' una LISTA NUDA**, non un dizionario con una chiave --
        la stessa trappola dei tre fratelli (`system_log/list` e `trace/list`
        rispondono cosi', `trace/get` no), verificata di nuovo qui e non
        data per scontata: la lista contiene solo `name` ed `entity_id`,
        ordinata per nome da Home Assistant stesso.

        Il client legge e non giudica: le righe escono cosi' come HA le
        manda. `{"errore": ...}` su guasto -- connessione caduta, HTTP non
        200, o una risposta che non e' la lista attesa -- mai un
        `{"calendari": []}`: un elenco vuoto significherebbe «questa casa non
        ha calendari», un'affermazione diversa da «non sono riuscito a
        chiederlo».
        """
        reply = await self._rest_get("/api/calendars")
        if "errore" in reply:
            return reply
        data = reply["corpo"]
        if not isinstance(data, list):
            return _failure(SHAPE, "Home Assistant ha risposto in una forma non attesa")
        return {"calendari": data}

    @cost(rest=1)
    async def calendar_events(self, entity_id: str, start: str, end: str) -> dict:
        """Gli eventi di UN calendario in una finestra, via
        GET /api/calendars/<entity_id>?start=&end=.

        Stesso trasporto di `calendars()` qui sopra, verificato alla stessa
        fonte e sugli stessi due tag rilasciati (`2024.7.0`, `2026.9.0`):
        classe `CalendarEventView` (`url = "/api/calendars/{entity_id}"`),
        corpo identico su entrambi --
        `[dataclasses.asdict(event, dict_factory=_api_event_dict_factory)
        for event in calendar_event_list]`.

        **La forma e' anche qui una LISTA NUDA**, non un dizionario con una
        chiave `eventi`: verificata di nuovo, non ereditata per somiglianza
        da `calendars()`.

        **Ogni evento porta OTTO chiavi, sempre, anche quando valgono
        `null`** -- misurato sulla casa il 06/09/2026 su 297 eventi veri, e
        confermato alla fonte: `CalendarEvent` (`calendar/__init__.py`) e' un
        dataclass con esattamente questi otto campi (`start`, `end`,
        `summary`, `description`, `location`, `uid`, `recurrence_id`,
        `rrule`), e `_api_event_dict_factory` scrive OGNI campo del
        dataclass incluso quando vale `None` -- non filtra come fa invece
        `_list_events_dict_factory` (usata dal SERVIZIO `calendar.get_events`,
        funzione `async_get_events_service`, non da questa vista): chi
        consuma questo metodo non deve assumere che una chiave mancante
        significhi «assente», perche' non manca mai.

        `start`/`end` hanno **una delle due forme, mai entrambe** (stessa
        misura del 06/09/2026, stessa fonte): `{"dateTime":
        "2026-09-05T16:00:00+02:00"}` per un evento a orario, `{"date":
        "2026-08-17"}` per un evento giornaliero -- `_api_event_dict_factory`
        distingue guardando se il valore e' un `datetime.datetime` o un
        `datetime.date` nudo.

        Il client legge e non giudica: gli eventi escono cosi' come HA li
        manda, senza proiezioni -- cosa dire e cosa tacere e' di chi
        compone. `{"errore": ...}` su guasto, mai `{"eventi": []}`: **sulla
        casa vera i prossimi sette giorni sono vuoti su entrambi i
        calendari** (misurato 06/09/2026) -- il vuoto e' il caso NORMALE di
        questo metodo, non un guasto raro, e va comunque distinto da un
        guasto vero, o un calendario rotto e uno senza impegni
        risponderebbero la stessa identica cosa.

        **`summary`, `description` e `location` escono GREZZI, non
        sanificati.** E' una scelta deliberata e non un'omissione: li
        sanifica il consumatore, lo strumento `calendar` della chat
        (`home_space/tools.py::ToolDispatcher._calendar`). Un calendario
        condiviso e' un vettore di testo iniettato quanto un
        sensore-messaggio (L1-sicurezza.md). **Chi consuma questo metodo per
        metterlo in un prompt deve passare da `sanitize_ha_free_text` (o
        equivalente) da solo** -- il client qui non lo fa.

        Valida `entity_id` PRIMA di fare rete (stessa guardia di `history()`
        qui sopra): un identificatore ostile o malformato non
        deve comporre un URL, anche se il percent-encoding qui sotto chiude
        comunque l'iniezione.

        **Tetto a `MAX_CALENDAR_EVENTS` (vedi la costante qui sopra per la
        misura e la ragione del numero), ORDINATO e tagliato dalla TESTA --
        DIREZIONE OPPOSTA a `history()` qui sopra, e non per distrazione.**
        Per quella la finestra finisce ad ADESSO: la coda
        sono i punti piu' RECENTI, cioe' i piu' rilevanti, e
        tagliare dalla coda e' la scelta giusta (`points[-N:]` in
        `history()`). Per un calendario la
        finestra tipica PARTE da adesso e va in avanti: la coda sono gli
        eventi piu' LONTANI nel tempo, la testa sono i PROSSIMI
        appuntamenti -- esattamente cio' per cui questo strumento esiste.
        Tagliare dalla coda (una versione precedente di questo metodo lo
        faceva) scarterebbe proprio quello che serve, e lo farebbe in modo
        PREVEDIBILE proprio sulle integrazioni che rispondono gia'
        ordinate (es. `local_calendar`, Google) -- dove ci si aspetterebbe
        che funzionasse. Verificato alla stessa fonte: l'integrazione
        Google di Home Assistant tronca con `islice(timeline.active_after(
        now), max_events)` -- la TESTA di una timeline ordinata, i piu'
        vicini, non la coda.

        **Il contratto**: i primi `MAX_CALENDAR_EVENTS` eventi in ordine
        cronologico DALL'INIZIO della finestra chiesta; cio' che manca e'
        OLTRE quel punto. E' un contratto INDIPENDENTE dall'integrazione --
        a differenza di un taglio-coda-senza-ordinare, che dipenderebbe da
        un ordine che nessuna integrazione e' tenuta a garantire -- e vale
        identico anche per una finestra nel PASSATO ("cosa avevo segnato il
        mese scorso?"): "dall'inizio della finestra" resta la direzione
        giusta, i primi N sono i piu' vicini a quell'inizio.

        Per ordinare senza assumere che HA l'abbia gia' fatto, la chiave e'
        `start.get("dateTime") or start.get("date")`: sono sempre stringhe
        ISO-8601 in entrambe le forme misurate (vedi sopra), quindi
        l'ordinamento LESSICOGRAFICO su quella stringa e' gia' quello
        cronologico -- non serve parsare un `datetime`.

        **Perche' il lessicografico basta, detto con precisione.** Non e' una
        proprieta' generale delle stringhe ISO: `16:00+02:00` e `15:00Z` sono
        lo stesso ordine sbagliato, perche' si confronta l'ora SCRITTA e non
        l'istante. Regge perche' ogni `dateTime` esce dalla vista di HA gia'
        passato per `dt_util.as_local(value).isoformat()` (verificato alla
        fonte sui tag `2024.7.0` riga 417 e `2026.9.0` riga 445): un solo fuso,
        quello dell'istanza, e mai la forma `Z`. **L'unica eccezione e' l'ora
        ripetuta del ritorno all'ora solare** -- l'ultima domenica di ottobre
        fra le 2 e le 3, dove `02:30+02:00` esce dopo `02:00+01:00`. Due eventi
        entrambi dentro quell'ora possono uscire invertiti; e' dichiarato, non
        corretto, perche' parsare ogni istante per un'ora l'anno costerebbe piu'
        di quanto valga.
        Un giornaliero e un evento a orario dello stesso giorno finiscono
        nell'ordine giusto senza casi speciali: `"2026-09-05"` e' prefisso di
        `"2026-09-05T..."`, quindi precede ogni orario di quel giorno -- che e'
        vero, un giornaliero comincia a mezzanotte.

        `sorted(...)` invece di `list.sort()` per non mutare l'oggetto
        ricevuto; entrambi sarebbero stabili, e la stabilita' serve qui perche'
        a parita' di istante l'ordine con cui HA li ha mandati si conserva.

        **Un elenco tagliato non deve poter sembrare completo.** A
        differenza di `history()` qui sopra, che dichiara
        `troncato` SEMPRE (anche a falso), qui la chiave `troncato` esce **SOLO quando
        il taglio e' avvenuto** -- stessa disciplina di
        `elenco_incompleto`/`mute_da`/`entita_stato_ignoto` in
        `home_space/queries.py`: "le chiavi che non hanno niente da dire
        non escono", una legge del prodotto piu' generale del "sempre" dei
        due fratelli. E' una divergenza DICHIARATA fra le due convenzioni
        (stessa chiave, presenza diversa) tracciata in `docs/BACKLOG.md` --
        non corretta qui sui fratelli: e' fuori dal mio perimetro.
        """
        if not is_entity_id(str(entity_id)):
            logger.warning("calendario: entity_id non valido: %r", entity_id)
            return _failure(REQUEST, _truncate(f"entity_id non valido: {entity_id!r}", 200))
        if not isinstance(start, str) or not isinstance(end, str):
            # `quote()` solleverebbe su un istante che non e' scritto: la
            # domanda si ferma qui, con la busta, e non parte.
            return _failure(REQUEST, "la finestra non e' fatta di due istanti scritti")
        reply = await self._rest_get(
            f"/api/calendars/{quote(entity_id, safe='')}"
            f"?start={quote(start, safe='')}&end={quote(end, safe='')}")
        if "errore" in reply:
            return reply
        data = reply["corpo"]
        if not isinstance(data, list):
            return _failure(SHAPE, "Home Assistant ha risposto in una forma non attesa")

        def _chrono_key(event):
            begin = event.get("start") if isinstance(event, dict) else None
            begin = begin if isinstance(begin, dict) else {}
            return begin.get("dateTime") or begin.get("date") or ""

        ordered = sorted(data, key=_chrono_key)
        result: dict = {"eventi": ordered[:MAX_CALENDAR_EVENTS]}
        if len(ordered) > MAX_CALENDAR_EVENTS:
            result["troncato"] = True
        return result

    async def _ws_send(self, commands: list[tuple[str, dict | None]],
                       timeout: float = 10.0) -> list[dict | None]:
        """L'UNICO invio WebSocket del client: N comandi su UNA connessione →
        N messaggi interi, in ordine.

        Prima c'erano tre vie (`_ws_batch`, `_ws_request` che rendeva il solo
        `result`, `_ws_command` che rendeva il messaggio di un comando solo) e
        quattro `_ws_batch(...)[0]` riscritti a mano: tre contratti per la
        stessa cosa (A-28). Chi manda un comando solo scrive
        `(msg,) = await self._ws_send([(tipo, extra)])` e legge il messaggio.

        Prima ogni lettura WS apriva una sessione e una connessione nuove, con
        handshake e autenticazione completi, e le chiudeva: sei registri
        costavano sei handshake in serie. Qui il costo si paga una volta.

        Ogni elemento e' il messaggio INTERO ({success, result, error}), oppure
        `None` per i comandi rimasti senza risposta o se la connessione e'
        fallita del tutto: chi chiama decide se un guasto e' tollerabile.
        """
        replies: list[dict | None] = [None] * len(commands)
        if not commands:
            return replies
        ws_url = (
            self._base_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/websocket"
        )
        token = self._headers["Authorization"].removeprefix("Bearer ")
        types = [t for t, _ in commands]
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.ws_connect(ws_url) as ws,
            ):
                # Una riga per CONNESSIONE, non per comando: e' da qui che si
                # contano dal vivo le connessioni che HIRIS apre.
                logger.debug("_ws_send: una connessione, %d comandi (%s)",
                             len(commands), types)
                handshake = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                if handshake.get("type") == "auth_required":
                    await ws.send_json({"type": "auth", "access_token": token})
                    auth = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                    if auth.get("type") != "auth_ok":
                        logger.warning("HA WS auth failed in _ws_send(%s)", types)
                        return replies
                for msg_id, (msg_type, extra) in enumerate(commands, start=1):
                    payload = {"id": msg_id, "type": msg_type}
                    if extra:
                        payload.update(extra)
                    await ws.send_json(payload)
                awaited = set(range(1, len(commands) + 1))
                while awaited:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                    msg_id = msg.get("id")
                    if msg_id in awaited:
                        replies[msg_id - 1] = msg
                        awaited.discard(msg_id)
        except Exception as exc:
            logger.debug("_ws_send(%s) failed: %s", types, exc)
        return replies

    @cost(ws=1)
    async def statistic_ids(self) -> set[str] | dict:
        """Le entita' per cui Home Assistant TIENE statistiche, per nome.

        Home Assistant calcola statistiche di lungo periodo solo per le entita'
        che dichiarano uno `state_class`. Misurato sulla casa vera il
        15/09/2026: **130 entita' su 1206, tutte `sensor`** -- nessuno
        `switch`, `light`, `valve`, `binary_sensor`.

        Serve a dire il primo dei due «rifiuta se» della spec §6 (`docs/design/
        2026-09-10-i-tre-attori.md`): una serie vuota puo' voler dire *«quel
        giorno non e' arrivato niente»* oppure *«questa entita' non ne
        produrra' mai»*, e senza questa lettura le due sono indistinguibili.
        Nel resoconto del 14/09/2026, **18 rifiuti su 28** erano della seconda
        specie e dicevano la prima.

        **La busta e non `set()` quando la lettura fallisce.** Un insieme vuoto
        affermerebbe «nessuna entita' di questa casa ha statistiche», e con
        quella affermazione ogni misura del resoconto rifiuterebbe. Fino al
        03/10/2026 il guasto era `None`, una forma sua (D3).
        """
        (msg,) = await self._ws_send([("recorder/list_statistic_ids", None)])
        occurrence = self._ws_occurrence(msg, "statistiche")
        if "errore" in occurrence:
            return occurrence
        raw = occurrence["statistiche"]
        if not isinstance(raw, list):
            return _failure(SHAPE, "l'elenco delle statistiche non e' arrivato come elenco")
        return {str(r["statistic_id"]) for r in raw
                if isinstance(r, dict) and r.get("statistic_id")}

    @cost(ws=1)
    async def hourly_statistics(self, identifiers: list[str],
                                from_iso: str, to_iso: str) -> dict:
        """Le statistiche ORARIE di una finestra ESPLICITA: chi chiama (il
        resoconto di un giorno, la storia dei valori) ha bisogno di istanti
        precisi, non di «N giorni indietro da adesso».

        `from_iso`/`to_iso` sono istanti ISO gia' calcolati dal chiamante --
        stesso contratto di `history()` qui sopra: il fuso della casa e il
        confine di un «giorno» sono decisioni di CHI CHIAMA (`home_space/
        historian.py::day_boundaries`), non di questo client, che parla solo
        di istanti espliciti.

        `period="hour"` fisso: e' la grana che i chiamanti usano, e renderlo
        un parametro sarebbe generalita' speculativa.

        Richiesta e traduzione passano da `_request_statistics` (l'UNICO
        confine): contratto `{"serie": ...}` o `{"errore": ...}`.
        """
        return await self._request_statistics(
            identifiers, {"start_time": from_iso, "end_time": to_iso, "period": "hour"})

    #: Quale comando WebSocket porta la configurazione di un'entita', per
    #: dominio. `components/automation/__init__.py` e
    #: `components/script/__init__.py` registrano `<dominio>/config` e
    #: tornano `raw_config` -- la configurazione dell'ENTITA', quindi anche
    #: quella di un'automazione che vive in un pacchetto o in un `!include`.
    #: **Corretto il 27/09/2026 rileggendo il tag `2026.9.3`**: qui c'era
    #: scritto che entrambi sono `@websocket_api.require_admin`. Lo e' solo
    #: `automation/config`; `script/config` no.
    #: Un dominio che non e' qui dentro non ha una configurazione da chiedere,
    #: e non se ne inventa una.
    _CONFIG_COMMAND_BY_DOMAIN: ClassVar[dict[str, str]] = {
        "automation": "automation/config", "script": "script/config"}

    @cost(ws=1)
    async def behavior_configs(self, entity_ids: list[str]) -> dict:
        """Il corpo di automazioni e script, in **una raffica sola**.

        Torna `{"configurazioni": {entity_id: corpo}}` oppure
        `{"errore": str}` -- mai un dizionario vuoto, che direbbe «questa casa
        non ha automazioni» anche col websocket giu' (stessa disciplina di
        `related` e `problems`).

        **Se TUTTE le risposte mancano** (connessione o autenticazione
        cadute: `_ws_send` non solleva, torna una `None` per comando) il
        risultato e' `{"errore": ...}`, mai una mappa vuota. **Se solo alcune**
        mancano o sono rifiutate, le altre restano e le prime si nominano in
        `non_letti` -- `{entity_id: motivo}`, presente SOLO se c'e' almeno una
        voce non letta (stessa forma di `traces`).

        **Una voce che non risponde MANCA dalla mappa, e non vale `{}`**:
        «non ho letto il corpo» e «il corpo e' vuoto» sono due fatti diversi --
        il primo e' un limite di HIRIS, il secondo un fatto sulla casa -- e
        chi archivia deve poterli distinguere per dichiarare il proprio punto
        cieco.

        Misurato sulla casa vera il 10/09/2026: 20 configurazioni in **18 ms**
        su una connessione sola, 44 KB in tutto.

        **La rotta HTTP `/api/config/automation/config/{id}` NON e'
        equivalente**: legge solo `automations.yaml`, quindi non vedrebbe le
        automazioni scritte nei pacchetti o negli `include` -- il punto cieco
        che questa lettura esiste per chiudere.
        """
        wanted = [(eid, self._CONFIG_COMMAND_BY_DOMAIN.get(domain_of(eid)))
                  for eid in entity_ids]
        wanted = [(eid, command) for eid, command in wanted if command]
        if not wanted:
            return {"configurazioni": {}}
        replies = await self._ws_send(
            [(command, {"entity_id": eid}) for eid, command in wanted])
        if all(reply is None for reply in replies):
            return _failure(SILENCE, _HA_SILENT)
        configs: dict[str, dict] = {}
        unread: dict[str, str] = {}
        for index, (eid, _command) in enumerate(wanted):
            msg = replies[index] if index < len(replies) else None
            if msg is None:
                unread[eid] = "Home Assistant non ha risposto in tempo"
                continue
            occurrence = self._ws_occurrence(msg, "corpo")
            if "errore" in occurrence:
                unread[eid] = occurrence["errore"]
                continue
            result = occurrence["corpo"]
            body = result.get("config") if isinstance(result, dict) else None
            if isinstance(body, dict):
                configs[eid] = body
            else:
                unread[eid] = "risposta in forma inattesa"
        answer: dict = {"configurazioni": configs}
        if unread:
            answer["non_letti"] = unread
        return answer

    async def _request_statistics(self, identifiers: list[str],
                                  window: dict) -> dict:
        """`recorder/statistics_during_period` -> `{"serie": ...}` o
        `{"errore": ...}`. L'UNICO punto che parla con questo comando WS e
        l'UNICO che traduce la sua risposta. Chi chiama passa solo la FINESTRA
        (`start_time`/`end_time`/`period`): la richiesta e la traduzione
        delle chiavi sono qui una volta sola (fondamenta 2, nessun doppione).

        Nessun `types` esplicito nella richiesta: **misurato il 27/08/2026
        sulla casa vera** che, senza restringerlo, Home Assistant risponde
        con TUTTI i campi che sa calcolare per quello `statistic_id` --
        `state`/`sum`/`change` per un contatore (`state_class: total_
        increasing`/`total`), `mean`/`min`/`max` per una misura istantanea
        (`state_class: measurement`, es. la percentuale di batteria) --
        cosi' una sola chiamata serve entrambe le forme senza dover sapere
        in anticipo di quale delle due si tratta.

        Le chiavi si traducono qui, all'unico confine con Home Assistant:
        `start`/`end`/`min`/`max`/`mean`/`sum`/`state`/`change` sono il
        vocabolario di HA, e lasciarle passare significherebbe farle
        affiorare fino al modello (o al bilancio) mescolate a chiavi
        italiane. `somma`/`stato`/`cambio` ci sono solo quando HA li manda
        DAVVERO -- si omettono, invece di metterli a `None`: un valore nullo
        e un campo assente non sono lo stesso fatto (una somma nulla
        direbbe "azzerata", non "non richiesta a questo `statistic_id`").

        **La forma esatta, misurata il 27/08/2026** (mandato «il bilancio
        dell'energia», che corregge il debito dichiarato in `statistiche`:
        «mai girata in produzione», misurato prima solo sulla documentazione).
        Su `sensor.ze1es030n5e528_energia_prodotta_oggi` (un contatore
        `total_increasing` che si azzera ogni notte), l'ora 07-08 di una
        giornata vera:
        `{"start": 1787724000000, "end": 1787727600000, "sum": 173.77,
        "state": 0.27, "change": 0.27}`. `change` e' il delta di QUELL'ora,
        calcolato da HA e GIA' corretto per gli azzeramenti (la somma dei
        `change` di un giorno intero, provata sullo stesso sensore, torna
        identica a `ultimo.somma - primo.somma`): e' il numero giusto per
        «la forma ora per ora» del bilancio, senza doverlo ricostruire
        sottraendo `somma` a mano.

        Ritorna `{"serie": {statistic_id: [{"inizio","fine","minimo",
        "massimo","media",["somma"],["stato"],["cambio"]}]}}`, oppure
        `{"errore": str}` -- mai `{}`, che direbbe «non ci sono statistiche»
        anche quando il websocket e' giu'.
        """
        (msg,) = await self._ws_send([(
            "recorder/statistics_during_period",
            {"statistic_ids": list(identifiers), **window},
        )])
        occurrence = self._ws_occurrence(msg, "serie")
        if "errore" in occurrence:
            return occurrence
        raw = occurrence["serie"]
        if not isinstance(raw, dict):
            return _failure(SHAPE, "le statistiche non sono arrivate come oggetto")
        return {"serie": _translate_statistics(raw)}

    # I tipi che `search/related` accetta, coi VALORI di `ItemType`
    # (`components/search/__init__.py`), non coi nomi delle costanti. Chiesti
    # alla tabella che li traduce (`ha_vocabulary.LINK_NAME`): scritti una
    # volta sola (B-48, 04/10/2026).
    RELATED_ITEM_TYPES = tuple(LINK_NAME)

    @cost(ws=1)
    async def related(self, item_type: str, identifier: str) -> dict:
        """Chi tocca questa cosa, secondo Home Assistant.

        `search/related` e' calcolato da HA su TUTTO cio' che ha caricato,
        ovunque sia scritto. HIRIS legge invece `automations.yaml` e
        `scripts.yaml`: non vede i pacchetti, gli `!include`, le cartelle, le
        scene ne' i gruppi -- cioe' tutto cio' che una casa cresciuta usa
        davvero. Crede di conoscere il comportamento della casa e ne conosce
        la parte scritta in due file.

        Non SOSTITUISCE quella lettura: i file portano il CORPO (cosa fa
        l'automazione), questo porta i LEGAMI (chi tocca cosa). Sono due fatti
        diversi sullo stesso oggetto, e confonderli rifarebbe la confusione
        fra dichiarato e dedotto che questo progetto paga da sempre.

        Restituisce `{tipo: [identificatori]}` -- HA manda insiemi, che
        viaggiano in JSON come liste in ordine ARBITRARIO: si ordinano, o due
        letture identiche producono due risposte diverse.

        `{"errore": ...}` su guasto: un elenco vuoto significherebbe «questa
        cosa non la tocca nessuno», che e' un'affermazione, non un silenzio.
        Il componente `search` e' dipendenza di `frontend`, quindi c'e' in
        ogni HA con interfaccia -- ma un rifiuto va comunque distinto da un
        «niente».
        """
        if item_type not in self.RELATED_ITEM_TYPES:
            return _failure(REQUEST, f"tipo non riconosciuto da Home Assistant: {item_type}")
        (msg,) = await self._ws_send(
            [("search/related", {"item_type": item_type, "item_id": identifier})])
        occurrence = self._ws_occurrence(msg, "legami")
        if "errore" in occurrence:
            return occurrence
        result = occurrence["legami"]
        if not isinstance(result, dict):
            return _failure(SHAPE, "risposta in forma inattesa")
        return {key: sorted(str(v) for v in values)
                for key, values in result.items() if values}

    @cost(ws=1)
    async def problems(self) -> dict:
        """I guasti che Home Assistant ha GIA' diagnosticato.

        `repairs/list_issues`. Oggi, alla domanda «c'e' qualcosa che non va in
        casa?», HIRIS sa solo contare le entita' non disponibili: HA tiene un
        registro dei problemi con la severita', se sono riparabili, e in quale
        versione qualcosa si rompera'.

        Restituisce `{"problemi": [...]}` con le righe cosi' come HA le manda
        (`domain`, `issue_id`, `severity`, `is_fixable`, `breaks_in_ha_version`,
        `ignored`, `translation_key`, ...) -- la scelta di cosa dire e cosa
        tacere NON e' del client: e' di chi compone. Qui si legge soltanto.

        Si scartano solo le IGNORATE (`ignored`, cioe' `dismissed_version` non
        nullo): l'utente ha gia' detto «non dirmelo», e ripeterglielo sarebbe
        disobbedire a una scelta che ha espresso in Home Assistant. HA stesso
        filtra gia' le non attive.

        `{"errore": ...}` su guasto, per la stessa ragione dei legami: un
        elenco vuoto significherebbe «non c'e' niente che non va».
        """
        (msg,) = await self._ws_send([("repairs/list_issues", None)])
        occurrence = self._ws_occurrence(msg, "problemi")
        if "errore" in occurrence:
            return occurrence
        result = occurrence["problemi"]
        if not isinstance(result, dict) or not isinstance(result.get("issues"), list):
            return _failure(SHAPE, "risposta in forma inattesa")
        return {"problemi": [p for p in result["issues"]
                             if isinstance(p, dict) and not p.get("ignored")]}

    @cost(ws=1)
    async def system_log(self) -> dict:
        """Le righe che Home Assistant ha GIA' raccolto nel proprio registro
        di errori.

        `system_log/list`, WS, `require_admin` -- HIRIS parla col token del
        Supervisor, quindi lo puo' chiamare. Verificato alla fonte
        (`homeassistant/components/system_log/__init__.py`, funzione
        `list_errors`): il comando torna una LISTA NUDA, non un dizionario
        con una chiave come `repairs/list_issues` --
        `connection.send_result(msg["id"], hass.data[DOMAIN].records.to_list())`.

        Restituisce `{"voci": [...]}` con le righe cosi' come HA le manda
        (`name`, `message`, `level`, `source`, `timestamp`, `exception`,
        `count`, `first_occurred` -- da `LogEntry.to_dict()`, stessa fonte):
        come per `problems()` e `related()`, il client legge e non giudica,
        cosa dire e cosa tacere e' di chi compone.

        L'ORDINE non e' rimescolato: `DedupStore.to_list()` (stessa fonte,
        `"Return reversed list of log entries - LIFO"`) manda gia' la piu'
        recente per prima. Chi consuma questo metodo non deve ipotizzarlo.

        Non esiste un «piu' in basso» da cui leggere il grezzo: HA deduplica
        gia' dentro il proprio gestore (`DedupStore.add_entry`), su chiave
        `(logger, posizione nel sorgente, causa radice)` -- cioe' `LogEntry.
        key = (self.name, self.source, self.root_cause)`, stessa fonte --
        PRIMA di qualunque cosa HIRIS possa raggiungere. `count` e
        `first_occurred` sono gia' il risultato di quella deduplicazione:
        disfarli qui vorrebbe dire inventare un dato che HA non manda piu'.

        `{"errore": ...}` su guasto, per la stessa ragione di `problemi` e
        `legami`: un elenco vuoto significherebbe «non c'e' niente nel
        registro», che e' un'affermazione, non un silenzio.
        """
        (msg,) = await self._ws_send([("system_log/list", None)])
        occurrence = self._ws_occurrence(msg, "voci")
        if "errore" in occurrence:
            return occurrence
        result = occurrence["voci"]
        if not isinstance(result, list):
            return _failure(SHAPE, "risposta in forma inattesa")
        return {"voci": result}

    @cost(ws=1)
    async def traces(self, keys: list[tuple[str, str]]) -> dict:
        """Le esecuzioni RECENTI di piu' automazioni e script, in **una
        raffica sola** (`trace/list`, WS, `require_admin`).

        Nasce il 30/09/2026 con la storia (spec `2026-09-30-la-storia.md`
        §1 e §8 punto 3): «perche' sono partite le automazioni dei rifiuti» costava
        cinque chiamate allo strumento e cinque connessioni. `keys` e'
        `[(domain, item_id)]`: per un'automazione `item_id` e' l'id della
        CONFIGURAZIONE (la catena e' qui sotto); per uno script e' la sua
        chiave di configurazione, che e' anche il suo `unique_id` e il suo
        `object_id` (`script.<chiave>`) -- VERIFICATO ALLA FONTE il
        30/09/2026 sui tag `2024.7.0` e `2026.9.0`:

        - `components/script/__init__.py`: `self._attr_unique_id = key`
          (2024.7.0 r.509, 2026.9.0 r.568) e `self.entity_id =
          ENTITY_ID_FORMAT.format(key)` (r.511 / r.570): stessa chiave;
        - `_async_run` traccia con `trace_script(self.hass, self.unique_id,
          ...)` (2024.7.0 r.637-639; 2026.9.0 r.708-710 con `_attr_unique_id`);
        - `components/script/trace.py`: `ScriptTrace._domain = DOMAIN` (r.22
          / r.20), `trace_script(hass, item_id, ...)` (r.28 / r.26) e
          `ScriptTrace(item_id, ...)`: la chiave e' `script.<item_id>`;
        - `components/trace/websocket_api.py`, `trace/list` (r.87-101) e
          `trace/get` (r.53-69), identici sui due tag: `domain` (validato
          contro `TRACE_DOMAINS`) e `item_id` (stringa libera) si ricompongono
          in `f"{domain}.{item_id}"`, senza passare dal registro delle entita'.

        Per gli script, dunque, l'`object_id` dell'entita' E' l'`item_id`.

        **Per un'automazione l'`item_id` e' l'id della CONFIGURAZIONE, non
        l'`object_id` dell'entita'** -- e non e' una sfumatura: e' la
        differenza fra leggere le tracce e non leggerne mai nessuna. La
        catena, verificata alla fonte sui tag RILASCIATI `2024.7.0` e
        `2026.9.0` (non su `dev`), anello per anello:

        1. `components/automation/__init__.py` traccia con
           `trace_automation(self.hass, self.unique_id, ...)`;
        2. nella stessa classe, `self._attr_unique_id = automation_id`, e
           `automation_id: str | None = config_block.get(CONF_ID)` -- cioe'
           la chiave `id:` della configurazione, quella che l'interfaccia di
           HA genera come timbro numerico (`"1771346155970"`);
        3. `components/trace/models.py`, `ActionTrace.__init__`:
           `self.key = f"{self._domain}.{item_id}"`, con `_domain` fisso a
           `"automation"` (`components/automation/trace.py`,
           `AutomationTrace._domain = DOMAIN`);
        4. `components/trace/websocket_api.py`, `websocket_trace_list` e
           `websocket_trace_get`: ricompongono
           `key = f"{msg['domain']}.{msg['item_id']}"` e lo cercano nel
           magazzino con un `.get(key)` NUDO -- nessuna validazione, nessun
           passaggio dal registro delle entita'.

        Sulla casa vera tutte e diciotto le automazioni hanno un `id` di
        configurazione DIVERSO dall'`object_id`: mandare l'`object_id`
        significa `[]` per ognuna, sempre, scattata o no -- un vuoto che
        legge come «non ha mai girato».

        **La risoluzione `entity_id -> id di configurazione` NON avviene
        qui**, ma ai chiamanti (`server.py::watch_automation_outcomes` e la
        storia, `ToolDispatcher._run_history`), dove lo specchio dello stato
        gia' vive: il client resta «legge e non giudica». L'id sta in
        `attributes["id"]` dello stato dell'entita' --
        `BaseAutomationEntity.capability_attributes` (`{CONF_ID:
        self.unique_id}`, solo `if self.unique_id is not None`), e
        `helpers/entity.py::__async_calculate_state` copia le capability
        attributes dentro gli attributi dello stato (verificato su entrambi
        i tag).

        **Un'automazione YAML scritta SENZA `id:`** non e' un caso teorico:
        `unique_id` resta `None`, `capability_attributes` torna `None`
        (quindi NESSUN `attributes["id"]` da risolvere), e la sua traccia
        finisce sotto la chiave letterale `"automation.None"` --
        `async_store_trace` la memorizza davvero, ma quella chiave e'
        CONDIVISA da tutte le automazioni senza `id`, e `trace_automation`
        non chiama nemmeno `finished()` su di esse (`finally: if
        automation_id: trace.finished()`). Non sono tracce indirizzabili per
        automazione: chi non risolve l'id non deve ripiegare sull'`object_id`
        ne' sulla stringa `"None"`, deve dire che non riesce a risolvere --
        che NON e' «non ha mai girato».

        Ogni risposta di `trace/list` e' una LISTA NUDA
        (`async_list_traces(...) -> list[dict[str, Any]]`), non un
        dizionario con una chiave come `repairs/list_issues`: le righe
        (`ActionTrace.as_short_dict()`, `trace/models.py`, verificato) portano
        `run_id`, `state`, `script_execution`, `timestamp` (`start`/`finish`),
        `domain`, `item_id`, `last_step`, e -- solo quando presenti --
        `not_triggered` ed `error`.

        **HA non conserva tutte le esecuzioni**, verificato alla fonte:
        `stored_traces` (`homeassistant/components/trace/const.py`,
        `DEFAULT_STORED_TRACES = 5`) e' configurabile per automazione in YAML
        (`trace: stored_traces: N`). Da HA 2026.7.0 in poi (tag `2026.7.0`,
        `2026.8.0`, `2026.9.0`) il tetto e' PER SECCHIO -- le esecuzioni
        scattate (`runs`) e quelle valutate ma non scattate (`not_triggered`)
        vivono in due `LimitedSizeDict` distinti (`TraceBuckets`,
        `trace/models.py`; `async_store_trace`, `trace/util.py`), quindi fino
        al DOPPIO di `stored_traces` tracce vive; su HA 2026.6.0 e prima, fino
        al minimo dichiarato 2024.7.0 (tag `2024.7.0` e `2026.6.0`), un solo
        dizionario per automazione, tetto TOTALE pari a `stored_traces`. Chi
        consuma questo metodo non deve assumere il caso piu' recente solo
        perche' e' quello su cui gira la casa di sviluppo.

        Fino al 04/10/2026 esisteva anche `automation_traces(automation_id)`,
        la stessa lettura per UNA automazione: il giro delle tracce la
        chiamava una volta per automazione segnata, una connessione per
        ognuna. Il giro passa da qui (Tappa 2, Task 8, A-21 e A-32), e quel
        metodo e' uscito senza chiamanti.

        Torna `{"tracce": {"<domain>.<item_id>": [...]}, "non_letti": {...}}`:
        una chiave che Home Assistant rifiuta, o che non risponde, finisce in
        `non_letti` col suo motivo e NON spegne le altre -- e non diventa mai
        `[]`, che direbbe «non e' mai partita». Il client legge e non giudica:
        le righe escono come Home Assistant le manda.

        **`_ws_send` non solleva mai**: connessione caduta, autenticazione
        rifiutata o timeout totale tornano come UNA `None` per comando
        (`_ws_send`, `except Exception` finale; `tests/test_ha_client_invio.py`).
        Quindi la «raffica che non parte» e' quella in cui TUTTE le risposte
        sono `None`: `{"errore": ...}`, mai «nessuna esecuzione». Se solo
        alcune sono `None` (il timeout ne taglia la coda), quelle chiavi
        vanno in `non_letti` con «non ha risposto in tempo».

        **Una chiave SCONOSCIUTA torna `[]`, non un errore**: un id di script
        scritto male, o un'automazione YAML senza `id:` (che vive sotto
        `automation.None`, condivisa), sono indistinguibili da «mai partita».
        `trace/util.py::_get_debug_traces` usa `.get(key)` e non solleva.
        Perche' un `[]` significhi qualcosa, **il chiamante DEVE risolvere le
        chiavi PRIMA di chiedere**, e una chiave irrisolta va in `non_letti`
        senza essere mandata qui.
        """
        if not keys:
            return {"tracce": {}, "non_letti": {}}
        replies = await self._ws_send(
            [("trace/list", {"domain": domain, "item_id": item_id})
             for domain, item_id in keys])
        if all(reply is None for reply in replies):
            return _failure(SILENCE, _HA_SILENT)
        found: dict[str, list] = {}
        unread: dict[str, str] = {}
        for index, (domain, item_id) in enumerate(keys):
            key = f"{domain}.{item_id}"
            msg = replies[index] if index < len(replies) else None
            if msg is None:
                unread[key] = "Home Assistant non ha risposto in tempo"
                continue
            reading = self._trace_list(msg)
            if "errore" in reading:
                unread[key] = reading["errore"]
                continue
            found[key] = reading["tracce"]
        return {"tracce": found, "non_letti": unread}

    @classmethod
    def _trace_list(cls, msg: dict | None) -> dict:
        """UNA risposta di `trace/list` -> `{"tracce": [...]}` o la busta. La
        forma e' una LISTA NUDA (vedi `traces`)."""
        occurrence = cls._ws_occurrence(msg, "tracce")
        if "errore" in occurrence:
            return occurrence
        if not isinstance(occurrence["tracce"], list):
            return _failure(SHAPE, "risposta in forma inattesa")
        return occurrence

    @cost(ws=1)
    async def trace(self, domain: str, item_id: str, run_id: str) -> dict:
        """UNA esecuzione di un'automazione o di uno script, col grafo intero
        dei passi (`trace/get`, WS, `require_admin`): stessa fonte e stessa
        chiave di `traces`, piu' `run_id`.

        Il risultato E' un dizionario (`ActionTrace.as_extended_dict()`,
        verificato): i campi della riga breve piu' `trace`, `config`,
        `blueprint_inputs`, `context`. Se `run_id` e' gia' uscito dal tetto,
        Home Assistant risponde con un errore esplicito (`ERR_NOT_FOUND`), che
        arriva qui come ogni altro rifiuto. `{"errore": ...}` su ogni guasto.
        """
        (msg,) = await self._ws_send(
            [("trace/get", {"domain": domain, "item_id": item_id,
                            "run_id": run_id})])
        occurrence = self._ws_occurrence(msg, "traccia")
        if "errore" in occurrence:
            return occurrence
        if not isinstance(occurrence["traccia"], dict):
            return _failure(SHAPE, "risposta in forma inattesa")
        return occurrence

    @cost(ws=1)
    async def get_translations(self, language: str,
                               category: str = "entity_component") -> dict:
        """Le traduzioni che Home Assistant pubblica, per una lingua e una
        categoria.

        `{"risorse": {chiave: testo}}` oppure `{"errore": ...}` -- mai un
        dizionario vuoto su guasto: un elenco vuoto direbbe «questa casa non
        traduce niente», che e' un'altra cosa dal non aver potuto chiedere.
        Stesso contratto di `problems()`/`system_log()` qui sopra, per la
        stessa ragione.

        Il comando e' `frontend/get_translations`
        (`homeassistant/components/frontend/__init__.py:467`, tag `2026.9.1`),
        `language` e `category` obbligatori (`:1007-1015`), risposta
        `{"resources": {...}}` (`:1028-1030`). **Non ha `@require_admin`**
        (`:1007-1019`): qualunque connessione autenticata puo' chiamarlo, e
        il proxy del Supervisor non filtra il prefisso `frontend/`
        (`supervisor/api/middleware/security.py:45-50` @ `2026.09.0`).

        Qui si LEGGE soltanto: la scelta di quale categoria serva, e di come
        si costruisce una chiave, sta in `proxy/state_translations.py` -- il
        client non ha un'opinione su cosa della casa valga la pena tenere.
        """
        (msg,) = await self._ws_send([(
            "frontend/get_translations",
            {"language": language, "category": category})])
        occurrence = self._ws_occurrence(msg, "risorse")
        if "errore" in occurrence:
            return occurrence
        result = occurrence["risorse"]
        resources = result.get("resources") if isinstance(result, dict) else None
        if not isinstance(resources, dict):
            return _failure(SHAPE, "risposta in forma inattesa")
        return {"risorse": resources}

    @cost(ws=1)
    async def get_config(self) -> dict:
        """Il sistema di riferimento della casa, da `get_config` di HA.

        Restituisce il dizionario grezzo di Home Assistant, oppure la busta del
        guasto -- fino al 03/10/2026 era `{}`, che si leggeva come «la casa
        non dichiara niente» (D3). A distillarlo e' `topology.reference_frame`:
        qui si LEGGE soltanto, cosi' il client non ha un'opinione su cosa
        della casa valga la pena tenere.

        NON e' un registro e non passa da `read_registries`: quello lavora su
        liste di righe (`isinstance(risultato, list)`), questo torna un
        dizionario. Infilarcelo avrebbe voluto dire allargare la forma di
        `read_registries` per un solo caso speciale -- CONSISTENZA: una
        funzione che restituisce registri restituisce registri.

        Il comando esiste in `websocket_api/commands.py` (`handle_get_config`)
        e la forma della risposta e' `Config.as_dict()` in `core_config.py`.
        """
        (msg,) = await self._ws_send([("get_config", None)])
        occurrence = self._ws_occurrence(msg, "sistema")
        if "errore" in occurrence:
            return occurrence
        if not isinstance(occurrence["sistema"], dict):
            return _failure(SHAPE, "il sistema di riferimento non e' arrivato come oggetto")
        return occurrence["sistema"]

    @cost(ws=1)
    async def energy_prefs(self) -> dict:
        """Cio' che la dashboard Energia dichiara: chi e' rete, sole, batteria,
        gas, acqua, e quali dispositivi consumano -- dichiarato dall'utente,
        mai indovinato dal nome dei sensori (CLAUDE.md, «su Home Assistant non
        si ipotizza mai»: l'energia prodotta letta come «consumo» e' nata qui).

        Restituisce le preferenze di Home Assistant COME SONO, oppure la busta
        del guasto. Il client legge soltanto: quale entita' abbia quale ruolo
        lo dice la casa (piano degli attori, Task 2.2), non questo metodo.

        **La forma, letta sul sorgente al tag `2026.9.4` il 04/10/2026, non
        ancora misurata su questa casa** (Task 2.0 del piano degli attori).
        `ws_get_prefs` (`components/energy/websocket_api.py`) manda
        `manager.data` intero: `{"energy_sources": [...], "device_consumption":
        [...], "device_consumption_water": [...]}` (`data.py`,
        `EnergyPreferences`). Ogni sorgente ha un `type` -- `grid`, `solar`,
        `battery`, `gas`, `water` -- e porta i suoi sensori in campi SINGOLI:
        la rete `stat_energy_from` (prelievo) e `stat_energy_to` (immissione),
        entrambi anche `None`; la batteria `stat_energy_from` (scarica),
        `stat_energy_to` (carica) e, se dichiarati, `stat_soc` e `capacity`.

        **La trappola di `grid`.** Il formato vecchio della rete portava liste
        (`flow_from`/`flow_to`); Home Assistant lo migra al formato a campi
        singoli quando carica le preferenze (`_EnergyPreferencesStore`,
        `STORAGE_MINOR_VERSION = 3`), quindi al tag letto non esce piu'. Il
        client non lo traduce e non lo rifiuta: lo passa com'e', e a giudicarlo
        e' chi legge. Che la rete di QUESTA casa arrivi a campi singoli era
        gia' stato misurato il 27/08/2026 (docstring di `energy_directions`,
        uscita il 30/09/2026 senza chiamanti).

        **Una casa senza dashboard Energia** non ha preferenze: Home Assistant
        rifiuta il comando con `not_found` / «No prefs». E' la busta del
        rifiuto, col codice di Home Assistant: «non dichiarato» e «non ho
        potuto leggere» restano distinguibili dal `codice`, e una dashboard
        vuota non si inventa.
        """
        (msg,) = await self._ws_send([("energy/get_prefs", None)])
        occurrence = self._ws_occurrence(msg, "preferenze")
        if "errore" in occurrence:
            return occurrence
        prefs = occurrence["preferenze"]
        if not isinstance(prefs, dict) or not isinstance(prefs.get("energy_sources"), list):
            return _failure(SHAPE, "le preferenze della dashboard Energia non sono "
                                   "arrivate nella forma di Home Assistant")
        return prefs

    # Gli ambiti delle categorie di Home Assistant. Sono partizionate per
    # ambito: chiederne uno solo farebbe sparire la tassonomia che l'utente ha
    # scritto sugli script o sugli helper, contro il principio per cui il
    # significato e' dichiarato e non dedotto. Costano quattro comandi sulla
    # stessa connessione: praticamente nulla.
    _CATEGORY_SCOPES = ("automation", "script", "scene", "helpers")

    # I registri che l'utente ha gia' compilato in Home Assistant. Sono la
    # spina dorsale del significato per HIRIS: piani, aree, dispositivi,
    # etichette e categorie sono la tassonomia che ha scelto lui — non serve
    # dedurla, e dedurla costerebbe token e sbaglierebbe in silenzio.
    # Le voci "categorie" sono una per ambito (vedi _CATEGORY_SCOPES) e
    # condividono tutte la chiave "categorie": `read_registries` e
    # `read_registry` le fondono in un'unica lista, marcando ogni riga con il
    # proprio ambito (`_registry_rows`).
    _REGISTRIES: list[tuple[str, str, dict | None]] = [
        ("piani",        "config/floor_registry/list",        None),
        ("aree",         "config/area_registry/list",         None),
        ("dispositivi",  "config/device_registry/list",       None),
        ("entita",       "config/entity_registry/list",       None),
        ("etichette",    "config/label_registry/list",        None),
        ("integrazioni", "config_entries/get",               None),
    ] + [
        ("categorie", "config/category_registry/list", {"scope": scope})
        for scope in _CATEGORY_SCOPES
    ]

    def _registry_rows(self, entry: tuple[str, str, dict | None],
                       msg: dict | None) -> dict:
        """Le righe di UN comando di registro, `{"righe": [...]}`, o la busta
        del guasto.

        L'unico posto in cui si legge la risposta di un registro: la usano
        `read_registry` e `read_registries`, cosi' un registro letto da solo e
        lo stesso letto con gli altri hanno la stessa forma (fondamenta 3). Le
        categorie escono marcate col proprio `ambito`: Home Assistant non lo
        riporta nelle righe (vedi `read_registries`).
        """
        key, _msg_type, extra = entry
        occurrence = self._ws_occurrence(msg, "righe")
        if "errore" in occurrence:
            return occurrence
        rows = occurrence["righe"]
        if not isinstance(rows, list):
            return _failure(SHAPE, f"il registro «{key}» non e' arrivato come elenco")
        scope = extra.get("scope") if key == "categorie" and extra else None
        if scope:
            rows = [{**row, "ambito": scope} for row in rows]
        return {"righe": rows}

    @cost(ws=1)
    async def read_registry(self, registry: str) -> dict:
        """UN registro della casa: `{nome: righe}`, oppure la busta del guasto.

        Per chi ha bisogno di un registro e non dell'anagrafe intera (A-01,
        A-06, 03/10/2026): il recapito delle promesse, l'officina, il giro
        delle condizioni. I nomi e i comandi sono quelli di `_REGISTRIES` --
        la stessa tabella di `read_registries`, non una seconda -- e un
        registro costa un comando (le categorie uno per ambito, sulla stessa
        connessione). **Niente alias**: il secondo giro
        `config/entity_registry/get_entries` serve solo all'anagrafe, e resta
        in `read_registries`.

        A differenza di `read_registries`, un registro caduto non diventa una
        lista vuota: e' la busta, con la sua causa. Chi chiede un registro solo
        non ha un'anagrafe da costruire comunque, e un elenco vuoto direbbe «la
        casa non ne ha». E' la ragione per cui `list_labels`, che rendeva `[]`
        muto a una risposta in forma inattesa, e' uscita al suo posto (A-33).
        """
        entries = [entry for entry in self._REGISTRIES if entry[0] == registry]
        if not entries:
            known = ", ".join(dict.fromkeys(key for key, _, _ in self._REGISTRIES))
            return _failure(REQUEST, f"«{registry}» non e' un registro che so leggere. "
                                     f"Registri: {known}.")
        replies = await self._ws_send([(msg_type, extra) for _, msg_type, extra in entries])
        rows: list[dict] = []
        for entry, msg in zip(entries, replies):
            read = self._registry_rows(entry, msg)
            if "errore" in read:
                return read
            rows.extend(read["righe"])
        return {registry: rows}

    @cost(ws=2)
    async def read_registries(self) -> tuple[dict[str, list[dict]], list[str]]:
        """Tutti i registri della casa, su una connessione sola, piu' il giro
        degli alias. **E' la lettura dell'anagrafe** (`topology.rebuild`): chi
        vuole un registro solo usa `read_registry`.

        Restituisce `(registri, non_disponibili)`. Un registro che manca o
        fallisce diventa una lista vuota — un Home Assistant senza piani deve
        comunque produrre un'anagrafe — ma il suo nome finisce in
        `non_disponibili`: una casa senza piani e un registro dei piani caduto
        producono la stessa lista vuota, e chi ci costruisce sopra deve poterli
        distinguere. Il valore restituito lo dice; un commento no.

        Le categorie sono chieste per ogni ambito (automation, script, scene,
        helpers): ogni categoria restituita porta un campo `ambito` proprio,
        perche' HA non lo include e due categorie omonime in ambiti diversi
        sarebbero altrimenti indistinguibili. Se un singolo ambito fallisce,
        `non_disponibili` riporta quale (es. `categorie:script`), non un
        generico `categorie`.
        """
        commands = [(msg_type, extra) for _, msg_type, extra in self._REGISTRIES]
        replies = await self._ws_send(commands)
        registries: dict[str, list[dict]] = {}
        unavailable: list[str] = []
        for entry, msg in zip(self._REGISTRIES, replies):
            key, msg_type, extra = entry
            read = self._registry_rows(entry, msg)
            if "errore" in read:
                scope = extra.get("scope") if extra else None
                name = f"{key}:{scope}" if key == "categorie" and scope else key
                # Tre guasti diversi, tre diciture, scelte dalla causa della
                # busta di `_registry_rows`: il rifiuto porta il motivo che
                # Home Assistant ha scritto, non il nome del comando che gia'
                # sapevamo; la forma inattesa mostra cosa e' arrivato; il
                # silenzio dice che HA non ha mai parlato.
                if read["causa"] == REFUSAL:
                    logger.debug("registro %s rifiutato da Home Assistant: %s (%s)",
                                 name, read["errore"], msg_type)
                elif read["causa"] == SHAPE:
                    logger.debug("registro %s risposta in forma inattesa (%s): %r",
                                 name, msg_type, msg.get("result"))
                else:
                    logger.debug("registro %s non disponibile: nessuna risposta "
                                 "dal comando (%s)", name, msg_type)
                unavailable.append(name)
                rows = []
            else:
                rows = read["righe"]
            registries.setdefault(key, []).extend(rows)

        await self._add_extended_fields(registries, unavailable)
        return registries, unavailable

    async def _add_extended_fields(self, registries: dict[str, list[dict]],
                                   unavailable: list[str]) -> None:
        """Gli ALIAS delle entita', che `config/entity_registry/list` non manda.

        Quel comando risponde con `RegistryEntry.as_partial_dict`
        (`helpers/entity_registry.py`), che NON contiene `aliases` -- ne'
        `device_class`, ne' `capabilities`. Stanno solo in `extended_dict`,
        servito da `config/entity_registry/get_entries`, che vuole l'elenco
        degli `entity_ids` e risponde `{entity_id: extended_dict | None}`.

        Conseguenza, finche' nessuno l'ha chiamato: la colonna `alias` delle
        entita' era vuota su ogni casa, sempre. Gli alias sono le parole con
        cui l'utente ha DICHIARATO come chiama le sue cose -- la spina dorsale
        di `search` -- e reggevano solo per le aree, che invece li mandano
        davvero nel proprio registro. Un utente che aveva scritto «lampada
        della nonna» come alias non trovava niente cercandola.

        La classe non si prende da qui: arriva gia' dallo specchio dello stato
        (`home_space.topology.live_first`), che ce l'ha per ogni entita' e non
        costa nessuna chiamata. Questo comando serve per cio' che lo specchio
        NON ha.

        Costa un comando in piu' per ricostruzione dell'anagrafe, non uno per
        entita': `entity_ids` e' una lista sola.

        Se fallisce, gli alias restano vuoti e lo si DICHIARA come qualunque
        altro silenzio -- `entita:alias` in `non_disponibili`, con i due punti
        come per `categorie:script`. La dicitura non e' `entita`: quello
        significa «il registro delle entita' non ha risposto», e farebbe
        credere alla casa di non avere entita' affatto.
        """
        entities = registries.get("entita") or []
        ids = [e.get("entity_id") for e in entities if e.get("entity_id")]
        if not ids:
            return
        # `_ws_send` non solleva: un comando senza risposta e' `None`.
        (msg,) = await self._ws_send(
            [("config/entity_registry/get_entries", {"entity_ids": ids})])
        extended_by_id = msg.get("result") if msg else None
        if not isinstance(extended_by_id, dict):
            unavailable.append("entita:alias")
            return
        for entry in entities:
            extended = extended_by_id.get(entry.get("entity_id"))
            if not isinstance(extended, dict):
                continue
            # `None` DENTRO la lista non e' un alias, e' una sentinella.
            #
            # Home Assistant dichiara `_serialize_aliases(...) -> list[str | None]`
            # e mappa `COMPUTED_NAME` su `None` (`helpers/entity_registry.py`):
            # quel `null` significa «qui va il nome calcolato», che e' un dato
            # che HIRIS ha gia' (`original_name`), non una parola che qualcuno
            # ha scritto.
            #
            # Preso alla lettera ha riempito l'archivio: 1030 entita' su 1223
            # con `alias: [null]`, e `search` e `remember` -- gli unici due che
            # costruiscono l'indice -- morivano con
            # «'NoneType' object has no attribute 'lower'» su ogni chiamata.
            #
            # E' la lezione del `carbon_monoxide` in un'altra forma: avevo
            # verificato CHE `aliases` esistesse in `extended_dict`, non COSA
            # possono contenere i suoi elementi. Il tipo lo diceva.
            alias = [a for a in (extended.get("aliases") or [])
                     if isinstance(a, str) and a.strip()]
            if alias:
                entry["aliases"] = alias

    def add_state_listener(self, callback: Callable[[dict], None]) -> None:
        """callback(dati_evento) a ogni `state_changed`: chi ascolta riceve
        `{"entity_id", "old_state", "new_state"}` cosi' come Home Assistant lo
        manda -- lo stesso rubinetto che alimenta lo specchio delle entita'.

        Due tipi di ascoltatori, e la differenza conta per chi si aggiunge:
        quelli PERMANENTI si registrano all'avvio e restano (lo specchio);
        quelli EFFIMERI vivono una sola operazione e devono togliersi con
        `remove_state_listener` (`action/actuator.py`, che aspetta l'annuncio
        delle entita' che ha appena comandato). Un effimero che non si toglie
        e' una perdita silenziosa: la lista cresce a ogni comando, e ogni
        evento della casa la percorre tutta.
        """
        self._state_listeners.append(callback)

    def remove_state_listener(self, callback: Callable[[dict], None]) -> None:
        """Toglie un ascoltatore aggiunto con `add_state_listener`.

        Togliere qualcosa che non c'e' non e' un errore: chi si smonta lo fa
        tipicamente in un `finally`, e li' l'unica cosa peggiore di un
        ascoltatore rimasto e' un'eccezione che copre quella vera.
        """
        try:
            self._state_listeners.remove(callback)
        except ValueError:
            pass

    def add_topology_listener(self, callback: Callable[[str], None]) -> None:
        """callback(tipo_evento) a ogni cambio di registro: la casa e' cambiata."""
        self._topology_listeners.append(callback)

    def add_service_listener(self, callback: Callable[[str], None]) -> None:
        """callback(tipo_evento) quando un servizio compare o sparisce, e a ogni
        riconnessione. Chi ascolta INVALIDA il registro dei servizi: non lo
        rilegge subito -- installare un'integrazione emette una raffica di
        eventi, e una lettura per ognuno sarebbe una tempesta per un dato che
        serve solo al prossimo comando."""
        self._service_listeners.append(callback)

    def add_dashboard_listener(self, callback: Callable[[dict], None]) -> None:
        """callback(dati_evento) a ogni cambio di una plancia (DASHBOARD_EVENT).
        `event_data` porta il `url_path` di quella cambiata, ma chi ascolta
        rilegge tutte le plance — vedi DASHBOARD_EVENT."""
        self._dashboard_listeners.append(callback)

    def add_automation_listener(self, callback: Callable[[dict], None]) -> None:
        """callback(dati_evento) a ogni AUTOMATION_TRIGGERED_EVENT -- vedi la
        sua costante per il perche' l'evento non porta (e non puo' portare)
        un esito. `event_data` porta almeno `entity_id` (vedi la costante);
        chi ascolta decide da solo cosa farne, questo client legge e basta."""
        self._automation_listeners.append(callback)

    def add_integration_listener(self, callback: Callable[[list], None]) -> None:
        """callback(cambi) a ogni messaggio dell'iscrizione alle integrazioni
        (`CONFIG_ENTRIES_SUBSCRIPTION`): la lista cosi' come Home Assistant la
        manda, `[{"type": None | "added" | "removed" | "updated", "entry":
        voce}]`. Un messaggio le cui voci hanno `type` nullo e' l'ELENCO
        INTERO -- arriva a ogni connessione, la prima e le seguenti -- e chi
        ascolta sostituisce cio' che sapeva: e' cosi' che una voce tolta
        mentre la connessione era giu' sparisce. Questo client legge e non
        giudica: non tiene l'elenco."""
        self._integration_listeners.append(callback)

    def reread_after_first_connection(self) -> None:
        """Anche la PRIMA connessione avvisera' gli ascoltatori come una
        riconnessione («riconnessione»: specchio, anagrafe, comportamento,
        plance e servizi si rileggono).

        Di regola la prima connessione non avvisa nessuno (D2 della Tappa 2,
        «prima l'iscrizione»): l'avvio apre il websocket, aspetta che Home
        Assistant confermi l'iscrizione (`ws_ready`) e POI legge la casa una
        volta -- una rilettura alla prima connessione sarebbe la stessa casa
        letta due volte. Ma se Home Assistant non risponde entro il tetto
        dell'attesa, l'avvio legge lo stesso (e trova il vuoto): allora e' la
        prima connessione a dover far rileggere, e l'avvio lo chiede qui.

        Se la prima connessione e' GIA' avvenuta -- l'avvio ha smesso di
        aspettare nell'istante in cui arrivava -- l'avviso parte subito invece
        di perdersi.
        """
        if self._connections:
            self._announce_reconnection()
        else:
            self._reread_at_first_connection = True

    async def start_websocket(self) -> None:
        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/websocket"
        self._ws_task = asyncio.create_task(self._ws_loop(ws_url))

    async def _ws_loop(self, ws_url: str) -> None:
        """Il websocket di lunga vita: si connette, si autentica, si iscrive,
        ascolta; se cade, riprova. Non finisce mai da solo.

        **Un gettone rifiutato non lo ferma** (S-04, 03/10/2026). Fino a quel
        giorno un `auth_invalid` faceva `return`: il ciclo usciva, e l'add-on
        restava sordo -- niente stato vivo, niente anagrafe aggiornata -- fino
        al riavvio. Adesso si riprova, con un'attesa che cresce
        (`AUTH_RETRY_FIRST_S` .. `AUTH_RETRY_CEILING_S`) e torna alla prima
        dopo un'autenticazione riuscita. Cosa manda Home Assistant, letto il
        03/10/2026 al tag 2026.9.4 (`websocket_api/auth.py`, righe 44-46 e
        125-129): `{"type": "auth_invalid", "message": ...}`, poi chiude la
        connessione. Il messaggio va nel registro, cosi' com'e'.

        **`ws_ready` dice se la connessione c'e' ADESSO**: si accende quando
        Home Assistant conferma l'iscrizione agli stati (chi legge la casa
        dopo non perde un cambio), si spegne appena la connessione cade o
        l'autenticazione e' rifiutata.
        """
        auth_wait = AUTH_RETRY_FIRST_S
        while True:
            pause = 0
            try:
                async with self._session.ws_connect(ws_url) as ws:
                    refusal = await self._authenticate(ws)
                    if refusal is None:
                        auth_wait = AUTH_RETRY_FIRST_S
                        await self._listen(ws)
                    else:
                        logger.error(
                            "HA WebSocket: autenticazione rifiutata da Home Assistant "
                            "(%s) -- riprovo fra %ds", refusal, auth_wait)
                        pause = auth_wait
                        auth_wait = min(auth_wait * 2, AUTH_RETRY_CEILING_S)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("HA WebSocket disconnected: %s — reconnecting in %ds",
                               exc, RECONNECT_DELAY_S)
                pause = RECONNECT_DELAY_S
            finally:
                self.ws_ready.clear()
            if pause:
                await asyncio.sleep(pause)

    async def _authenticate(self, ws) -> str | None:
        """`None` se Home Assistant ha accettato il gettone, altrimenti cio'
        che ha scritto nel rifiuto."""
        auth_req = await ws.receive_json()
        if auth_req.get("type") == "auth_required":
            token = self._headers["Authorization"].removeprefix("Bearer ")
            await ws.send_json({"type": "auth", "access_token": token})
            auth_resp = await ws.receive_json()
            if auth_resp.get("type") != "auth_ok":
                return str(auth_resp.get("message") or auth_resp.get("type"))
        return None

    async def _listen(self, ws) -> None:
        """Una connessione autenticata: le iscrizioni, l'avviso di
        riconnessione, poi gli eventi finche' la connessione regge."""
        msg_id = 1
        states_subscription = msg_id
        await ws.send_json(
            {"id": msg_id, "type": "subscribe_events", "event_type": "state_changed"}
        )
        msg_id += 1
        await ws.send_json(
            {"id": msg_id, "type": "subscribe_events",
             "event_type": "entity_registry_updated"}
        )
        # Gli altri registri dell'anagrafe (Task 5): entity_registry_updated
        # e' gia' sottoscritto sopra (id 2) e va verso add_anagrafe_listener,
        # che copre anche rinomini, spostamenti, disabilitazioni e cancellazioni
        # (non solo le creazioni: quel filtro apparteneva al meccanismo storico
        # verso add_registry_listener, uscito con la context map che lo chiamava
        # -- fetta E3 Task 2, 2.0).
        for event_type in (
            t for t in TOPOLOGY_EVENTS if t != "entity_registry_updated"
        ):
            msg_id += 1
            await ws.send_json(
                {"id": msg_id, "type": "subscribe_events", "event_type": event_type}
            )
        # Task 5: le plance hanno un ascoltatore proprio, separato
        # dall'anagrafe (vedi DASHBOARD_EVENT in cima al modulo).
        msg_id += 1
        await ws.send_json(
            {"id": msg_id, "type": "subscribe_events", "event_type": DASHBOARD_EVENT}
        )
        # Task 4 di «le tracce e il log»: l'evento che segna
        # l'inizio delle azioni di un'automazione scattata --
        # vedi AUTOMATION_TRIGGERED_EVENT in cima al modulo per
        # la fonte e per il perche' non porta un esito.
        msg_id += 1
        await ws.send_json(
            {"id": msg_id, "type": "subscribe_events",
             "event_type": AUTOMATION_TRIGGERED_EVENT}
        )
        for event_type in SERVICE_EVENTS:
            msg_id += 1
            await ws.send_json({"id": msg_id, "type": "subscribe_events",
                                "event_type": event_type})
        # Le integrazioni (Task 7): l'elenco intero arriva subito, poi i
        # cambi -- vedi CONFIG_ENTRIES_SUBSCRIPTION in cima al modulo.
        msg_id += 1
        entries_subscription = msg_id
        await ws.send_json({"id": msg_id, "type": CONFIG_ENTRIES_SUBSCRIPTION})

        # L'avviso «riconnessione»: gli eventi emessi mentre la connessione
        # era giu' non tornano piu', e chi tiene una copia di cio' che Home
        # Assistant sa (specchio, anagrafe, comportamento, plance, servizi)
        # deve rileggere. NON alla prima connessione (D2 della Tappa 2,
        # «prima l'iscrizione», 03/10/2026): l'avvio si iscrive, aspetta
        # `ws_ready`, e POI legge la casa una volta -- la micro-finestra fra
        # lettura e iscrizione, che la rilettura alla prima connessione
        # copriva, non c'e' piu' perche' l'ordine e' rovesciato. Se l'avvio ha
        # dovuto leggere PRIMA (Home Assistant non rispondeva), lo chiede con
        # `reread_after_first_connection`.
        self._connections += 1
        if self._connections > 1 or self._reread_at_first_connection:
            self._announce_reconnection()

        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = msg.json()
            kind = data.get("type")
            if kind == "result":
                self._subscription_confirmed(data, states_subscription,
                                             entries_subscription)
            elif kind == "event" and data.get("id") == entries_subscription:
                self._dispatch_integrations(data.get("event"))
            elif kind == "event":
                self._dispatch_bus_event(data.get("event"))

    def _subscription_confirmed(self, data: dict, states_subscription: int,
                                entries_subscription: int) -> None:
        """La conferma di un'iscrizione. Quella agli stati accende `ws_ready`;
        un rifiuto di quella alle integrazioni si dice, perche' senza di lei
        lo stato delle integrazioni resta fermo all'ultima ricostruzione e il
        giro delle condizioni non parte."""
        if data.get("id") == states_subscription:
            if data.get("success"):
                self.ws_ready.set()
            else:
                logger.error("HA WebSocket: iscrizione agli stati rifiutata: %s",
                             data.get("error"))
        elif data.get("id") == entries_subscription and not data.get("success"):
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            logger.error("HA WebSocket: %s rifiutata da Home Assistant: %s (%s)",
                         CONFIG_ENTRIES_SUBSCRIPTION, error.get("message"),
                         error.get("code"))

    def _announce_reconnection(self) -> None:
        # Stessa ragione per l'anagrafe, i servizi e le plance: un registro
        # dei servizi stantio direbbe «non esiste in questa casa» di un
        # servizio che esiste, e una disconnessione perde per sempre un
        # DASHBOARD_EVENT emesso nel frattempo. L'antirimbalzo delle riletture
        # assorbe le riconnessioni ravvicinate.
        for cb in self._service_listeners:
            try:
                cb("riconnessione")
            except Exception:
                logger.exception("servizi_listener callback raised")
        for cb in self._topology_listeners:
            try:
                cb("riconnessione")
            except Exception:
                logger.exception("anagrafe_listener callback raised")
        for cb in self._dashboard_listeners:
            try:
                cb({})
            except Exception:
                logger.exception("plance_listener callback raised")

    def _dispatch_integrations(self, changes) -> None:
        if not isinstance(changes, list):
            logger.warning("HA WebSocket: %s ha mandato un evento in forma inattesa: %r",
                           CONFIG_ENTRIES_SUBSCRIPTION, type(changes).__name__)
            return
        for cb in self._integration_listeners:
            try:
                cb(changes)
            except Exception:
                logger.exception("integration_listener callback raised")

    def _dispatch_bus_event(self, event) -> None:
        if not isinstance(event, dict):
            return
        event_type = event.get("event_type")
        if event_type == "state_changed":
            for cb in self._state_listeners:
                try:
                    cb(event["data"])
                except Exception:
                    logger.exception("state_listener callback raised")
        elif event_type == DASHBOARD_EVENT:
            # Il percorso della plancia cambiata sta in event["data"], ma non
            # lo si usa per filtrare: chi ascolta rilegge tutte le plance (vedi
            # DASHBOARD_EVENT e rileggi_plance).
            for cb in self._dashboard_listeners:
                try:
                    cb(event.get("data", {}))
                except Exception:
                    logger.exception("plance_listener callback raised")
        elif event_type == AUTOMATION_TRIGGERED_EVENT:
            # `event["data"]` porta almeno `entity_id` (vedi
            # AUTOMATION_TRIGGERED_EVENT): chi ascolta decide da solo cosa
            # farne.
            for cb in self._automation_listeners:
                try:
                    cb(event.get("data", {}))
                except Exception:
                    logger.exception("automation_listener callback raised")
        if event_type in SERVICE_EVENTS:
            for cb in self._service_listeners:
                try:
                    cb(event_type)
                except Exception:
                    logger.exception("servizi_listener callback raised")
        if event_type in TOPOLOGY_EVENTS:
            # La casa e' cambiata (create/update/move/remove, su qualsiasi
            # registro): l'anagrafe va rifatta. Nessun filtro per action ne'
            # per tipo di registro — vedi TOPOLOGY_EVENTS in cima al modulo.
            for cb in self._topology_listeners:
                try:
                    cb(event_type)
                except Exception:
                    logger.exception("anagrafe_listener callback raised")
