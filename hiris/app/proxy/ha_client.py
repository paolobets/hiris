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
# ostile PRIMA di comporlo in un URL.
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
)

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

    # fetta E3 Task 8 ("escono i trentaquattro"): `get_history` e' uscito --
    # ORFANO DICHIARATO, i suoi call site (history_tools.py, calendar_tools.py)
    # erano gia' caduti col ToolDispatcher. Raccolto qui (fetta E3 Task 12):
    # verificato di nuovo, zero chiamanti in tutto il repo.

    # Review finale fetta E3, Important #3: `call_service` (POST
    # /api/services/{domain}/{service}) e' uscita -- era l'ULTIMA primitiva
    # di attuazione rimasta nel codebase, zero chiamanti di produzione (ne'
    # in questo modulo ne' altrove: verificato con grep sull'intero repo).
    # Nessun piano o report la dichiarava "tenuta apposta" (a differenza di
    # `get_statistics`), e il censimento non la vedeva: la stringa del suo
    # stesso log d'errore ("call_service %s.%s failed %s: %s") contava come
    # occorrenza nel codice, mascherando l'orfano. In un HIRIS che "conosce e
    # non agisce" la primitiva che agisce non deve esistere -- torna quando
    # tornera' un progetto agenti con perimetro e verifica umana.

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
    # `leggi_registri` (sopra) non li richiama: chiede
    # "config/config_entries/get_entries" direttamente nel suo batch WS, non
    # passando da `get_config_entries`.

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

    async def get_area_registry(self) -> list[dict]:
        return await self._ws_call("config/area_registry/list")

    async def get_entity_registry(self) -> list[dict]:
        return await self._ws_call("config/entity_registry/list")

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
        ("integrazioni", "config/config_entries/get_entries", None),
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
                logger.debug("registro %s non disponibile (%s)", nome, tipo)
                non_disponibili.append(nome)
                risultato = []
            if chiave == "categorie" and extra:
                ambito = extra.get("scope")
                risultato = [{**riga, "ambito": ambito} for riga in risultato]
            registri.setdefault(chiave, []).extend(risultato)
        return registri, non_disponibili

    def add_state_listener(self, callback: Callable[[dict], None]) -> None:
        self._state_listeners.append(callback)

    def add_anagrafe_listener(self, callback: Callable[[str], None]) -> None:
        """callback(tipo_evento) a ogni cambio di registro: la casa e' cambiata."""
        self._anagrafe_listeners.append(callback)

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
