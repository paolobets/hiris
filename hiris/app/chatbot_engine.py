import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .proxy.ha_client import HAClient

logger = logging.getLogger(__name__)


# Fix 4 (Important, whole-branch review, final fix wave): nomi dei due tool ritirati
# dalla fusione di Task 2 (recall_knowledge/save_knowledge -> recall_memory/
# save_memory). Un Chatbot creato PRIMA di questo branch puo' averli ancora
# nel proprio `allowed_tools` persistito (erano due checkbox separate); lo
# stesso vale per la CSV EXECUTE_API_TOOLS delle opzioni dell'add-on.
#
# fetta E3 Task 9 (rilievo 2 della review indipendente sul blocco 5-8):
# questo commento affermava ancora al presente che "il filtro per nome
# esatto (claude_runner.py:713, `t["name"] in allowed_tools`) non li
# riconosce piu'" -- quel filtro non esiste da `bca1b85` (Task 8: il
# catalogo di scorta che filtrava per `allowed_tools` e' uscito insieme al
# suo unico chiamante). Cio' che e' vero oggi, verificato leggendo il
# codice: il parametro `allowed_tools` di `chat()`/`chat_stream()` era
# rimasto inerte in entrambi i runner (nessun corpo lo leggeva piu') -- il
# Task 9 lo ha tolto dalla firma. `Chatbot.allowed_tools` (questo campo)
# non alimenta piu' nessun filtro di runtime: e' solo configurazione
# persistita che riempie il catalogo a checkbox di
# `static/config/templates.js` (resta li' fino alla E5). `normalize_tool_names`
# continua a riscrivere qui i nomi legacy al caricamento perche' altrimenti
# quell'editor mostrerebbe checkbox per nomi di tool che non esistono piu'.
LEGACY_TOOL_ALIASES = {
    "recall_knowledge": "recall_memory",
    "save_knowledge": "save_memory",
}


def normalize_tool_names(names: list[str]) -> list[str]:
    """Applica LEGACY_TOOL_ALIASES e de-duplica, preservando l'ordine di
    prima comparsa. Idempotente: rieseguirla sul proprio output non cambia
    nulla. Va chiamata in OGNI punto che legge un elenco di nomi di tool
    persistito/configurato da prima della fusione -- oggi
    `chatbot_engine.py` (Chatbot.allowed_tools, al caricamento). Un secondo
    chiamante viveva in `handlers_execute.py` (parse_execute_policy, la CSV
    EXECUTE_API_TOOLS): uscito con la Fetta E2 Task 4 insieme a tutta la
    superficie /api/execute."""
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        mapped = LEGACY_TOOL_ALIASES.get(n, n)
        if mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


DEFAULT_CHATBOTS_DATA_PATH = "/data/chatbots.json"
DEFAULT_CHATBOT_ID = "hiris-default"


@dataclass
class Chatbot:
    # Slice 5 Task 2: this dataclass is a persona (used only by chat) — the
    # "proactive" execution fields that used to describe an autonomous agent
    # (type, triggers, action_mode, rules, states, fallback_action,
    # budget_eur_limit) are gone. Task 1 already retired the engine code that
    # scheduled/reacted/executed on them (the manual "run" path that survived
    # them, `_run_chatbot`, is gone too now -- fetta E4 Task 2); this task
    # trims the schema itself now that nothing reads those fields.
    id: str
    name: str
    system_prompt: str
    allowed_tools: list
    enabled: bool
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    strategic_context: str = ""
    allowed_entities: list = field(default_factory=list)
    allowed_services: list = field(default_factory=list)
    is_default: bool = False
    model: str = "auto"
    max_tokens: int = 4096
    restrict_to_home: bool = False
    require_confirmation: bool = False   # chat only
    execution_log: list = field(default_factory=list)
    max_chat_turns: int = 0              # chat only
    allowed_endpoints: Optional[list] = None
    response_mode: str = "auto"
    # Extended Thinking budget tokens (0 = disabled).
    # When >0, Claude returns thinking blocks alongside the answer (sonnet-4.5+/
    # opus-4+ only). The runner clamps to max_tokens-1 if invalid.
    thinking_budget: int = 0
    knowledge_access: dict = field(default_factory=lambda: {"allow_sensitive": False, "kinds": "all"})


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ChatbotEngine:
    def __init__(self, ha_client: HAClient, data_path: str = DEFAULT_CHATBOTS_DATA_PATH) -> None:
        self._chatbots: dict[str, Chatbot] = {}
        self._scheduler = AsyncIOScheduler()
        self._claude_runner: Any = None
        self._ha = ha_client
        self._data_path = data_path
        self._entity_cache: Any = None
        self._archivio_casa: Any = None
        self._archivio_memoria: Any = None
        self._running_chatbots: set[str] = set()
        self._error_chatbots: set[str] = set()
        # Serialize tmp-write + os.replace across concurrent _save() calls
        # (executor uses a thread pool — two fire-and-forget _save() can otherwise
        # overlap on the same .tmp file and corrupt state).
        self._save_lock = threading.Lock()

    def set_claude_runner(self, runner: Any) -> None:
        self._claude_runner = runner

    def set_entity_cache(self, cache: Any) -> None:
        self._entity_cache = cache

    def set_archivi(self, archivio_casa, archivio_memoria) -> None:
        """Gli archivi della conoscenza, iniettati come la cache: il motore
        nasce prima di loro in `create_app()`."""
        self._archivio_casa = archivio_casa
        self._archivio_memoria = archivio_memoria

    async def start(self) -> None:
        # Il WebSocket verso HA e' del server (`server.py::_on_startup`), non
        # dell'engine: parte dopo la registrazione dei listener, prima di
        # questo `start()` -- i sensi della casa non dipendono dai chatbot.
        self._scheduler.start()
        self._load()
        self._seed_default_chatbot()
        logger.info("ChatbotEngine started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("ChatbotEngine stopped")

    def _save(self) -> None:
        # schema_version 4 (SP-4 Fase A Task 1: Agent -> Chatbot rename).
        # schema_version 3 (Slice 5 Task 2) dropped the proactive-only
        # fields (type/triggers/action_mode/rules/states/fallback_action/
        # budget_eur_limit) from the persisted shape. No migration on load —
        # a v1/v2 file simply has those keys ignored by _load()'s explicit
        # field list below.
        data = {"schema_version": 4, "chatbots": [asdict(c) for c in self._chatbots.values()]}
        tmp = self._data_path + ".tmp"
        lock = self._save_lock

        def _write() -> None:
            with lock:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, default=str)
                    os.replace(tmp, self._data_path)
                except Exception as exc:
                    logger.error("Failed to persist chatbots: %s", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _write)
        except RuntimeError:
            _write()

    def _load(self) -> None:
        # One-time migration agents.json -> chatbots.json (idempotente).
        legacy = self._data_path.replace("chatbots.json", "agents.json")
        if not os.path.exists(self._data_path) and os.path.exists(legacy):
            try:
                with open(legacy, encoding="utf-8") as f:
                    raw = json.load(f)
                raw.setdefault("chatbots", raw.pop("agents", []))
                raw["schema_version"] = 4
                tmp = self._data_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, default=str)
                os.replace(tmp, self._data_path)
                logger.info("Migrated agents.json -> chatbots.json")
            except Exception:
                logger.warning("agents.json migration failed", exc_info=True)
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("chatbots", data.get("agents", [])):
                chatbot = Chatbot(
                    id=raw["id"],
                    name=raw["name"],
                    system_prompt=raw.get("system_prompt", ""),
                    # Fix 4 (whole-branch review, final fix wave): a Chatbot persisted
                    # before the memoria-unica merge may still name the
                    # retired recall_knowledge/save_knowledge tools here --
                    # normalize_tool_names maps them to the current
                    # recall_memory/save_memory (and de-duplicates, in case
                    # both the old and new name were ever saved together).
                    allowed_tools=normalize_tool_names(raw.get("allowed_tools", [])),
                    enabled=raw.get("enabled", True),
                    is_default=raw.get("is_default", False),
                    last_run=raw.get("last_run"),
                    last_result=raw.get("last_result"),
                    strategic_context=raw.get("strategic_context", ""),
                    allowed_entities=raw.get("allowed_entities", []),
                    allowed_services=raw.get("allowed_services", []),
                    model=raw.get("model", "auto"),
                    max_tokens=raw.get("max_tokens", 4096),
                    restrict_to_home=raw.get("restrict_to_home", False),
                    require_confirmation=raw.get("require_confirmation", False),
                    execution_log=raw.get("execution_log", []),
                    max_chat_turns=int(raw.get("max_chat_turns", 0)),
                    allowed_endpoints=raw.get("allowed_endpoints"),
                    response_mode=raw.get("response_mode", "auto"),
                    thinking_budget=int(raw.get("thinking_budget", 0) or 0),
                    knowledge_access=raw.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
                )
                self._chatbots[chatbot.id] = chatbot
        except Exception as exc:
            logger.error("Failed to load chatbots from %s: %s", self._data_path, exc)

    # Review finale fetta E3, Important #2: la versione precedente istruiva a
    # chiamare `get_home_status()`/`get_area_entities()`, morti dalla E2
    # Task 8 -- catturato dal vivo in un turno di chat reale (il runner
    # riceveva esattamente questo prompt). Riscritta sui due strumenti veri
    # di oggi (casa/strumenti.py: cerca, guarda).
    _DEFAULT_SYSTEM_PROMPT = (
        "Sei l'assistente principale per la gestione della smart home.\n"
        "Per scoprire cosa c'è in casa usa `cerca` (trova per nome un'area, un'entità o un"
        " dispositivo) e `guarda` (il dettaglio di una cosa sola, col suo stato).\n"
        "La sezione CASA in fondo al prompt è uno snapshot di orientamento:"
        " usa i tool per valori precisi come temperature e stati correnti."
    )

    _LEGACY_DEFAULT_PROMPTS = {
        "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente.",
        "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
        # Il default precedente a questa correzione: un'installazione che lo
        # ha ancora persistito su disco va migrata al nuovo, non incontrata
        # in silenzio (stessa disciplina delle due righe sopra).
        "Sei l'assistente principale per la gestione della smart home.\n"
        "Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
        "La sezione CASA in fondo al prompt è uno snapshot di orientamento:"
        " usa i tool per valori precisi come temperature e stati correnti.",
    }

    def _seed_default_chatbot(self) -> None:
        if DEFAULT_CHATBOT_ID not in self._chatbots:
            chatbot = Chatbot(
                id=DEFAULT_CHATBOT_ID,
                name="HIRIS",
                system_prompt=self._DEFAULT_SYSTEM_PROMPT,
                allowed_tools=[],
                enabled=True,
                is_default=True,
            )
            self._chatbots[DEFAULT_CHATBOT_ID] = chatbot
            self._save()
        else:
            chatbot = self._chatbots[DEFAULT_CHATBOT_ID]
            changed = False
            if chatbot.system_prompt in self._LEGACY_DEFAULT_PROMPTS:
                chatbot.system_prompt = self._DEFAULT_SYSTEM_PROMPT
                changed = True
            if chatbot.allowed_tools:
                chatbot.allowed_tools = []
                changed = True
            if changed:
                self._save()

    def get_default_chatbot(self) -> Optional[Chatbot]:
        return self._chatbots.get(DEFAULT_CHATBOT_ID)

    # fetta E4 Task 3 ("un bot solo"): `create_chatbot`/`update_chatbot`/
    # `delete_chatbot` sono usciti insieme alle rotte HTTP che erano il loro
    # unico chiamante (server.py/handlers_chatbots.py) -- le tre strade di
    # creazione sopravvissute alla E3 (wizard, editor vuoto, onboarding
    # della chat) convergevano tutte su POST /api/chatbots con
    # `enabled: true` di default, il contrario di quanto prescrive lo
    # scope. `UPDATABLE_FIELDS` (la mappa di campi di `update_chatbot`) e
    # `_cap_max_tokens`/`_CHAT_MAX_TOKENS_CAP` (usati solo da create/update
    # per il tetto di `max_tokens` alla persistenza) escono con loro:
    # nessun chiamante li usava per altro. Il tetto in fase di CHAT resta
    # vivo altrove (claude_runner.CHAT_MAX_TOKENS, che floora ogni
    # richiesta indipendentemente dal valore persistito) -- non e' lo
    # stesso meccanismo e non e' toccato qui.
    #
    # `get_chatbot`/`list_chatbots` restano: `get_chatbot` e' letto da
    # `handle_chat` (system prompt del chatbot attivo) e da `_seed_default_
    # chatbot`; `list_chatbots` alimenta `handle_list_chatbots`, la
    # superficie di compatibilita' rimasta (vedi handlers_chatbots.py).

    def get_chatbot(self, agent_id: str) -> Optional[Chatbot]:
        return self._chatbots.get(agent_id)

    def list_chatbots(self) -> dict[str, dict]:
        return {c.id: asdict(c) for c in self._chatbots.values()}

    def get_chatbot_status(self, agent_id: str) -> str:
        if agent_id in self._running_chatbots:
            return "running"
        if agent_id in self._error_chatbots:
            return "error"
        return "idle"

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    # Autonomous agent scheduling (interval/cron triggers) and reactive
    # state-change dispatch were retired in Slice 5, handed off to the
    # Sentinella (watcher/) as the sole proactive engine. The Sentinella
    # itself is gone too now (fetta E3 Task 7, semaphore included): HIRIS
    # has no proactive/actuating engine left at all, it knows and does not
    # act. `_unschedule_chatbot` used to remain as a defensive no-op-safe
    # cleanup for any job left over from a pre-upgrade scheduler state, but
    # its only callers were `update_chatbot`/`delete_chatbot` -- gone in
    # fetta E4 Task 3 ("un bot solo") with the rest of the CRUD. Orphaned by
    # that removal (caught by the census, not by the brief), it is raccolto
    # qui subito rather than left dangling -- same discipline as
    # `detach_chatbot_id` above. `self._scheduler` itself (APScheduler,
    # started/stopped in `start()`/`stop()`) is untouched: nothing in this
    # task's perimeter adds or removes jobs, and whether the scheduler
    # object itself still earns its keep is a question for whichever future
    # task looks at `start()`/`stop()`, not this one.

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    # fetta E3 Task 12 ("esce il ritratto"): `_build_entity_context` e'
    # uscita -- il filo morto era gia' dichiarato dalla ricognizione (§1,
    # censimento "solo test": tre casi in tests/test_chatbot_engine.py e
    # nessun chiamante di produzione). Slice 5 Task 2 l'aveva gia' scollegata
    # da `_run_chatbot` (l'injection di contesto entita' dedicata al tipo
    # "agent" e' uscita col campo `type` stesso) e l'aveva tenuta solo come
    # helper direttamente testato; qui esce anche quello, coi suoi tre test.
    # `set_entity_cache`/`self._entity_cache` restano vivi come API (chiamati
    # da server.py) ma senza piu' un lettore in questo modulo: il Test Run
    # (Task 2, .superpowers/sdd/task-2-report.md) era l'unico punto che
    # passava `cache=self._entity_cache` a un DispatcherConoscenza. Orfano
    # dichiarato, non raccolto qui -- vedi il report del Task 2.

    # ------------------------------------------------------------------
    # Chatbot run
    # ------------------------------------------------------------------
    # Slice 5 retired the action/rules execution machinery (AZIONI parsing,
    # configured rules, action chains/batches) and the notion of an agent
    # "acting" on its own conclusions, handing that role to the Sentinella
    # (watcher/). The Sentinella is gone too now (fetta E3 Task 7): nothing
    # in HIRIS acts on its own conclusions today. Fetta E4 Task 2 then
    # retired the manual "Test Run" itself (`run_chatbot`/`_run_chatbot`):
    # it called the runner's `chat()` with `agent_id=`/`mode=` kwargs that
    # neither runner accepts and neither has `**kwargs` for -- a TypeError
    # on every real call, masked only because its one test used an
    # AsyncMock (see task-2-report.md). Nothing in HIRIS runs a persona
    # outside interactive chat (`api/handlers_chat.py`) anymore.
