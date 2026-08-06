import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import quote
import aiohttp

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Mirrors dispatcher._AUTOMATION_ID_RE (hiris/app/tools/dispatcher.py). HA
# automation ids are slug-style: lowercase alphanumeric + underscore. Reject
# anything else before composing a request path — last line of defense against
# path-injection/SSRF via a hostile automation_id (review A/#4).
_AUTOMATION_ID_RE = re.compile(r"^[a-z0-9_]+$")

# entity_id canonico (dominio.oggetto): stessa forma usata da
# get_calendar_events_range. Serve a rifiutare un entity_id ostile PRIMA di
# comporlo in un URL.
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

# Chiavi che identificano la forma minima di un'automazione Home Assistant.
# Fino a HA 2024.10 i nomi erano al singolare (trigger/condition/action); da li'
# in poi i nomi canonici sono al plurale, ma i singolari restano accettati per
# retrocompatibilita' — quindi vanno riconosciuti entrambi, o si rifiuterebbero
# automazioni legittime scritte nell'una o nell'altra forma.
_TRIGGER_KEYS = ("triggers", "trigger")
_ACTION_KEYS = ("actions", "action")

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


def is_automation_config(config: object) -> bool:
    """True se `config` ha la forma minima di un'automazione Home Assistant.

    Home Assistant richiede due sole cose perche' un'automazione sia
    un'automazione: i trigger e le azioni. Tutto il resto (alias, description,
    mode, id, conditions) e' facoltativo. Fa eccezione l'automazione costruita
    su un blueprint, che non ha trigger ne' azioni proprie — li eredita dal
    blueprint — e porta solo `use_blueprint` (path + input): e' una terza forma
    legittima e va accettata.

    Il controllo e' volutamente sulla STRUTTURA e non sul CONTENUTO: HA accetta
    la stessa cosa scritta in piu' modi (singolare o plurale, un mapping singolo
    al posto di una lista, liste vuote) e imitare la sua validazione qui
    significherebbe rifiutare automazioni valide. Basta distinguere una
    configurazione di automazione da un dizionario qualsiasi: senza queste
    chiavi non c'e' nulla che possa scattare ne' nulla che possa succedere, e
    scriverla in HA produrrebbe un'automazione inerte (o un errore) dopo che
    l'utente ha premuto "attiva".
    """
    if not isinstance(config, dict) or not config:
        return False
    blueprint = config.get("use_blueprint")
    if isinstance(blueprint, dict) and blueprint:
        return True
    has_trigger = any(config.get(k) is not None for k in _TRIGGER_KEYS)
    has_action = any(config.get(k) is not None for k in _ACTION_KEYS)
    return has_trigger and has_action


def is_automation_entity_id(value: object) -> bool:
    """True se `value` ha la forma di un entity_id di automazione
    (`automation.<slug>`) — la forma che l'LLM confonde spesso con l'id
    numerico che HA usa nell'URL di configurazione (bug live-verify #3: la
    proposta aveva 'automation.avviso_...' in config['id'] al posto dell'id
    numerico). Solo forma, nessuna verifica che l'automazione esista davvero:
    quella spetta a resolve_automation_id_by_entity_id.

    M-4: valida sull'intera stringa con _ENTITY_ID_RE (la stessa forma
    canonica dominio.oggetto usata da get_calendar_events_range) invece di
    applicare _AUTOMATION_ID_RE al solo suffisso -- terza convenzione che si
    era infilata in questo stesso file per fare la stessa domanda.

    Condivisa fra HAClient.create_automation (Correzione 1) e
    create_automation_proposal (Correzione 2) cosi' le due validazioni non
    divergono su cosa conta come 'sembra un entity_id'."""
    return (isinstance(value, str) and value.startswith("automation.")
            and bool(_ENTITY_ID_RE.match(value)))


def is_automation_id_candidate(value: object) -> bool:
    """True se `value` ha una delle TRE forme che HA accetta per identificare
    un'automazione esistente: id numerico, entity_id (`automation.<slug>`) o
    object_id nudo (`<slug>`) -- lo stesso contratto a tre forme che
    get_automation_config accetta da sempre (righe piu' sotto) e che
    trigger_automation/toggle_automation (automation_tools.py) e
    create_automation (risoluzione dell'id fornito) usano per lo stesso oggetto.

    Solo forma, nessuna verifica che l'automazione esista davvero (quella
    spetta a resolve_automation_id_by_entity_id / get_automation_config).

    C-2: prima di questa funzione la validazione alla CREAZIONE della
    proposta (proposal_tools.py) riconosceva solo due forme (numerico,
    entity_id) mentre l'APPLY (create_automation, sotto) ne accetta tre da
    sempre -- il gate rifiutava una proposta che l'apply avrebbe applicato.
    Principio: alla creazione si rifiuta SOLO cio' che l'apply rifiuterebbe
    di sicuro, quindi le due validazioni condividono questo unico predicato."""
    if not isinstance(value, str) or not value:
        return False
    if value.isascii() and value.isdigit():
        return True
    if is_automation_entity_id(value):
        return True
    return bool(_AUTOMATION_ID_RE.match(value))


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
        self._registry_listeners: list[Callable[[str, dict], None]] = []
        self._action_listeners: list[Callable[[dict], None]] = []

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

    async def get_history(self, entity_ids: list[str], days: int) -> list[dict]:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        # Review L/4 (defense in depth): quote each entity id before joining
        # -- currently safe only because both call sites (history_tools.py,
        # calendar_tools.py) pre-validate with a strict regex, but this way
        # the query string stays safe even if a future caller skips that.
        filter_param = ",".join(quote(eid, safe="") for eid in entity_ids)
        url = f"{self._base_url}/api/history/period/{start}?filter_entity_id={filter_param}&minimal_response=true"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            nested: list[list[dict]] = await resp.json()
        return [item for sublist in nested for item in sublist]

    async def call_service(self, domain: str, service: str, data: dict) -> bool:
        if not _IDENTIFIER_RE.match(domain) or not _IDENTIFIER_RE.match(service):
            logger.error("Rejected invalid domain/service: %r.%r", domain, service)
            return False
        url = f"{self._base_url}/api/services/{domain}/{service}"
        async with self._session.post(url, json=data) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error("call_service %s.%s failed %s: %s", domain, service, resp.status, body)
                return False
            return True

    async def get_automations(self) -> list[dict]:
        url = f"{self._base_url}/api/states"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            all_states: list[dict] = await resp.json()
        return [s for s in all_states if s["entity_id"].startswith("automation.")]

    async def create_automation(self, config: dict,
                                automation_id: str | None = None) -> dict:
        """Create/replace a UI-managed automation via HA's config API, then reload.
        Returns {"ok": True, "id": <id>} or {"error": ...}. Human-gated upstream."""
        # Consolidamento 1.2: non basta "un dizionario non vuoto". Un config
        # senza trigger ne' azioni diventava in HA un'automazione inerte dopo
        # che l'utente aveva approvato la proposta — la stessa promessa non
        # mantenuta del bug di luglio, con il tipo giusto e il contenuto
        # sbagliato. Si rifiuta qui, prima di coniare l'id e di scrivere.
        if not is_automation_config(config):
            return {"error": ("config automazione non valida: servono i trigger e le "
                              "azioni (oppure use_blueprint)")}
        # Update-in-place vs create: HA identifies a UI automation by the {id}
        # in the config URL. To MODIFY an existing automation we must reuse its
        # id — take it from the explicit param, else from the config's own "id"
        # field (get_automation_config returns it). Se nessuno dei due c'e' ma il
        # config ha un `alias` che corrisponde UNIVOCAMENTE a un'automazione
        # esistente, modifichiamo quella: l'LLM spesso propone il fix di
        # un'automazione SENZA riportarne l'id, e senza questo si creava un
        # doppione invece di sovrascrivere l'originale (bug live-verify #2).
        # Solo come ultima risorsa si conia un id nuovo (automazione davvero nuova).
        async def _by_alias() -> str | None:
            alias = config.get("alias")
            if isinstance(alias, str) and alias.strip():
                return await self.resolve_automation_id_by_alias(alias.strip())
            return None

        aid = str(automation_id or config.get("id") or "")
        # Un id FORNITO ma non numerico non e' "assente": e' un bersaglio
        # dichiarato, quasi sempre l'entity_id (o l'object_id nudo) al posto
        # dell'id numerico (bug live-verify #3). Le forme provate qui sotto
        # sono le stesse tre che get_automation_config accetta (C-2):
        # numerico (gia' escluso dall'if), entity_id, object_id nudo.
        #
        # DECISIONE (review C-1, non negoziabile): se l'id fornito non
        # risolve a NESSUNA di queste forme, si FALLISCE -- MAI un ripiego
        # sull'alias. Chi ha nominato un bersaglio ha gia' espresso
        # un'intenzione precisa: se quel bersaglio non esiste, indovinarne un
        # altro dal `friendly_name` e sovrascriverlo sarebbe un danno
        # irreversibile e silenzioso -- a differenza delle plance
        # (config_tools.apply_ha_config, mode == "replace"), qui non esiste
        # nessuno snapshot da cui tornare indietro. Il ripiego per alias
        # resta SOLO nel ramo "if not aid" qui sotto, dove non c'e' un
        # bersaglio dichiarato da tradire: e' il caso per cui era stato
        # costruito (bug live-verify #2).
        if aid and not (aid.isascii() and aid.isdigit()):
            if not is_automation_id_candidate(aid):
                return {"error": (
                    f"id automazione non valido: {aid!r}. Serve l'id numerico "
                    "che Home Assistant usa nell'URL di configurazione (lo "
                    "restituisce get_automation_config), oppure l'entity_id "
                    "(automation.<nome>) o l'object_id nudo (<nome>) di "
                    "un'automazione esistente. Per creare una automazione "
                    "nuova, ometti 'id'.")}
            eid = aid if aid.startswith("automation.") else f"automation.{aid}"
            resolved, lookup_failed = await self.resolve_automation_id_by_entity_id(eid)
            if resolved:
                aid = resolved
            elif lookup_failed:
                # I-3: un guasto di HA durante la verifica non e' "id
                # sbagliato", e' "non ho potuto controllare" -- confondere i
                # due casi spinge il modello a seguire il consiglio "ometti
                # l'id" e a creare il doppione che il bug live-verify #2
                # aveva chiuso. Nessuna scrittura in nessuno dei due casi.
                return {"error": (
                    f"non sono riuscito a verificare l'id fornito ({aid!r}): "
                    "Home Assistant non ha risposto alla lettura delle "
                    "automazioni esistenti. Riprova; l'automazione indicata "
                    "potrebbe esistere davvero.")}
            else:
                # Deliberato: NON si conia un id nuovo qui. Chi ha scritto un
                # id (anche sbagliato) ha indicato un bersaglio preciso e non
                # voleva un doppione — coniare un id nuovo produrrebbe
                # un'automazione indesiderata invece di segnalare l'errore.
                return {"error": (
                    f"id automazione non valido: {aid!r}. Nessuna automazione "
                    "esistente corrisponde a questo id. Serve l'id numerico "
                    "che Home Assistant usa nell'URL di configurazione (lo "
                    "restituisce get_automation_config). Per creare una "
                    "automazione nuova, ometti 'id'.")}
        if not aid:
            resolved = await _by_alias()
            if resolved:
                aid = resolved
        if not aid:
            aid = str(int(datetime.now(timezone.utc).timestamp() * 1_000_000))
        if not (aid.isascii() and aid.isdigit()):
            return {"error": "automation_id non valido"}
        # id coerente anche nel body scritto (l'URL identifica l'automazione, ma
        # teniamo il config allineato).
        body = {**config, "id": aid}
        url = f"{self._base_url}/api/config/automation/config/{aid}"
        try:
            async with self._session.post(url, json=body) as resp:
                if resp.status not in (200, 201):
                    err = await resp.text()
                    return {"error": f"HA ha rifiutato la config ({resp.status}): {err[:200]}"}
        except Exception as exc:
            # M-5: mai fare eco di str(exc) al chiamante (puo' contenere host,
            # path o dettagli di libreria) -- stessa regola gia' rispettata da
            # render_template. Questa funzione e' quella che il commit
            # riapre, quindi e' quella sanata qui; _post_config e
            # get_automation_config hanno la stessa forma pre-esistente ma
            # restano fuori dal perimetro di questa fix wave.
            logger.warning("create_automation: scrittura fallita (id=%s): %s", aid, exc)
            return {"error": "scrittura automazione fallita"}
        # Reload so the new automation becomes active immediately (idempotent).
        try:
            await self.call_service("automation", "reload", {})
        except Exception as exc:
            logger.warning("automation.reload after create failed (automation %s persisted, "
                           "will load on next HA restart): %s", aid, exc)
        return {"ok": True, "id": aid}

    async def resolve_automation_id_by_alias(self, alias: str) -> str | None:
        """L'id numerico dell'automazione il cui `friendly_name` == alias, SOLO se
        il match e' UNIVOCO (altrimenti None: ambiguo o assente). Usato per
        modificare l'automazione giusta quando la proposta non riporta l'id.
        Non solleva mai (fail-safe): in caso di errore -> None -> id nuovo."""
        try:
            autos = await self.get_automations()
        except Exception:
            return None
        ids = []
        for a in autos or []:
            attrs = a.get("attributes") or {}
            if attrs.get("friendly_name") == alias:
                aid = str(attrs.get("id") or "")
                if aid.isascii() and aid.isdigit():
                    ids.append(aid)
        return ids[0] if len(ids) == 1 else None

    async def resolve_automation_id_by_entity_id(self, entity_id: str) -> tuple[str | None, bool]:
        """(id, lookup_fallito).

        id: l'id numerico dell'automazione il cui `entity_id` == entity_id, se
        trovato ed e' un numero valido (altrimenti None). Gemello di
        resolve_automation_id_by_alias: stessa fonte `get_automations()`,
        stesso controllo isascii()/isdigit() sull'id trovato. A differenza
        dell'alias (un `friendly_name` puo' ripetersi su piu' automazioni)
        l'entity_id e' univoco per costruzione in HA: non serve alcun
        controllo di ambiguita'.

        lookup_fallito: True quando `get_automations()` ha sollevato -- in tal
        caso `id is None` NON significa "nessuna automazione con questo
        entity_id", significa "non ho potuto controllare" (stessa classe A3
        gia' chiusa in proxy.entity_cache.inventario_non_leggibile: un elenco
        vuoto/None racconta due cose diverse e il chiamante deve poterle
        distinguere). Prima di questa distinzione (I-3) un guasto transitorio
        di HA durante `create_automation` veniva raccontato al modello come
        "id automazione non valido", col consiglio di ometterlo -- che produce
        il doppione gia' chiuso dal bug live-verify #2.

        Non solleva mai (fail-safe)."""
        try:
            autos = await self.get_automations()
        except Exception:
            return None, True
        for a in autos or []:
            if a.get("entity_id") != entity_id:
                continue
            attrs = a.get("attributes") or {}
            aid = str(attrs.get("id") or "")
            return (aid if aid.isascii() and aid.isdigit() else None), False
        return None, False

    @staticmethod
    def _is_slug(value: str) -> bool:
        return bool(value) and all(c.islower() or c.isdigit() or c == "_" for c in value)

    async def _post_config(self, path: str, config: dict) -> dict:
        """POST a UI-managed config to /api/config/{path}. Returns ok/error."""
        url = f"{self._base_url}/api/config/{path}"
        try:
            async with self._session.post(url, json=config) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    return {"error": f"HA ha rifiutato la config ({resp.status}): {body[:200]}"}
        except Exception as exc:
            return {"error": f"scrittura config fallita: {exc}"}
        return {"ok": True}

    async def create_script(self, object_id: str, config: dict) -> dict:
        """Create a UI-managed script via HA config API, then reload. Human-gated upstream."""
        if not isinstance(config, dict) or not config:
            return {"error": "config script vuota o non valida"}
        if not self._is_slug(object_id):
            return {"error": "object_id script non valido (usa a-z 0-9 _)"}
        res = await self._post_config(f"script/config/{object_id}", config)
        if res.get("error"):
            return res
        try:
            await self.call_service("script", "reload", {})
        except Exception as exc:
            logger.warning("script.reload after create failed (script %s persisted): %s", object_id, exc)
        return {"ok": True, "id": object_id}

    async def create_scene(self, scene_id: str, config: dict) -> dict:
        """Create a UI-managed scene via HA config API, then reload. Human-gated upstream."""
        if not isinstance(config, dict) or not config:
            return {"error": "config scena vuota o non valida"}
        if not self._is_slug(scene_id):
            return {"error": "scene_id non valido (usa a-z 0-9 _)"}
        res = await self._post_config(f"scene/config/{scene_id}", config)
        if res.get("error"):
            return res
        try:
            await self.call_service("scene", "reload", {})
        except Exception as exc:
            logger.warning("scene.reload after create failed (scene %s persisted): %s", scene_id, exc)
        return {"ok": True, "id": scene_id}

    @staticmethod
    def _ws_error(msg: dict | None) -> str:
        if not msg:
            return "nessuna risposta WS"
        err = msg.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        return str(err or "errore WS sconosciuto")

    async def create_dashboard(self, url_path: str, title: str, config: dict,
                               icon: str | None = None, show_in_sidebar: bool = True) -> dict:
        """Create a new storage-mode Lovelace dashboard + save its config (two WS commands).
        Additive: appears as a new sidebar entry; never touches existing dashboards."""
        if not isinstance(config, dict) or "views" not in config:
            return {"error": "config dashboard non valida (manca 'views')"}
        created = await self._ws_command("lovelace/dashboards/create", {
            "url_path": url_path,
            "title": title,
            "icon": icon,
            "show_in_sidebar": bool(show_in_sidebar),
            "require_admin": False,
            "mode": "storage",
        })
        if not created or not created.get("success"):
            return {"error": f"creazione dashboard fallita: {self._ws_error(created)}"}
        saved = await self._ws_command("lovelace/config/save", {
            "url_path": url_path,
            "config": config,
        })
        if not saved or not saved.get("success"):
            # Roll back the just-created (guaranteed new) dashboard so the pending
            # proposal stays retryable: without this, a retry hits the now-existing
            # url_path and fails forever, leaving an orphan empty dashboard.
            # Best-effort — we only delete what THIS call created (create succeeded,
            # so url_path was new), never a pre-existing dashboard.
            dash_id = (created.get("result") or {}).get("id")
            if dash_id:
                rolled = await self._ws_command(
                    "lovelace/dashboards/delete", {"dashboard_id": dash_id}
                )
                if not rolled or not rolled.get("success"):
                    logger.warning(
                        "dashboard rollback failed (url_path=%s id=%s): %s — orphan dashboard remains",
                        url_path, dash_id, self._ws_error(rolled),
                    )
            else:
                logger.warning(
                    "dashboard rollback skipped: create response had no id (url_path=%s) — orphan may remain",
                    url_path,
                )
            return {"error": f"salvataggio config dashboard fallito: {self._ws_error(saved)}"}
        return {"ok": True, "url_path": url_path}

    async def get_lovelace_config(self, url_path: str) -> dict:
        """Return the current Lovelace config of a storage-mode dashboard via WS.
        Returns the config dict (with 'views'), or {"error": ...} if unavailable."""
        got = await self._ws_command(
            "lovelace/config", {"url_path": url_path, "force": False}
        )
        if not got or not got.get("success"):
            return {"error": f"config dashboard non leggibile: {self._ws_error(got)}"}
        result = got.get("result")
        if not isinstance(result, dict):
            return {"error": "config dashboard vuota o in modalità YAML (non gestita da storage)"}
        return result

    async def list_dashboards(self) -> list[dict] | dict:
        """Elenca le dashboard Lovelace (storage mode) via WS.
        Ritorna una lista di {url_path, title, mode} oppure {"error": ...}."""
        got = await self._ws_command("lovelace/dashboards/list", {})
        if not got or not got.get("success"):
            return {"error": f"elenco dashboard non leggibile: {self._ws_error(got)}"}
        result = got.get("result")
        if not isinstance(result, list):
            return {"error": "elenco dashboard vuoto o non valido"}
        out = []
        for d in result:
            if isinstance(d, dict):
                out.append({
                    "url_path": d.get("url_path"),
                    "title": d.get("title"),
                    "mode": d.get("mode"),
                })
        return out

    async def save_dashboard_config(self, url_path: str, config: dict) -> dict:
        """Sovrascrive la config di una dashboard storage-mode esistente.
        NON crea la dashboard: usare create_dashboard per quello.

        Home Assistant ammette DUE forme di config Lovelace valide: quella a
        viste ({"views": [...]}) e quella a strategia ({"strategy": {...}},
        senza 'views') usata dalle dashboard generate da template. Qui le
        accettiamo entrambe perche' il client HA deve accettare cio' che HA
        accetta: altrimenti il ripristino di uno snapshot "strategy" (pulsante
        Annulla dopo un replace) verrebbe rifiutato con 502 pur avendo lo
        snapshot su disco. La validazione stretta che pretende 'views' resta
        invece in tools/dashboard_tools.propose_dashboard, dove il contenuto e'
        scritto da un LLM: il tool accetta solo cio' che il modello puo'
        legittimamente proporre. La distinzione e' voluta."""
        if not isinstance(config, dict) or not ("views" in config or "strategy" in config):
            return {"error": "config dashboard non valida (serve 'views' o 'strategy')"}
        saved = await self._ws_command(
            "lovelace/config/save", {"url_path": url_path, "config": config}
        )
        if not saved or not saved.get("success"):
            return {"error": f"salvataggio config dashboard fallito: {self._ws_error(saved)}"}
        return {"ok": True, "url_path": url_path}

    async def get_automation_config(self, automation_id: str) -> dict:
        """Return the config (YAML-equivalent dict) of a UI-managed automation.

        `automation_id` may be the numeric unique id, the entity_id
        ('automation.foo') or the object_id ('foo'). HA's config API only serves
        automations created/managed via the UI (404 for hand-written YAML ones)."""
        numeric = str(automation_id or "")
        if not numeric.isascii() or not numeric.isdigit():
            bare = numeric[len("automation."):] if numeric.startswith("automation.") else numeric
            if not _AUTOMATION_ID_RE.match(bare):
                return {"error": "automation_id non valido"}
            eid = f"automation.{bare}"
            numeric = ""
            try:
                async with self._session.get(f"{self._base_url}/api/states/{eid}") as r:
                    if r.status == 200:
                        s = await r.json()
                        numeric = str(s.get("attributes", {}).get("id", "") or "")
            except Exception:
                numeric = ""
        if not numeric:
            return {"error": "automazione non trovata o priva di id univoco"}
        url = f"{self._base_url}/api/config/automation/config/{numeric}"
        try:
            async with self._session.get(url) as resp:
                if resp.status == 404:
                    return {"error": "config non disponibile: l'automazione non e' "
                                     "gestita dalla UI di HA (forse definita a mano in YAML)"}
                resp.raise_for_status()
                return await resp.json()
        except Exception as exc:
            return {"error": f"lettura config fallita: {exc}"}

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
        # start sta nel path (come get_history); end_time ed entity stanno nella
        # query, dove il "+" del fuso orario va percent-encoded o verrebbe letto
        # come spazio.
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

    async def get_config_entries(self) -> list[dict]:
        """Le voci di configurazione di HA, grezze — l'elenco delle integrazioni.

        Prima questo metodo restituiva le sole voci in ERRORE, con le chiavi
        rinominate: il nome mentiva, e l'elenco delle integrazioni installate
        — che sta qui dentro — veniva buttato. Il filtro ora vive dove serve,
        in health_monitor.errori_di_integrazione().
        """
        return await self._ws_call("config/config_entries/get_entries")

    async def get_system_info(self) -> dict:
        """Return HA system info from /api/config."""
        url = f"{self._base_url}/api/config"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return {
            "ha_version": data.get("version", "unknown"),
            "config_dir": data.get("config_dir", ""),
            "state": data.get("state", "unknown"),
            "unit_system": data.get("unit_system", {}).get("length", ""),
        }

    async def get_updates(self) -> list[dict]:
        """Return available updates from HA update.* entities."""
        url = f"{self._base_url}/api/states"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            all_states: list[dict] = await resp.json()
        updates = []
        for s in all_states:
            entity_id = s.get("entity_id", "")
            if entity_id.startswith("update.") and s.get("state") == "on":
                attrs = s.get("attributes", {})
                updates.append({
                    "entity_id": entity_id,
                    "name": attrs.get("friendly_name", s["entity_id"]),
                    "current": attrs.get("installed_version", "?"),
                    "available": attrs.get("latest_version", "?"),
                    "release_url": attrs.get("release_url"),
                })
        return updates

    async def get_calendars(self) -> list[dict]:
        """Return list of all calendar entities from HA."""
        url = f"{self._base_url}/api/calendars"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_calendar_events_range(self, entity_id: str, start: str, end: str) -> list[dict]:
        """Return events for a single calendar entity in [start, end] ISO8601 range."""
        if not re.match(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$", entity_id):
            logger.warning("Rejected invalid calendar entity_id: %r", entity_id)
            return []
        from urllib.parse import quote
        url = f"{self._base_url}/api/calendars/{entity_id}?start={quote(start, safe='')}&end={quote(end, safe='')}"
        async with self._session.get(url) as resp:
            if resp.status == 404:
                return []
            resp.raise_for_status()
            return await resp.json()

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

    def add_action_listener(self, callback: Callable[[dict], None]) -> None:
        """Register callback(event_data) for mobile_app_notification_action events
        (the actionable-notification button taps)."""
        self._action_listeners.append(callback)

    def add_registry_listener(self, callback: Callable[[str, dict], None]) -> None:
        """Register callback(entity_id, attributes) for entity_registry_updated events."""
        self._registry_listeners.append(callback)

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
                    await ws.send_json({"id": 3, "type": "subscribe_events", "event_type": "mobile_app_notification_action"})

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
                            elif event_type == "mobile_app_notification_action":
                                for cb in self._action_listeners:
                                    try:
                                        cb(event.get("data", {}))
                                    except Exception as cb_exc:
                                        logger.exception("action_listener callback raised: %s", cb_exc)
                            elif event_type == "entity_registry_updated":
                                action = event.get("data", {}).get("action")
                                if action == "create":
                                    eid = event["data"].get("entity_id", "")
                                    attrs = event["data"]  # full payload for create events
                                    for cb in self._registry_listeners:
                                        try:
                                            cb(eid, attrs)
                                        except Exception as cb_exc:
                                            logger.exception("registry_listener callback raised: %s", cb_exc)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("HA WebSocket disconnected: %s — reconnecting in 10s", exc)
                await asyncio.sleep(10)
