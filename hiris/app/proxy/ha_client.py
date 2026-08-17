import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import quote
import aiohttp

# Review finale fetta E3, Important #3: `_IDENTIFIER_RE` serviva solo a
# `call_service`, uscita qui sotto -- vedi il commento sopra `class HAClient`.

# fetta E3 Task 12 ("esce il ritratto"): `_AUTOMATION_ID_RE` e' uscita --
# serviva solo a `is_automation_id_candidate`/`get_automation_config`,
# entrambe cancellate qui insieme al resto della superficie di scrittura
# automazioni (vedi il commento piu' sotto, dove viveva `is_automation_config`).

# entity_id canonico (dominio.oggetto). Serve a rifiutare un entity_id
# ostile PRIMA di comporlo in un URL: e' una GUARDIA, e va tenuta la piu'
# STRETTA possibile.
#
# In `casa/comportamento.py` c'e' oggi la stessa espressione, ma per l'esigenza
# opposta -- riconoscere gli entity_id dentro una plancia, il piu' LARGAMENTE
# possibile. Non sono due copie da tenere allineate: allentare questa per
# seguire quella e' una falla, non una pulizia.
# DOPPIONE DICHIARATO: due esigenze contrapposte, non due copie --
#   una guardia contro l'iniezione (stretta) e un riconoscitore
#   (largo). Allinearle sarebbe una falla, non una pulizia.
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

# I registri che HIRIS replica. Prima se ne ascoltava UNO — quello delle
# entita' — e per giunta solo con action="create": rinomini, cambi d'area,
# disabilitazioni e cancellazioni passavano inosservati, e la casa che HIRIS
# credeva di conoscere si allontanava da quella vera in silenzio.
EVENTI_ANAGRAFE = (
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
# Perche' esistono: `RegistroServizi` si ricaricava SOLO a scadenza (300s), e
# per cinque minuti dopo l'installazione di un'integrazione HIRIS rifiutava i
# suoi servizi dicendo «non esiste in questa casa» -- una frase falsa detta con
# sicurezza. I nomi e i campi (`domain`, `service`) sono quelli dichiarati da
# Home Assistant su home-assistant.io/docs/configuration/events/.
EVENTI_SERVIZI = ("service_registered", "service_removed")

# L'evento delle plance (Task 5): porta il PERCORSO di quella cambiata, ma
# innesca comunque una rilettura completa (sono poche, e la replica si rifa'
# invece di rattopparsi — vedi rileggi_plance). Deliberatamente FUORI da
# EVENTI_ANAGRAFE: quello innesca la ricostruzione dei *registri*, che e'
# un'altra cosa — le plance hanno un proprio ascoltatore.
EVENTO_PLANCE = "lovelace_updated"

# Deve restare identica a `_CHIAVE_PLANCIA_PRINCIPALE` in casa/archivio.py: e'
# la chiave sotto cui la predefinita finisce nell'archivio (percorso vero
# `None` -> questa stringa li'). Duplicata invece di importata per non far
# dipendere il client HA dallo storage — stesso principio per cui EVENTO_PLANCE
# e' referenziato per commento (mai importato) dall'altro verso in archivio.py.
# leggi_plance() la usa per rifiutare una plancia vera il cui url_path collide
# con la chiave sentinella, invece di lasciarla scontrarsi in scrittura.
_CHIAVE_PLANCIA_PRINCIPALE = "__principale__"

# Cap espliciti: questi dati finiscono nel prompt di un LLM, quindi la loro
# dimensione va limitata alla fonte.
# Il logbook di una settimana puo' contenere decine di migliaia di voci.
MAX_LOGBOOK_ENTRIES = 200
# Finestra massima interrogabile dal logbook. Il cap sulle voci limita la
# risposta, non il costo della query: senza un tetto sulle ore HA scandisce
# l'intero database del recorder. 168 ore = 7 giorni, quanto basta per "cosa e'
# successo questa settimana?" e non di piu' (il recorder di default ne conserva
# 10, quindi oltre non c'e' comunque granche' da leggere).
MAX_LOGBOOK_HOURS = 168
# Finestra usata quando `hours` non e' un numero interpretabile.
DEFAULT_LOGBOOK_HOURS = 24
# Template accettato in ingresso: oltre questa soglia non e' piu' una domanda
# ma un payload.
MAX_TEMPLATE_LEN = 2000
# Risposta del template (sia il risultato sia il messaggio d'errore di HA, che
# puo' includere un traceback intero).
MAX_TEMPLATE_RESPONSE_LEN = 2000

_TRUNC_MARK = " [troncato]"

logger = logging.getLogger(__name__)


def _truncate(text: str, cap: int) -> str:
    """Tronca `text` a `cap` caratteri marcandolo, marcatore incluso nel cap.

    Il risultato non supera mai `cap`. Se `cap` e' cosi' piccolo da non poter
    ospitare il marcatore si taglia e basta: meglio perdere il marcatore che
    sforare il limite dichiarato."""
    if len(text) <= cap:
        return text
    if cap <= len(_TRUNC_MARK):
        return text[:max(0, cap)]
    return text[:cap - len(_TRUNC_MARK)] + _TRUNC_MARK


# fetta E3 Task 12 ("esce il ritratto", il task della coerenza): il Task 10
# aveva lasciato QUESTO gruppo di metodi di scrittura HA orfano DI PROPOSITO
# (create_automation/is_automation_config, create_script, create_scene,
# create_dashboard, get_lovelace_config, save_dashboard_config -- persero il
# loro ultimo chiamante di produzione, handlers_proposals.py/
# proposta_config.py, quando le proposte uscirono per intero), promettendo
# che sarebbero tornati "quando saranno rifatte col perimetro e la verifica
# umana (progetto agenti)". Questo task raccoglie quella promessa: escono qui,
# insieme alle loro suite dedicate (test_ha_client_automation_config.py,
# test_ha_client_config.py, test_dashboard_client.py, test_proposal_config_
# shape.py) e a cio' che li serviva SOLO loro -- is_automation_entity_id/
# is_automation_id_candidate (usate solo da create_automation),
# resolve_automation_id_by_alias/resolve_automation_id_by_entity_id (usate
# solo da create_automation), _is_slug/_post_config (usate solo da
# create_script/create_scene), _ws_error (usato solo da create_dashboard/
# get_lovelace_config/save_dashboard_config) e get_automation_config (che non
# aveva NESSUN chiamante nemmeno prima -- ne' create_automation lo invocava
# mai, solo lo nominava nei propri messaggi d'errore). Tornera' tutto insieme
# quando il progetto agenti lo richiedera' davvero: prima non c'era motivo di
# tenerlo in piedi senza un chiamante che lo eserciti.

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
# difetti di `fields` in `azione/registro.py`. L'argomento non e' stato
# ignorato: e' stato applicato. Questa e' la forma non misurata **trattata
# come tale**, cioe' esattamente come `registro.py` tratta `fields`:
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
# non cambia; cio' che e' cambiato e' chi ci si appoggia: `azione/porta.py`
# non fonda piu' l'esito su questo ritorno da solo, e aspetta l'annuncio degli
# eventi con una scadenza.
_forma_cambiati_dichiarata = False


def _cambiati_da(risposta) -> list[dict]:
    """Gli stati che HA dichiara cambiati, da qualunque delle forme note.

    Restituisce sempre una lista di dizionari che hanno un `entity_id`: cio'
    che non ha quella chiave non e' uno stato e non serve a nessuno dei suoi
    lettori. Non solleva mai.
    """
    global _forma_cambiati_dichiarata

    grezzi = risposta
    if isinstance(risposta, dict):
        # forma `?return_response` (HA >= 2023.7)
        grezzi = risposta.get("changed_states")
    if not isinstance(grezzi, list):
        grezzi = []

    stati = [v for v in grezzi if isinstance(v, dict) and v.get("entity_id")]

    if not _forma_cambiati_dichiarata:
        _forma_cambiati_dichiarata = True
        # `sorted(...)` di una sola voce: basta a riconoscere la forma, e non
        # versa nel log gli attributi di mezza casa.
        prima_voce = sorted(stati[0].keys()) if stati else None
        logger.info(
            "call_service: la risposta di Home Assistant e' %s, %s voci "
            "utilizzabili, chiavi della prima: %s -- prima misura di questa "
            "forma su questo impianto",
            type(risposta).__name__,
            len(stati),
            prima_voce)
    return stati


def _identificatori(grezzo) -> list[str]:
    """Un insieme di identificatori di Home Assistant, letto come una lista.

    Dall'altra parte del websocket quei campi sono `set` di Python
    (`SelectedEntities` in homeassistant/helpers/target.py) e arrivano qui
    serializzati come liste, in ordine ARBITRARIO: si ordinano, o la stessa
    domanda fatta due volte darebbe due anteprime diverse senza che in casa
    sia cambiato niente. Cio' che non e' una stringa si salta: non e' un
    identificatore, e indovinare cosa sia costerebbe piu' di ignorarlo.
    """
    if not isinstance(grezzo, list):
        return []
    return sorted(v for v in grezzo if isinstance(v, str) and v)


class HAClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._state_listeners: list[Callable[[dict], None]] = []
        self._anagrafe_listeners: list[Callable[[str], None]] = []
        self._plance_listeners: list[Callable[[dict], None]] = []
        self._servizi_listeners: list[Callable[[str], None]] = []

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(headers=self._headers)

    async def stop(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
        if self._session:
            await self._session.close()

    async def get_states(self, entity_ids: list[str]) -> list[dict]:
        url = f"{self._base_url}/api/states"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            all_states: list[dict] = await resp.json()
        if entity_ids:
            return [s for s in all_states if s["entity_id"] in entity_ids]
        return all_states

    async def get_services(self) -> list[dict]:
        """Il registro dei servizi di QUESTA installazione.

        E' la fonte del «meccanismo» (spec dell'azione, §1): cosa e'
        tecnicamente possibile qui dentro, dichiarato da Home Assistant e non
        indovinato da noi. Include le integrazioni installate dall'utente, che
        nessun catalogo scritto a mano potrebbe conoscere.

        Legge e basta: nessuna scrittura verso HA vive in questo metodo.
        """
        url = f"{self._base_url}/api/services"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()

    # fetta E3 Task 8 ("escono i trentaquattro"): `get_history` e' uscito --
    # ORFANO DICHIARATO, i suoi call site (history_tools.py, calendar_tools.py)
    # erano gia' caduti col ToolDispatcher. Raccolto qui (fetta E3 Task 12):
    # verificato di nuovo, zero chiamanti in tutto il repo.

    async def call_service(self, dominio: str, servizio: str, dati: dict) -> list[dict]:
        """Chiama un servizio di Home Assistant. La primitiva che ATTUA.

        Era uscita con la fetta E3 -- «in un HIRIS che conosce e non agisce la
        primitiva che agisce non deve esistere» -- e torna adesso con la fetta
        «comandare» dell'azione. Il commento che ne raccontava la rimozione e'
        stato tolto: descriveva un fatto che non e' piu' vero.

        **Non chiamarla direttamente.** L'unico chiamante di produzione e'
        `azione/porta.py`, che verifica prima e legge il suo ritorno. Questa
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
        scadenza (`azione/porta.py`). Lo specchio interno (`EntityCache`) e'
        alimentato dagli stessi eventi, quindi rileggerlo nella riga dopo
        questa `await` legge quasi sempre lo stato di PRIMA: non e' una fonte
        del «dopo», e' l'ultimo valore noto.

        Vuota significa «HA non ha riportato cambiamenti in questa risposta»,
        mai «il dispositivo e' guasto» e nemmeno «non e' cambiato niente».
        """
        url = f"{self._base_url}/api/services/{dominio}/{servizio}"
        async with self._session.post(url, json=dati) as resp:
            resp.raise_for_status()
            risposta = await resp.json()
        return _cambiati_da(risposta)

    # I cinque campi con cui Home Assistant accetta un bersaglio: sono le
    # chiavi di `cv.TARGET_FIELDS` (homeassistant/helpers/config_validation.py),
    # verificate alla fonte. Qui ci sono i VALORI delle costanti, non i loro
    # nomi -- `ATTR_AREA_ID` vale "area_id", `ATTR_LABEL_ID` vale "label_id" --
    # perche' in questo progetto la differenza fra il nome di una costante di
    # Home Assistant e il suo valore e' gia' costata cara (`CO` vale
    # "carbon_monoxide", non "co").
    CAMPI_BERSAGLIO = ("entity_id", "device_id", "area_id", "floor_id", "label_id")

    async def estrai_dal_bersaglio(self, bersaglio: dict) -> dict:
        """Cosa contiene un bersaglio -- e a dirlo e' HOME ASSISTANT, non HIRIS.

        E' il comando `extract_from_target` (websocket_api/commands.py):
        gli si passa un bersaglio nella forma di `cv.TARGET_FIELDS` (aree,
        piani, etichette, dispositivi, entita') e risponde con le entita' che
        quel bersaglio tocca davvero.

        **Perche' non lo deduce l'anagrafe.** L'albero di `gerarchia()` e' una
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
        if not isinstance(bersaglio, dict):
            return {"errore": "il bersaglio non e' un oggetto"}
        pulito = {}
        for campo in self.CAMPI_BERSAGLIO:
            voci = bersaglio.get(campo)
            if isinstance(voci, str):
                voci = [voci]
            if not isinstance(voci, list):
                continue
            voci = [v for v in voci if isinstance(v, str) and v.strip()]
            if voci:
                pulito[campo] = voci
        if not pulito:
            return {"errore": "il bersaglio non nomina niente che Home Assistant "
                              "sappia risolvere"}

        msg = await self._ws_command("extract_from_target",
                                     {"target": pulito,
                                      "expand_group": True,
                                      "primary_entities_only": True})
        # Tre modi di non aver saputo, tre frasi diverse: la connessione non
        # c'e' stata, Home Assistant ha detto di no (e allora si riporta cosa
        # ha detto: un `unknown_command` su una versione vecchia si legge
        # qui), la risposta non era leggibile. Un solo «non lo so» li avrebbe
        # confusi, e sono guasti con rimedi diversi.
        if not msg:
            return {"errore": "Home Assistant non ha risposto"}
        if not msg.get("success"):
            guasto = msg.get("error")
            guasto = guasto if isinstance(guasto, dict) else {}
            return {"errore": f"Home Assistant ha rifiutato «extract_from_target» "
                              f"({guasto.get('code') or 'senza codice'}: "
                              f"{guasto.get('message') or 'senza messaggio'})"}
        risultato = msg.get("result")
        if not isinstance(risultato, dict):
            return {"errore": "la risposta di «extract_from_target» non e' un oggetto"}

        # I dispositivi che non esistono arrivano ANCHE in
        # `referenced_devices`: `_resolve_referenced_devices`
        # (homeassistant/helpers/target.py) li aggiunge a entrambi gli
        # insiemi. Tenerli qui vorrebbe dire dire «questo dispositivo si
        # tocca» di un dispositivo che non c'e'; toglierli non nasconde
        # niente, perche' restano interi in `dispositivi_mancanti`.
        mancanti = _identificatori(risultato.get("missing_devices"))
        return {
            "entita": _identificatori(risultato.get("referenced_entities")),
            "dispositivi": [d for d in _identificatori(risultato.get("referenced_devices"))
                            if d not in set(mancanti)],
            "aree": _identificatori(risultato.get("referenced_areas")),
            "dispositivi_mancanti": mancanti,
            "aree_mancanti": _identificatori(risultato.get("missing_areas")),
            "piani_mancanti": _identificatori(risultato.get("missing_floors")),
            "etichette_mancanti": _identificatori(risultato.get("missing_labels")),
        }

    # fetta E3 Task 12: `get_automations`/`create_automation`/
    # `resolve_automation_id_by_alias`/`resolve_automation_id_by_entity_id`/
    # `_is_slug`/`_post_config`/`create_script`/`create_scene`/`_ws_error`/
    # `create_dashboard`/`get_lovelace_config` sono usciti insieme (vedi il
    # commento sopra `class HAClient`): erano la superficie di scrittura HA
    # delle proposte, orfana di proposito dal Task 10. `get_automations`
    # (che HA nomina "automazioni", non lette da nessun altro tool "conosce")
    # non aveva altro chiamante che i due `resolve_*` qui sopra.

    # Review finale fetta E2, I-2: `list_dashboards` e' uscito -- orfano dal
    # Task 7 (il suo ultimo chiamante di produzione, `tools/dispatcher.py`,
    # e' stato cancellato). `leggi_plance()` sotto usa lo stesso comando WS
    # (`lovelace/dashboards/list`) per il percorso ancora vivo.

    async def leggi_plance(self) -> tuple[list[dict], list[str]]:
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
        ragione leggibile) invece di far fallire `sostituisci_plance` con
        `UNIQUE constraint failed` — che altrimenti ferma silenziosamente
        l'aggiornamento della replica delle plance.

        Se l'elenco stesso non arriva (timeout, disconnessione), lo si
        dichiara come `"elenco: ..."` in `non_disponibili` — invece di
        confonderlo con «l'elenco e' arrivato ed e' vuoto», che e' un fatto
        diverso sulla casa (nessuna plancia aggiuntiva, non «non lo so»). Per
        questo si usa `_ws_command` (il messaggio intero, con `success`) e
        non `_ws_request`: quest'ultimo restituisce `None` sia se il comando
        e' fallito sia se e' riuscito con `result: None`, le due cose non si
        distinguerebbero.
        """
        got = await self._ws_command("lovelace/dashboards/list", {})
        elenco_arrivato = bool(got and got.get("success"))
        elenco = got.get("result") if elenco_arrivato else None
        elenco = elenco if isinstance(elenco, list) else []

        non_disponibili: list[str] = []
        if not elenco_arrivato:
            non_disponibili.append(
                "elenco: lovelace/dashboards/list non ha risposto — le plance "
                "aggiuntive potrebbero non essere tutte qui"
            )

        # `None` = la predefinita, sempre in testa. Un percorso vero deve
        # essere sia UNICO (la tabella `plance` lo usa come chiave primaria:
        # due voci con lo stesso percorso mandano `sostituisci_plance` in
        # `UNIQUE constraint failed`, e l'aggiornamento della replica smette
        # silenziosamente) sia DIVERSO dalla chiave sentinella della
        # predefinita (altrimenti le due collidono nello stesso modo quando
        # l'archivio traduce `None` in quella chiave per lo storage). Niente
        # `INSERT OR REPLACE`: un percorso scartato va dichiarato in
        # `non_disponibili`, non nascosto sovrascrivendo in silenzio.
        # `is not None` (non verita' booleana): un url_path vuoto ("") e'
        # falsy ma e' un percorso legittimo, non un'assenza.
        # `non_disponibili` non si ridichiara qui: gia' inizializzata sopra,
        # puo' gia' portare la dichiarazione "elenco" se l'elenco non e'
        # arrivato — ridichiararla la cancellerebbe.
        percorsi: list[str | None] = [None]
        visti: set[str] = set()
        for d in elenco:
            p = d.get("url_path")
            if p is None:
                continue
            if p == _CHIAVE_PLANCIA_PRINCIPALE:
                non_disponibili.append(
                    f"{p} (collide con la chiave della plancia predefinita, ignorata)")
                continue
            if p in visti:
                non_disponibili.append(f"{p} (duplicata nell'elenco, ignorata)")
                continue
            visti.add(p)
            percorsi.append(p)

        comandi = [("lovelace/config", {} if p is None else {"url_path": p})
                   for p in percorsi]
        risposte = await self._ws_batch(comandi)

        # setdefault, non un comprehension che sovrascrive: un percorso
        # duplicato deve accoppiarsi al PRIMO dizionario visto (coerente con
        # `visti` sopra), non all'ultimo — altrimenti la voce tenuta e quella
        # dichiarata scartata si scambierebbero i dati.
        per_percorso: dict[str | None, dict] = {}
        for d in elenco:
            if isinstance(d, dict):
                per_percorso.setdefault(d.get("url_path"), d)
        plance: list[dict] = []
        for percorso, msg in zip(percorsi, risposte):
            config = msg.get("result") if msg else None
            if not isinstance(config, dict):
                config = None
                non_disponibili.append(percorso or "principale")
            voce = dict(per_percorso.get(percorso) or {})
            voce.setdefault("url_path", percorso)
            voce.setdefault("title", "Principale" if percorso is None else percorso)
            voce["config"] = config
            plance.append(voce)
        return plance, non_disponibili

    # fetta E3 Task 12: `save_dashboard_config` esce con `create_dashboard`
    # (stessa superficie di scrittura, vedi il commento sopra `class
    # HAClient`). `get_automation_config` esce con lei: non aveva NESSUN
    # chiamante nemmeno prima di questo task -- ne' `create_automation` lo
    # invocava mai (lo nominava solo nei propri messaggi d'errore, come
    # suggerimento per l'LLM), ne' alcun altro modulo vivo.

    async def get_error_log(self, limit: int = 100) -> dict:
        """Fetch HA error log and return parsed summary."""
        _empty = {"errors": 0, "warnings": 0, "top_errors": []}
        url = f"{self._base_url}/api/error_log"
        try:
            async with self._session.get(url) as resp:
                if resp.status in (403, 404):
                    logger.debug("get_error_log: endpoint returned %s — skipping", resp.status)
                    return _empty
                resp.raise_for_status()
                text = await resp.text()
        except Exception as exc:
            logger.debug("get_error_log: unavailable (%s)", exc)
            return _empty
        lines = text.strip().splitlines()
        errors, warnings, top_errors = 0, 0, []
        for line in lines[-limit:]:
            if " ERROR " in line:
                errors += 1
                if len(top_errors) < 5:
                    top_errors.append(line[20:120] if len(line) > 20 else line)
            elif " WARNING " in line:
                warnings += 1
        return {"errors": errors, "warnings": warnings, "top_errors": top_errors}

    @staticmethod
    def _health_value(value: Any) -> Any:
        """Appiattisce un valore di system_health in uno scalare presentabile.

        HA restituisce sia scalari sia valori "tipizzati" come
        {"type": "date", "value": ...}, {"type": "pending"} oppure
        {"type": "failed", "error": "..."}. Il formato non e' documentato: si
        riconosce quello che si capisce e si scarta il resto (None = ignora)."""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            if value.get("error"):
                return _truncate(str(value["error"]), 200)
            if "value" in value:
                inner = value["value"]
                if isinstance(inner, (str, int, float, bool)) or inner is None:
                    return inner
                return None
            if value.get("type"):
                return str(value["type"])
        return None

    async def get_system_health(self) -> dict:
        """Salute nativa delle integrazioni via WS `system_health/info`.

        Ritorna una mappa dominio -> {chiave: valore} con le sole informazioni
        riconosciute; {} se il dato non e' disponibile. Sola lettura, non
        solleva mai: ogni fallimento vale come "dato non disponibile"."""
        try:
            result = await self._ws_request("system_health/info")
        except Exception as exc:
            logger.debug("get_system_health: WS non disponibile (%s)", exc)
            return {}
        if not isinstance(result, dict):
            return {}
        health: dict = {}
        for domain, payload in result.items():
            if not isinstance(payload, dict):
                continue
            # HA annida le informazioni sotto "info", ma non e' garantito:
            # se manca si legge il payload stesso.
            info = payload.get("info")
            if not isinstance(info, dict):
                info = payload
            entries = {}
            for key, raw in info.items():
                value = self._health_value(raw)
                if value is not None or raw is None:
                    entries[str(key)] = value
            if entries:
                health[str(domain)] = entries
        return health

    async def get_logbook(self, entity_id: str | None, hours: int) -> list[dict]:
        """Cronologia eventi via GET /api/logbook/<ISO start>.

        `entity_id` filtra su una singola entita' (None = tutta la casa),
        `hours` e' la finestra all'indietro da adesso, normalizzata fra 1 e
        MAX_LOGBOOK_HOURS (valori non numerici valgono DEFAULT_LOGBOOK_HOURS).
        Ritorna al piu' MAX_LOGBOOK_ENTRIES voci {when, name, message,
        entity_id}, tenendo le piu' recenti; [] se il dato non e' disponibile.
        Non solleva mai: ogni fallimento vale come "dato non disponibile".

        TRONCAMENTO — una lista lunga esattamente MAX_LOGBOOK_ENTRIES voci
        significa quasi certamente che le voci PIU' VECCHIE della finestra sono
        state scartate. Il tipo di ritorno non ospita un flag, quindi il
        chiamante che confeziona la risposta per l'utente DEVE controllare
        `len(voci) == MAX_LOGBOOK_ENTRIES` e dichiarare il troncamento:
        altrimenti l'LLM conclude che "non e' successo altro". Vale lo stesso
        per la finestra: se `hours` e' stato clampato a MAX_LOGBOOK_HOURS il
        periodo coperto e' piu' corto di quello richiesto."""
        if entity_id is not None and not _ENTITY_ID_RE.match(str(entity_id)):
            logger.warning("get_logbook: entity_id non valido: %r", entity_id)
            return []
        # `hours` arriva direttamente da una tool-call dell'LLM: puo' essere
        # None, una stringa, NaN o un numero fuori scala. Si normalizza in
        # spazio float e si clampa PRIMA di costruire il timedelta, perche'
        # int(inf), int(10**12) come ore e timedelta(hours=18_000_000)
        # sollevano OverflowError, che non deve mai raggiungere il chiamante.
        try:
            numeric = float(hours)
        except Exception:
            numeric = float(DEFAULT_LOGBOOK_HOURS)
        if numeric != numeric:  # NaN: non confrontabile, vale come assente
            numeric = float(DEFAULT_LOGBOOK_HOURS)
        window = int(min(float(MAX_LOGBOOK_HOURS), max(1.0, numeric)))
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=window)).isoformat()
        # start sta nel path (come /api/history/period); end_time ed entity
        # stanno nella query, dove il "+" del fuso orario va percent-encoded
        # o verrebbe letto come spazio.
        url = (f"{self._base_url}/api/logbook/{start}"
               f"?end_time={quote(now.isoformat(), safe='')}")
        if entity_id is not None:
            url += f"&entity={quote(entity_id, safe='')}"
        try:
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    logger.debug("get_logbook: HTTP %s — nessun dato", resp.status)
                    return []
                data = await resp.json()
        except Exception as exc:
            logger.debug("get_logbook: non disponibile (%s)", exc)
            return []
        if not isinstance(data, list):
            return []
        entries = []
        for item in data:
            if not isinstance(item, dict):
                continue
            entries.append({
                "when": item.get("when"),
                "name": item.get("name"),
                "message": item.get("message"),
                "entity_id": item.get("entity_id"),
            })
        # Cap DOPO il filtro: troncare prima farebbe restituire meno voci del
        # massimo pur essendocene di valide piu' vecchie.
        return entries[-MAX_LOGBOOK_ENTRIES:]

    async def render_template(self, template: str) -> dict:
        """Valuta un template Jinja di HA via POST /api/template.

        E' una POST ma resta una LETTURA: HA renderizza e basta, nessun effetto
        collaterale. Ritorna {"result": "<testo>"} oppure {"error": "..."}.
        L'endpoint risponde testo semplice, non JSON. In caso di template
        sbagliato HA restituisce il proprio messaggio d'errore (utile all'LLM
        per correggersi): lo si inoltra ma troncato, perche' puo' contenere un
        traceback intero."""
        if not isinstance(template, str) or not template.strip():
            return {"error": "template vuoto o non valido"}
        if len(template) > MAX_TEMPLATE_LEN:
            return {"error": f"template troppo lungo (max {MAX_TEMPLATE_LEN} caratteri)"}
        url = f"{self._base_url}/api/template"
        try:
            async with self._session.post(url, json={"template": template}) as resp:
                body = await resp.text()
                if resp.status != 200:
                    message = body.strip() or f"HA ha risposto {resp.status}"
                    return {"error": _truncate(message, MAX_TEMPLATE_RESPONSE_LEN)}
                return {"result": _truncate(body, MAX_TEMPLATE_RESPONSE_LEN)}
        except Exception as exc:
            # Mai fare eco di str(exc) al chiamante: resta nel log.
            logger.debug("render_template: valutazione fallita (%s)", exc)
            return {"error": "valutazione del template non riuscita"}

    # fetta E3 Task 11 -> Task 12: `get_config_entries`/`get_system_info`/
    # `get_updates` sono usciti. Erano gia' ORFANI DICHIARATI dal Task 11
    # (l'HealthMonitor/SupervisorClient che li leggeva e' uscito per intero):
    # verificato di nuovo qui, zero chiamanti in tutto il repo.
    # `leggi_registri` (sopra) non li richiama: chiede il comando delle
    # integrazioni direttamente nel suo batch WS, non passando da
    # `get_config_entries`. Il nome del comando era sbagliato fino al Task
    # B6 ("config/config_entries/get_entries", che non esiste in HA): vedi
    # `_REGISTRI` per quello vero, "config_entries/get".

    # fetta E2 Task 8 ("escono i trentaquattro"): `get_calendars`/
    # `get_calendar_events_range` sono uscite -- orfane a cascata dalla
    # stessa fetta: il loro unico chiamante era `tools/calendar_tools.
    # get_calendar_events`, uscito lui stesso perche' orfano dal Task 7 (il
    # `ToolDispatcher` che lo chiamava e' uscito). Nessun test le copriva
    # come API del client (a differenza di `get_statistics`, che ha una sua
    # suite dedicata, tests/test_ha_client_statistics.py, e resta): nessuna
    # garanzia persa.

    async def _ws_batch(self, comandi: list[tuple[str, dict | None]],
                        timeout: float = 10.0) -> list[dict | None]:
        """N comandi WebSocket su UNA connessione → N messaggi interi, in ordine.

        Prima ogni lettura WS apriva una sessione e una connessione nuove, con
        handshake e autenticazione completi, e le chiudeva: sei registri
        costavano sei handshake in serie. Qui il costo si paga una volta.

        Ogni elemento e' il messaggio INTERO ({success, result, error}), oppure
        `None` per i comandi rimasti senza risposta o se la connessione e'
        fallita del tutto: chi chiama decide se un guasto e' tollerabile.
        """
        risposte: list[dict | None] = [None] * len(comandi)
        if not comandi:
            return risposte
        ws_url = (
            self._base_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/websocket"
        )
        token = self._headers["Authorization"].removeprefix("Bearer ")
        tipi = [t for t, _ in comandi]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    handshake = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                    if handshake.get("type") == "auth_required":
                        await ws.send_json({"type": "auth", "access_token": token})
                        auth = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        if auth.get("type") != "auth_ok":
                            logger.warning("HA WS auth failed in _ws_batch(%s)", tipi)
                            return risposte
                    for numero, (msg_type, extra) in enumerate(comandi, start=1):
                        payload = {"id": numero, "type": msg_type}
                        if extra:
                            payload.update(extra)
                        await ws.send_json(payload)
                    attesi = set(range(1, len(comandi) + 1))
                    while attesi:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        numero = msg.get("id")
                        if numero in attesi:
                            risposte[numero - 1] = msg
                            attesi.discard(numero)
        except Exception as exc:
            logger.debug("_ws_batch(%s) failed: %s", tipi, exc)
        return risposte

    async def _ws_request(self, msg_type: str, extra: dict | None = None,
                          timeout: float = 10.0) -> Any:
        """Un comando WS → il solo `result` (dict o list, secondo il comando)."""
        msg = (await self._ws_batch([(msg_type, extra)], timeout=timeout))[0]
        return msg.get("result") if msg else None

    async def _ws_command(self, msg_type: str, extra: dict | None = None,
                          timeout: float = 10.0) -> dict | None:
        """Un comando WS → il messaggio intero ({success, result, error}), cosi'
        le scritture possono verificare l'esito. `None` solo se la connessione
        o l'autenticazione sono fallite."""
        return (await self._ws_batch([(msg_type, extra)], timeout=timeout))[0]

    async def _ws_call(self, msg_type: str, timeout: float = 10.0) -> list[dict]:
        """Back-compat wrapper: WS command whose result is a list (registry, etc.)."""
        result = await self._ws_request(msg_type, timeout=timeout)
        return result if isinstance(result, list) else []

    async def get_statistics(self, statistic_ids: list[str], period: str,
                             days: int) -> dict:
        """HA Long-Term Statistics for measurement sensors over the last N days.

        period: "5minute" | "hour" | "day" | "week" | "month".
        Returns {statistic_id: [{start, mean, min, max, sum?}, ...]} ({} on failure).
        end_time is omitted -> HA defaults it to now.
        """
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = await self._ws_request(
            "recorder/statistics_during_period",
            extra={"start_time": start,
                   "statistic_ids": list(statistic_ids),
                   "period": period},
        )
        return result if isinstance(result, dict) else {}

    async def get_config(self) -> dict:
        """Il sistema di riferimento della casa, da `get_config` di HA.

        Restituisce il dizionario grezzo di Home Assistant ({} se la risposta
        non e' un dizionario). A distillarlo e' `anagrafe.riferimento_dalla_config`:
        qui si LEGGE soltanto, cosi' il client non ha un'opinione su cosa
        della casa valga la pena tenere.

        NON e' un registro e non passa da `leggi_registri`: quello lavora su
        liste di righe (`isinstance(risultato, list)`), questo torna un
        dizionario. Infilarcelo avrebbe voluto dire allargare la forma di
        `leggi_registri` per un solo caso speciale -- CONSISTENZA: una
        funzione che restituisce registri restituisce registri.

        Il comando esiste in `websocket_api/commands.py` (`handle_get_config`)
        e la forma della risposta e' `Config.as_dict()` in `core_config.py`.
        """
        risultato = await self._ws_request("get_config")
        return risultato if isinstance(risultato, dict) else {}

    # `get_area_registry` e `get_entity_registry` SONO usciti (review dei
    # doppioni, 17/08). Emettevano gli stessi identici comandi WS che
    # `leggi_registri` manda gia' in batch: una seconda porta per un fatto che
    # ne ha gia' una, viva solo nei test -- e i test che le esercitavano davano
    # l'impressione che la lettura dei registri fosse coperta da due lati,
    # mentre il percorso vero (`_ws_batch` piu' la gestione di
    # `non_disponibili`) ha una sola implementazione. Chi avesse aggiunto una
    # normalizzazione in `leggi_registri` non l'avrebbe vista applicata dalle
    # prove che passavano di qui.

    # Gli ambiti delle categorie di Home Assistant. Sono partizionate per
    # ambito: chiederne uno solo farebbe sparire la tassonomia che l'utente ha
    # scritto sugli script o sugli helper, contro il principio per cui il
    # significato e' dichiarato e non dedotto. Costano quattro comandi sulla
    # stessa connessione: praticamente nulla.
    _AMBITI_CATEGORIA = ("automation", "script", "scene", "helpers")

    # I registri che l'utente ha gia' compilato in Home Assistant. Sono la
    # spina dorsale del significato per HIRIS: piani, aree, dispositivi,
    # etichette e categorie sono la tassonomia che ha scelto lui — non serve
    # dedurla, e dedurla costerebbe token e sbaglierebbe in silenzio.
    # Le voci "categorie" sono una per ambito (vedi _AMBITI_CATEGORIA) e
    # condividono tutte la chiave "categorie": leggi_registri le fonde in
    # un'unica lista, marcando ogni riga con il proprio ambito.
    _REGISTRI: list[tuple[str, str, dict | None]] = [
        ("piani",        "config/floor_registry/list",        None),
        ("aree",         "config/area_registry/list",         None),
        ("dispositivi",  "config/device_registry/list",       None),
        ("entita",       "config/entity_registry/list",       None),
        ("etichette",    "config/label_registry/list",        None),
        ("integrazioni", "config_entries/get",               None),
    ] + [
        ("categorie", "config/category_registry/list", {"scope": ambito})
        for ambito in _AMBITI_CATEGORIA
    ]

    async def leggi_registri(self) -> tuple[dict[str, list[dict]], list[str]]:
        """Tutti i registri della casa, su una connessione sola.

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
        comandi = [(tipo, extra) for _, tipo, extra in self._REGISTRI]
        risposte = await self._ws_batch(comandi)
        registri: dict[str, list[dict]] = {}
        non_disponibili: list[str] = []
        for (chiave, tipo, extra), msg in zip(self._REGISTRI, risposte):
            risultato = msg.get("result") if msg else None
            if not isinstance(risultato, list):
                ambito = extra.get("scope") if extra else None
                nome = f"{chiave}:{ambito}" if chiave == "categorie" and ambito else chiave
                # Tre guasti diversi, tre diciture: `msg` porta il messaggio
                # WS intero ({success, result, error} -- vedi il docstring di
                # `_ws_batch`), e prima d'ora si guardava solo `result`,
                # buttando via il motivo che HA aveva gia' scritto in `error`.
                errore = msg.get("error") if msg else None
                if errore:
                    # HA e' arrivato e ha rifiutato il comando: il motivo e'
                    # suo, non il nome del comando che gia' sapevamo.
                    motivo = errore.get("message") or errore.get("code") or errore
                    logger.debug("registro %s rifiutato da Home Assistant: %s (%s)",
                                 nome, motivo, tipo)
                elif msg is not None:
                    # HA e' arrivato, non ha rifiutato nulla, ma `result` non
                    # e' la lista attesa: guasto diverso dal rifiuto.
                    logger.debug("registro %s risposta in forma inattesa (%s): %r",
                                 nome, tipo, risultato)
                else:
                    # Il comando non ha mai avuto risposta -- la connessione
                    # non si e' aperta o la risposta non e' arrivata: nessun
                    # `error` da mostrare perche' HA non ha mai parlato.
                    logger.debug("registro %s non disponibile: nessuna risposta dal comando (%s)",
                                 nome, tipo)
                non_disponibili.append(nome)
                risultato = []
            if chiave == "categorie" and extra:
                ambito = extra.get("scope")
                risultato = [{**riga, "ambito": ambito} for riga in risultato]
            registri.setdefault(chiave, []).extend(risultato)

        await self._aggiungi_campi_estesi(registri, non_disponibili)
        return registri, non_disponibili

    async def _aggiungi_campi_estesi(self, registri: dict[str, list[dict]],
                                     non_disponibili: list[str]) -> None:
        """Gli ALIAS delle entita', che `config/entity_registry/list` non manda.

        Quel comando risponde con `RegistryEntry.as_partial_dict`
        (`helpers/entity_registry.py`), che NON contiene `aliases` -- ne'
        `device_class`, ne' `capabilities`. Stanno solo in `extended_dict`,
        servito da `config/entity_registry/get_entries`, che vuole l'elenco
        degli `entity_ids` e risponde `{entity_id: extended_dict | None}`.

        Conseguenza, finche' nessuno l'ha chiamato: la colonna `alias` delle
        entita' era vuota su ogni casa, sempre. Gli alias sono le parole con
        cui l'utente ha DICHIARATO come chiama le sue cose -- la spina dorsale
        di `cerca` -- e reggevano solo per le aree, che invece li mandano
        davvero nel proprio registro. Un utente che aveva scritto «lampada
        della nonna» come alias non trovava niente cercandola.

        La classe non si prende da qui: arriva gia' dallo specchio dello stato
        (`casa.anagrafe.classe_effettiva`), che ce l'ha per ogni entita' e non
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
        entita = registri.get("entita") or []
        ids = [e.get("entity_id") for e in entita if e.get("entity_id")]
        if not ids:
            return
        try:
            estese = await self._ws_request(
                "config/entity_registry/get_entries", extra={"entity_ids": ids})
        except Exception as e:
            logger.debug("campi estesi delle entita' non letti: %s", e)
            estese = None
        if not isinstance(estese, dict):
            non_disponibili.append("entita:alias")
            return
        for voce in entita:
            estesa = estese.get(voce.get("entity_id"))
            if isinstance(estesa, dict) and estesa.get("aliases"):
                voce["aliases"] = estesa["aliases"]

    def add_state_listener(self, callback: Callable[[dict], None]) -> None:
        """callback(dati_evento) a ogni `state_changed`: chi ascolta riceve
        `{"entity_id", "old_state", "new_state"}` cosi' come Home Assistant lo
        manda -- lo stesso rubinetto che alimenta lo specchio delle entita'.

        Due tipi di ascoltatori, e la differenza conta per chi si aggiunge:
        quelli PERMANENTI si registrano all'avvio e restano (lo specchio);
        quelli EFFIMERI vivono una sola operazione e devono togliersi con
        `remove_state_listener` (`azione/porta.py`, che aspetta l'annuncio
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

    def add_anagrafe_listener(self, callback: Callable[[str], None]) -> None:
        """callback(tipo_evento) a ogni cambio di registro: la casa e' cambiata."""
        self._anagrafe_listeners.append(callback)

    def add_servizi_listener(self, callback: Callable[[str], None]) -> None:
        """callback(tipo_evento) quando un servizio compare o sparisce, e a ogni
        riconnessione. Chi ascolta INVALIDA il registro dei servizi: non lo
        rilegge subito -- installare un'integrazione emette una raffica di
        eventi, e una lettura per ognuno sarebbe una tempesta per un dato che
        serve solo al prossimo comando."""
        self._servizi_listeners.append(callback)

    def add_plance_listener(self, callback: Callable[[dict], None]) -> None:
        """callback(dati_evento) a ogni cambio di una plancia (EVENTO_PLANCE).
        `dati_evento` porta il `url_path` di quella cambiata, ma chi ascolta
        rilegge tutte le plance — vedi EVENTO_PLANCE."""
        self._plance_listeners.append(callback)

    async def start_websocket(self) -> None:
        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/websocket"
        self._ws_task = asyncio.create_task(self._ws_loop(ws_url))

    async def _ws_loop(self, ws_url: str) -> None:
        while True:
            try:
                async with self._session.ws_connect(ws_url) as ws:
                    auth_req = await ws.receive_json()
                    if auth_req.get("type") == "auth_required":
                        token = self._headers["Authorization"].removeprefix("Bearer ")
                        await ws.send_json({"type": "auth", "access_token": token})
                        auth_resp = await ws.receive_json()
                        if auth_resp.get("type") != "auth_ok":
                            logger.error("HA WebSocket auth failed")
                            return

                    await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
                    await ws.send_json({"id": 2, "type": "subscribe_events", "event_type": "entity_registry_updated"})
                    # Gli altri registri dell'anagrafe (Task 5): entity_registry_updated
                    # e' gia' sottoscritto sopra (id 2) e va verso add_anagrafe_listener,
                    # che copre anche rinomini, spostamenti, disabilitazioni e cancellazioni
                    # (non solo le creazioni: quel filtro apparteneva al meccanismo storico
                    # verso add_registry_listener, uscito con la context map che lo chiamava
                    # -- fetta E3 Task 2, 2.0).
                    numero = 2
                    for tipo_evento in (t for t in EVENTI_ANAGRAFE if t != "entity_registry_updated"):
                        numero += 1
                        await ws.send_json({"id": numero, "type": "subscribe_events", "event_type": tipo_evento})
                    # Task 5: le plance hanno un ascoltatore proprio, separato
                    # dall'anagrafe (vedi EVENTO_PLANCE in cima al modulo).
                    numero += 1
                    await ws.send_json({"id": numero, "type": "subscribe_events", "event_type": EVENTO_PLANCE})
                    for tipo_evento in EVENTI_SERVIZI:
                        numero += 1
                        await ws.send_json({"id": numero, "type": "subscribe_events",
                                            "event_type": tipo_evento})

                    # Task 6: ogni (ri)connessione riuscita rifa' l'anagrafe, non solo
                    # gli eventi di registro ricevuti mentre la connessione era su. Un
                    # distacco (riavvio di HA, blip di rete, i 10s di backoff sotto)
                    # perde gli eventi emessi nel frattempo per sempre: nessuna
                    # rilettura successiva li recupera da sola, e l'anagrafe resta
                    # stantia in silenzio mentre `aggiornata_il` continua a raccontare
                    # l'ultima ricostruzione come se fosse il presente. Questo chiude
                    # anche la micro-finestra fra la lettura iniziale di _on_startup e
                    # la prima sottoscrizione qui sopra. L'antirimbalzo di
                    # programma_ricostruzione_anagrafe assorbe le riconnessioni
                    # ravvicinate, quindi non costa una lettura extra ad ogni giro.
                    # Stessa ragione del giro sull'anagrafe qui sotto: gli eventi
                    # emessi mentre la connessione era giu' non tornano, e un
                    # registro dei servizi stantio direbbe «non esiste in questa
                    # casa» di un servizio che esiste.
                    for cb in self._servizi_listeners:
                        try:
                            cb("riconnessione")
                        except Exception as cb_exc:
                            logger.exception("servizi_listener callback raised: %s", cb_exc)
                    for cb in self._anagrafe_listeners:
                        try:
                            cb("riconnessione")
                        except Exception as cb_exc:
                            logger.exception("anagrafe_listener callback raised: %s", cb_exc)
                    # Stessa logica per le plance: una disconnessione perde per
                    # sempre un eventuale EVENTO_PLANCE emesso nel frattempo.
                    for cb in self._plance_listeners:
                        try:
                            cb({})
                        except Exception as cb_exc:
                            logger.exception("plance_listener callback raised: %s", cb_exc)

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            if data.get("type") != "event":
                                continue
                            event = data.get("event", {})
                            event_type = event.get("event_type")
                            if event_type == "state_changed":
                                for cb in self._state_listeners:
                                    try:
                                        cb(event["data"])
                                    except Exception as cb_exc:
                                        logger.exception("state_listener callback raised: %s", cb_exc)
                            elif event_type == EVENTO_PLANCE:
                                # Il percorso della plancia cambiata sta in
                                # event["data"], ma non lo si usa per filtrare:
                                # chi ascolta rilegge tutte le plance (vedi
                                # EVENTO_PLANCE e rileggi_plance).
                                for cb in self._plance_listeners:
                                    try:
                                        cb(event.get("data", {}))
                                    except Exception as cb_exc:
                                        logger.exception("plance_listener callback raised: %s", cb_exc)
                            if event_type in EVENTI_SERVIZI:
                                for cb in self._servizi_listeners:
                                    try:
                                        cb(event_type)
                                    except Exception as cb_exc:
                                        logger.exception(
                                            "servizi_listener callback raised: %s", cb_exc)
                            if event_type in EVENTI_ANAGRAFE:
                                # La casa e' cambiata (create/update/move/remove, su
                                # qualsiasi registro): l'anagrafe va rifatta. Nessun
                                # filtro per action ne' per tipo di registro — vedi
                                # EVENTI_ANAGRAFE in cima al modulo.
                                for cb in self._anagrafe_listeners:
                                    try:
                                        cb(event_type)
                                    except Exception as cb_exc:
                                        logger.exception("anagrafe_listener callback raised: %s", cb_exc)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("HA WebSocket disconnected: %s — reconnecting in 10s", exc)
                await asyncio.sleep(10)
