import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
import anthropic
from .tools.ha_tools import (
    TOOL_DEF as HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
)
from .tools.energy_tools import TOOL_DEF as ENERGY_TOOL
from .tools.weather_tools import TOOL_DEF as WEATHER_TOOL
from .tools.notify_tools import TOOL_DEF as NOTIFY_TOOL
from .tools.automation_tools import (
    GET_AUTOMATIONS_TOOL_DEF,
    TRIGGER_TOOL_DEF,
    TOGGLE_TOOL_DEF,
)
from .tools.task_tools import (
    CREATE_TASK_TOOL_DEF, LIST_TASKS_TOOL_DEF, CANCEL_TASK_TOOL_DEF,
)
from .tools.calendar_tools import (
    GET_CALENDAR_EVENTS_TOOL_DEF,
    SET_INPUT_HELPER_TOOL_DEF,
    CREATE_CALENDAR_EVENT_TOOL_DEF,
)
from .tools.http_tools import HTTP_REQUEST_TOOL_DEF
from .tools.memory_tools import (
    RECALL_MEMORY_TOOL_DEF,
    SAVE_MEMORY_TOOL_DEF,
)
from .tools.dispatcher import ToolDispatcher

logger = logging.getLogger(__name__)

# ── Base system prompt ─────────────────────────────────────────────────────
# Always injected at runtime BEFORE any agent-specific instructions.
# Agents configure WHAT to do and HOW to behave; this layer defines the tools
# available and the invariant anti-hallucination rules.
BASE_SYSTEM_PROMPT = (
    "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n\n"
    "## Strumenti disponibili\n"
    "- get_home_status(): panoramica compatta di tutti i dispositivi. Usalo come prima chiamata.\n"
    "- get_entities_on(): tutti i dispositivi attualmente accesi.\n"
    "- get_entities_by_domain(domain): entità di un dominio (es. 'light', 'sensor').\n"
    "- get_entity_states(ids): stato attuale e attributi di entità specifiche.\n"
    "  Per i termostati (climate.*) restituisce temperatura attuale e setpoint.\n"
    "- get_area_entities(): aree/stanze e i dispositivi associati.\n"
    "- get_ha_automations(): elenco automazioni HA.\n"
    "- trigger_automation(id): esegue manualmente un'automazione.\n"
    "- toggle_automation(id, enabled): attiva o disattiva un'automazione.\n"
    "- get_energy_history(days): storico consumi energetici.\n"
    "- get_weather_forecast(hours): previsioni meteo.\n"
    "- call_ha_service(domain, service, data): controlla dispositivi.\n"
    "- send_notification(message, channel): invia notifiche (ha_push, apprise, retropanel).\n"
    "- create_calendar_event(calendar_entity, summary, event_type, ...): crea un evento nel calendario HA.\n"
    "- create_task(label, trigger, actions): pianifica un'azione futura.\n"
    "- list_tasks(agent_id, status): elenca i task pianificati.\n"
    "- cancel_task(task_id): annulla un task pianificato.\n"
    "- get_calendar_events(hours, calendar_entity?): eventi calendario HA nelle prossime N ore.\n"
    "- set_input_helper(entity_id, value): imposta un input helper HA (boolean/number/text/select).\n"
    "- http_request(url, method?, headers?, body?): chiama un'API esterna o un dispositivo locale"
    " pre-approvato (solo se configurato nell'agente).\n"
    "- recall_memory(query, k?, tags?): cerca nella memoria persistente dell'agente ricordi rilevanti"
    " da sessioni precedenti.\n"
    "- save_memory(content, tags?): salva un'informazione importante in memoria per sessioni future"
    " (solo per agenti chat).\n\n"
    "## Regole fondamentali\n"
    "- Usa SEMPRE gli strumenti per dati sulla casa — non inventare stati, valori o entità.\n"
    "- Non dichiarare azioni mai eseguite: se non hai chiamato il tool, non dire di averlo fatto.\n"
    "- Se hai chiamato uno strumento con successo, l'azione è reale:\n"
    "  non aggiungere disclaimers come 'ho inventato', 'ho simulato' o 'non ho realmente eseguito'.\n"
    "- Rispondi nella lingua dell'utente."
)

CALL_SERVICE_TOOL_DEF = {
    "name": "call_ha_service",
    "description": "Call a Home Assistant service to control devices (light, switch, climate, etc.).",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Service domain, e.g. 'light', 'switch'"},
            "service": {"type": "string", "description": "Service name, e.g. 'turn_on', 'turn_off'"},
            "data": {"type": "object", "description": "Service call data, e.g. {entity_id: 'light.living'}"},
        },
        "required": ["domain", "service"],
    },
}

ALL_TOOL_DEFS = [
    HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
    ENERGY_TOOL,
    WEATHER_TOOL,
    NOTIFY_TOOL,
    GET_AUTOMATIONS_TOOL_DEF,
    TRIGGER_TOOL_DEF,
    TOGGLE_TOOL_DEF,
    CALL_SERVICE_TOOL_DEF,
    CREATE_TASK_TOOL_DEF,
    LIST_TASKS_TOOL_DEF,
    CANCEL_TASK_TOOL_DEF,
    GET_CALENDAR_EVENTS_TOOL_DEF,
    SET_INPUT_HELPER_TOOL_DEF,
    CREATE_CALENDAR_EVENT_TOOL_DEF,
    HTTP_REQUEST_TOOL_DEF,
    RECALL_MEMORY_TOOL_DEF,
    SAVE_MEMORY_TOOL_DEF,
]

# Tools available to non-chat agents in evaluation mode.
# Excludes direct-execution tools (send_notification, call_ha_service,
# trigger_automation, toggle_automation, http_request) to prevent prompt
# injection from HA entity state from triggering real-world actions.
EVALUATION_ONLY_TOOLS = frozenset({
    "get_entity_states", "get_area_entities", "get_home_status",
    "get_entities_on", "get_entities_by_domain",
    "get_energy_history", "get_weather_forecast",
    "get_ha_automations", "get_calendar_events",
    "create_task", "list_tasks", "cancel_task",
    "recall_memory",  # read-only — safe for non-chat agents
    # save_memory excluded: write risk in reactive agents (prompt injection via HA state)
})

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_TOOL_ITERATIONS = 10
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]

AUTO_MODEL_MAP: dict[str, str] = {
    "chat": "claude-sonnet-4-6",
    "agent": "claude-haiku-4-5-20251001",
    # legacy type names kept for migration compatibility
    "monitor": "claude-haiku-4-5-20251001",
    "reactive": "claude-haiku-4-5-20251001",
    "preventive": "claude-haiku-4-5-20251001",
}

from .backends.pricing import PRICING as _PRICING


def resolve_model(model: str, agent_type: str) -> str:
    if model == "auto":
        return AUTO_MODEL_MAP.get(agent_type, MODEL)
    return model

RESTRICT_PROMPT = (
    "Sei HIRIS, assistente per la smart home. "
    "Rispondi SOLO a domande relative alla casa, domotica, energia, clima, sicurezza. "
    "Per qualsiasi altro argomento, rispondi educatamente che non puoi aiutare su quel tema."
)

REQUIRE_CONFIRMATION_PROMPT = (
    "Prima di chiamare call_ha_service per eseguire un'azione reale, "
    "descrivi l'azione che intendi eseguire e chiedi conferma con il formato: "
    "'Proposta: [descrizione azione]. Confermi? (sì/no)'. "
    "Esegui call_ha_service SOLO se il messaggio più recente dell'utente "
    "contiene 'sì', 'si', 'ok', 'conferma' o 'yes' (case insensitive)."
)


def _parse_structured_output(text: str) -> tuple[str, dict]:
    """Parse structured output block from the TRAILING section of a Claude response.

    Two-pass strategy:
    1. Locate the AZIONI: marker (last occurrence) and collect all lines after it.
    2. Scan bottom-up from the marker (or end-of-text) for VALUTAZIONE / NOTIFICA / PARAM.
       Stop at the first non-blank, non-marker line to avoid consuming mid-text content.

    Returns:
        Tuple of (clean_text, structured) where structured contains:
        - valutazione: str | None
        - notifica: str | None
        - params: dict[str, str]  — from ``PARAM key: value`` lines
        - azioni: list[str]       — raw action command lines (one per list entry)
    """
    structured: dict = {
        "valutazione": None,
        "notifica": None,
        "params": {},
        "azioni": [],
    }
    lines = text.splitlines()

    # Pass 1: locate the AZIONI: marker (last occurrence)
    azioni_marker_idx: int | None = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("AZIONI:"):
            azioni_marker_idx = i
            break

    if azioni_marker_idx is not None:
        marker_stripped = lines[azioni_marker_idx].strip()
        inline = marker_stripped[len("AZIONI:"):].strip()
        azioni_lines: list[str] = []
        if inline:
            azioni_lines.append(inline)
        for j in range(azioni_marker_idx + 1, len(lines)):
            cmd = lines[j].strip()
            if cmd:
                azioni_lines.append(cmd)
        structured["azioni"] = azioni_lines

    # Pass 2: scan bottom-up for VALUTAZIONE / NOTIFICA / PARAM
    scan_end = azioni_marker_idx if azioni_marker_idx is not None else len(lines)
    cut = scan_end

    for i in range(scan_end - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("VALUTAZIONE:"):
            structured["valutazione"] = stripped[len("VALUTAZIONE:"):].strip()
            cut = i
        elif stripped.startswith("NOTIFICA:"):
            structured["notifica"] = stripped[len("NOTIFICA:"):].strip()
            cut = i
        elif stripped.startswith("PARAM ") and ":" in stripped:
            rest = stripped[len("PARAM "):].strip()
            colon_pos = rest.find(":")
            if colon_pos > 0:
                key = rest[:colon_pos].strip()
                value = rest[colon_pos + 1:].strip()
                structured["params"][key] = value
            cut = i
        elif not stripped:
            cut = i  # blank lines in trailing block are consumable
        else:
            break  # real content reached — stop

    clean_text = "\n".join(lines[:cut]).rstrip()
    return clean_text, structured


class ClaudeRunner:
    def __init__(
        self,
        api_key: str,
        dispatcher: ToolDispatcher,
        usage_path: str = "",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._dispatcher = dispatcher
        self._usage_path = usage_path
        self.last_tool_calls: list[dict] = []
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_requests: int = 0
        self.total_cost_usd: float = 0.0
        self.total_rate_limit_errors: int = 0
        self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
        self._per_agent_usage: dict[str, dict] = {}
        self._load_usage()

    def set_task_engine(self, engine: Any) -> None:
        self._dispatcher.set_task_engine(engine)

    def _load_usage(self) -> None:
        if not self._usage_path or not os.path.exists(self._usage_path):
            return
        try:
            with open(self._usage_path, encoding="utf-8") as f:
                data = json.load(f)
            self.total_input_tokens = data.get("total_input_tokens", 0)
            self.total_output_tokens = data.get("total_output_tokens", 0)
            self.total_requests = data.get("total_requests", 0)
            self.usage_last_reset = data.get("last_reset", self.usage_last_reset)
            self.total_cost_usd = data.get("total_cost_usd", 0.0)
            self.total_rate_limit_errors = data.get("total_rate_limit_errors", 0)
            self._per_agent_usage = data.get("per_agent", {})
        except Exception as exc:
            logger.warning("Failed to load usage from %s: %s", self._usage_path, exc)

    def _save_usage(self) -> None:
        if not self._usage_path:
            return
        data = {
            "schema_version": 1,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_requests": self.total_requests,
            "last_reset": self.usage_last_reset,
            "total_cost_usd": self.total_cost_usd,
            "total_rate_limit_errors": self.total_rate_limit_errors,
            "per_agent": dict(self._per_agent_usage),
        }
        tmp = self._usage_path + ".tmp"

        def _write() -> None:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp, self._usage_path)
            except Exception as exc:
                logger.error("Failed to save usage to %s: %s", self._usage_path, exc)

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _write)
        except RuntimeError:
            _write()

    def reset_usage(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.total_cost_usd = 0.0
        self.total_rate_limit_errors = 0
        self.usage_last_reset = datetime.now(timezone.utc).isoformat()
        self._save_usage()

    def _ensure_today_reset(self, pau: dict) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if pau.get("tokens_today_date", "") != today:
            pau["tokens_today"] = 0
            pau["tokens_today_date"] = today

    def get_agent_usage(self, agent_id: str) -> dict:
        """Return usage stats for a specific agent. Returns zero-filled dict if not found."""
        pau = self._per_agent_usage.get(agent_id)
        if pau is None:
            return {
                "input_tokens": 0, "output_tokens": 0,
                "requests": 0, "cost_usd": 0.0, "last_run": None,
                "tokens_today": 0, "tokens_today_date": "",
            }
        self._ensure_today_reset(pau)
        return dict(pau)

    def reset_agent_usage(self, agent_id: str) -> None:
        """Reset usage counters for a specific agent."""
        self._per_agent_usage[agent_id] = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }
        self._save_usage()

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Single API call with no tools and no retry loop — for classification tasks."""
        kwargs: dict = {"model": MODEL, "max_tokens": 1024, "messages": messages}
        if system:
            kwargs["system"] = system
        try:
            response = await self._client.messages.create(**kwargs)
            return next((b.text for b in response.content if b.type == "text"), "")
        except Exception as exc:
            logger.error("simple_chat failed: %s", exc)
            return ""

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
        visible_entity_ids: Optional[frozenset] = None,
        response_mode: str = "auto",
    ) -> str:
        if agent_id:
            if agent_id not in self._per_agent_usage:
                self._per_agent_usage[agent_id] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "requests": 0, "cost_usd": 0.0, "last_run": None,
                    "tokens_today": 0, "tokens_today_date": "",
                }
            self._per_agent_usage[agent_id]["requests"] += 1
            self._per_agent_usage[agent_id]["last_run"] = datetime.now(timezone.utc).isoformat()
        self.last_tool_calls = []
        # ── System prompt blocks with prompt caching ─────────────────────────
        # Block 1 — BASE (always cached): tool list + anti-hallucination rules.
        # Block 2 — agent prompt (cached): strategic_context + system_prompt,
        #           stable per agent across queries → reused from cache.
        # Block 3 — context_str (NOT cached): SemanticContextMap output,
        #           query-dependent → different content each request → no reuse.
        system_blocks: list[dict] = [
            {"type": "text", "text": BASE_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
        ]
        if system_prompt:
            system_blocks.append({"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}})
        if context_str:
            system_blocks.append({"type": "text", "text": context_str})
        if restrict_to_home:
            system_blocks.append({"type": "text", "text": RESTRICT_PROMPT})
        if require_confirmation:
            system_blocks.append({"type": "text", "text": REQUIRE_CONFIRMATION_PROMPT})
        if response_mode == "compact":
            system_blocks.append({"type": "text", "text": "Rispondi in modo conciso, massimo 2-3 frasi."})
        elif response_mode == "minimal":
            system_blocks.append({"type": "text", "text": (
                "Rispondi SOLO in formato chiave: valore, una riga per dato. "
                "Esempio:\nStato: acceso\nTemperatura: 21°C"
            )})
        effective_model = resolve_model(model, agent_type)
        tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
        if allowed_endpoints is None:
            tools = [t for t in tools if t["name"] != "http_request"]
        if not self._dispatcher.has_memory:
            tools = [t for t in tools if t["name"] not in ("recall_memory", "save_memory")]
        hist = list(conversation_history or [])
        messages: list[dict] = []
        if hist:
            for msg in hist[:-1]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            last = hist[-1]
            content = last["content"]
            if isinstance(content, str):
                cached_content = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
            elif isinstance(content, list) and content:
                # Preserve structured blocks; attach cache_control to the last block only
                cached_content = content[:-1] + [{**content[-1], "cache_control": {"type": "ephemeral"}}]
            else:
                cached_content = content  # empty list or unexpected type: skip caching
            messages.append({"role": last["role"], "content": cached_content})
        messages.append({"role": "user", "content": user_message})
        self.total_requests += 1  # one per user exchange, regardless of tool iterations

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                response = await self._call_api(
                    model=effective_model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    tools=tools,
                    messages=messages,
                )
            except anthropic.APIError as exc:
                logger.error("Claude API error: %s", exc)
                return "Errore temporaneo del servizio AI. Riprova tra poco."

            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            self.total_input_tokens += inp + cache_creation + cache_read
            self.total_output_tokens += out
            prices = _PRICING.get(effective_model, _PRICING["_default"])
            cost = (
                inp * prices["input"]
                + cache_creation * prices.get("cache_write", prices["input"] * 1.25)
                + cache_read * prices.get("cache_read", prices["input"] * 0.1)
                + out * prices["output"]
            ) / 1_000_000
            self.total_cost_usd += cost
            if agent_id and agent_id in self._per_agent_usage:
                pau = self._per_agent_usage[agent_id]
                pau["input_tokens"] += inp + cache_creation + cache_read
                pau["output_tokens"] += out
                pau["cost_usd"] += cost
                self._ensure_today_reset(pau)
                pau["tokens_today"] = pau.get("tokens_today", 0) + inp + cache_creation + cache_read + out
            self._save_usage()

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._dispatcher.dispatch(
                            block.name, block.input,
                            allowed_entities=allowed_entities,
                            allowed_services=allowed_services,
                            allowed_endpoints=allowed_endpoints,
                            agent_id=agent_id,
                            visible_entity_ids=visible_entity_ids,
                        )
                        self.last_tool_calls.append({"tool": block.name, "input": block.input})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks) if text_blocks else f"Stopped: {response.stop_reason}"

        return "Max tool iterations reached."

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
        visible_entity_ids=None,
        response_mode: str = "auto",
    ):
        """Async generator yielding SSE-formatted lines for the chat response.

        Phase 1 implementation: awaits the full chat() response, then slices it
        into 80-char chunks for SSE framing. The client sees all tokens arrive
        after the full Claude round-trip (same latency as non-streaming).
        Phase 2 will replace this with true Anthropic streaming API calls.

        Yields lines in the form:
          'data: {"type": "token", "text": "<chunk>"}\\n\\n'
          'data: {"type": "done", "agent_id": "<id>", "tool_calls": [...]}\\n\\n'
          'data: {"type": "error", "message": "<msg>"}\\n\\n'
        """
        import json as _json
        try:
            result = await self.chat(
                user_message=user_message,
                system_prompt=system_prompt,
                context_str=context_str,
                allowed_tools=allowed_tools,
                conversation_history=conversation_history,
                allowed_entities=allowed_entities,
                allowed_services=allowed_services,
                allowed_endpoints=allowed_endpoints,
                model=model,
                max_tokens=max_tokens,
                agent_type=agent_type,
                restrict_to_home=restrict_to_home,
                require_confirmation=require_confirmation,
                agent_id=agent_id,
                visible_entity_ids=visible_entity_ids,
                response_mode=response_mode,
            )
        except Exception as exc:
            yield f'data: {_json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        chunk_size = 80
        for i in range(0, len(result), chunk_size):
            yield f'data: {_json.dumps({"type": "token", "text": result[i:i + chunk_size]})}\n\n'

        tool_calls = self.last_tool_calls if isinstance(self.last_tool_calls, list) else []
        yield f'data: {_json.dumps({"type": "done", "agent_id": agent_id, "tool_calls": tool_calls})}\n\n'

    async def run_with_actions(
        self,
        user_message: str,
        system_prompt: str,
        action_mode: str = "automatic",
        states: Optional[list[str]] = None,
        rules: Optional[list[dict]] = None,
        allowed_tools: Optional[list[str]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "agent",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
        response_mode: str = "auto",
    ) -> tuple[str, dict]:
        """Run an autonomous agent evaluation — restrict tools, inject structured-output instructions.

        Claude gathers data using read-only tools, then produces a structured trailing
        block (VALUTAZIONE / NOTIFICA / PARAM / AZIONI) that the caller parses and acts on.

        Args:
            user_message: Trigger message (may contain event context or a cron prompt).
            system_prompt: Agent-specific instructions.
            action_mode: ``"automatic"`` — LLM writes AZIONI block; ``"configured"`` — user-defined rules.
            states: Allowed VALUTAZIONE values. Defaults to [OK, ATTENZIONE, ANOMALIA].
            rules: Pre-configured action rules (used only by caller; included here for completeness).
            allowed_tools: Whitelist of tool names, or None for all evaluation tools.
            allowed_entities: Entity glob patterns allowed for this agent.
            allowed_services: Service patterns allowed for this agent.
            allowed_endpoints: HTTP endpoint whitelist.
            model: Model ID or ``"auto"``.
            max_tokens: Response token budget.
            agent_type: Used for model auto-resolution (``"agent"`` maps to Haiku).
            restrict_to_home: Inject home-topic restriction prompt.
            require_confirmation: Not used for agents; present for API symmetry.
            agent_id: Agent ID for per-agent usage tracking.
            response_mode: ``"minimal"`` for terse motivazione, ``"auto"`` for standard.

        Returns:
            Tuple of ``(clean_text, structured)`` where ``structured`` contains:
            ``valutazione``, ``notifica``, ``params``, ``azioni``.
        """
        # Restrict to evaluation-only tools — Claude may read HA state and schedule
        # tasks but cannot directly call action services (prevents prompt-injection attacks).
        eval_tools = list(EVALUATION_ONLY_TOOLS)
        if allowed_tools:
            eval_tools = [t for t in eval_tools if t in allowed_tools]

        _states = states if states else ["OK", "ATTENZIONE", "ANOMALIA"]
        states_str = "|".join(_states)
        motivazione = "1 riga sintetica" if response_mode == "minimal" else "1-2 righe sintetiche"

        if action_mode == "automatic":
            eval_instruction = (
                "\n\n---\n"
                "ISTRUZIONI DI RISPOSTA:\n"
                "Analizza il contesto e concludi la risposta con queste righe esatte:\n\n"
                f"VALUTAZIONE: {states_str}\n"
                f"NOTIFICA: [messaggio da inviare — {motivazione}]\n"
                "[PARAM nome: valore  ← aggiungi una riga per ogni parametro dinamico necessario]\n"
                "AZIONI:\n"
                "[una azione per riga — formato: comando entità [valore]]\n\n"
                "Comandi disponibili:\n"
                "  turn_on <entity_id>\n"
                "  turn_off <entity_id>\n"
                "  set_value <entity_id> <value>\n"
                "  wait <minuti>\n"
                "  notify <channel> <message>\n"
                "  call_service <domain.service> <entity_id> [key=value ...]\n\n"
                "Se non sono necessarie azioni ometti il blocco AZIONI: completamente."
            )
        else:  # configured
            eval_instruction = (
                "\n\n---\n"
                "ISTRUZIONI DI RISPOSTA:\n"
                "Analizza il contesto e concludi la risposta con queste righe esatte:\n\n"
                f"VALUTAZIONE: {states_str}\n"
                f"NOTIFICA: [messaggio da inviare — {motivazione}]\n"
                "[PARAM nome: valore  ← aggiungi una riga per ogni parametro dinamico necessario]"
            )

        augmented_prompt = system_prompt + eval_instruction

        raw_result = await self.chat(
            user_message=user_message,
            system_prompt=augmented_prompt,
            allowed_tools=eval_tools,
            allowed_entities=allowed_entities,
            allowed_services=allowed_services,
            allowed_endpoints=allowed_endpoints,
            model=model,
            max_tokens=max_tokens,
            agent_type=agent_type,
            restrict_to_home=restrict_to_home,
            require_confirmation=require_confirmation,
            agent_id=agent_id,
            response_mode=response_mode,
        )
        clean_text, structured = _parse_structured_output(raw_result)
        return clean_text, structured

    async def _call_api(self, **kwargs) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._client.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                if exc.status_code in (429, 529) and attempt < MAX_RETRIES:
                    self.total_rate_limit_errors += 1
                    delay = RETRY_DELAYS[attempt]
                    logger.warning("Rate limit (attempt %d/%d), retry in %ds", attempt + 1, MAX_RETRIES, delay)
                    await asyncio.sleep(delay)
                else:
                    raise

