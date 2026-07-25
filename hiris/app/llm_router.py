from __future__ import annotations
import json
import logging
import re
from typing import Any

from .claude_runner import _current_tool_calls, _current_thinking_blocks

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = (
    "Sei un classificatore di entità Home Assistant. "
    "Rispondi SOLO con JSON valido, nessun testo aggiuntivo."
)

_CLASSIFY_ROLES = (
    "energy_meter, solar_production, grid_import, climate_sensor, "
    "presence, lighting, appliance, door_window, electrical, diagnostic, other"
)


def _is_openai_model(model: str) -> bool:
    return bool(re.match(r"^(gpt-|o[1-9])", model))


def _is_openrouter_model(model: str) -> bool:
    """User-facing prefix to route a model through OpenRouter.

    Accepts both 'openrouter:provider/model' and 'openrouter/provider/model'
    so users coming from LiteLLM-style naming feel at home.
    """
    return model.startswith("openrouter:") or model.startswith("openrouter/")


def backend_is_cloud(model: str) -> bool:
    """True se il modello esce verso un provider cloud (claude/openai/openrouter).
    Ollama (e modelli senza prefisso noto) sono locali. 'auto' è trattato come
    cloud per prudenza (le strategie default partono dal cloud)."""
    if model == "auto":
        return True
    if model.startswith("claude-"):
        return True
    if _is_openrouter_model(model):
        return True
    if _is_openai_model(model):
        return True
    return False


_STRATEGY_ORDER = {
    # cost_first: prefer free local (Ollama) → cheap cloud → full cloud
    "cost_first":    ["ollama", "openrouter", "openai", "claude"],
    # quality_first: prefer most capable first, then the dedicated OpenAI slot
    "quality_first": ["claude", "openai", "openrouter", "ollama"],
    # balanced (default): still leads with the most capable model (Claude),
    # but economizes on the fallback chain by preferring OpenRouter (which
    # can hit cheaper/free-tier models) over the dedicated OpenAI slot,
    # before finally falling back to local Ollama. Distinct from
    # quality_first: swaps positions 2 and 3.
    "balanced":      ["claude", "openrouter", "openai", "ollama"],
}

_VALID_BACKEND_NAMES = frozenset({"claude", "openai", "openrouter", "ollama"})
# Backend names that run LOCALLY (no egress). Kept next to _VALID_BACKEND_NAMES
# so any future backend addition is forced to decide its egress class here;
# automatic_allows_sensitive() treats every name NOT in this set as cloud, so a
# forgotten entry fails CLOSED (over-blocks sensitive memory, never leaks it).
_LOCAL_BACKEND_NAMES = frozenset({"ollama"})


def _norm_policy(policy: list[str] | None, strategy: str) -> list[str]:
    """Normalize a backend policy list.

    A non-empty list is filtered to known backend names, preserving order.
    None/empty, OR a non-empty list that filters down to nothing (every name
    unknown), falls back to the strategy's default order (backward-compat) --
    an all-invalid policy must not silently leave the router with an empty
    backend chain.
    """
    if policy:
        filtered = [name for name in policy if name in _VALID_BACKEND_NAMES]
        if filtered:
            return filtered
    return list(_STRATEGY_ORDER[strategy])


class LLMRouter:
    """Routes LLM calls to the appropriate backend.

    Backends: Claude (anthropic), OpenAI cloud, OpenRouter proxy, Ollama local.

    strategy controls the default backend preference order when model="auto":
      - "quality_first": Claude → OpenAI → OpenRouter → Ollama
      - "balanced": Claude → OpenRouter → OpenAI → Ollama
      - "cost_first": Ollama → OpenRouter → OpenAI → Claude
    Fallback: if the primary backend raises an exception and model="auto",
    the next backend in the policy chain is tried automatically.

    Two independent ordered policies select the backend chain when
    model="auto", picked via the `mode` kwarg on chat/chat_stream/
    run_with_actions ("chat" → chat_policy, else → automatic_policy).
    If a policy is not supplied (None/empty), it derives from
    _STRATEGY_ORDER[strategy] — unchanged behavior for existing callers.

    Explicit model routing (when model != "auto"):
      - 'claude-*'                  → Claude runner
      - 'gpt-*' or 'o[1-9]'         → OpenAI runner
      - 'openrouter:*' or 'openrouter/*' → OpenRouter runner (prefix stripped)
      - anything else               → Ollama runner
    """

    def __init__(
        self,
        claude: Any = None,
        openai: Any = None,
        openrouter: Any = None,
        ollama: Any = None,
        strategy: str = "balanced",
        automatic_policy: list[str] | None = None,
        chat_policy: list[str] | None = None,
    ) -> None:
        self._claude = claude
        self._openai = openai
        self._openrouter = openrouter
        self._ollama = ollama
        self._strategy = strategy if strategy in _STRATEGY_ORDER else "balanced"
        self._all = [r for r in [claude, openai, openrouter, ollama] if r is not None]
        # Two ordered backend policies (proactive/agents vs interactive chat).
        # Each falls back to the strategy's default order when not provided.
        self._automatic_policy = _norm_policy(automatic_policy, self._strategy)
        self._chat_policy = _norm_policy(chat_policy, self._strategy)

    def automatic_allows_sensitive(self) -> bool:
        """True only if the whole *available* automatic chain is local.

        Rationale: a prompt composed for a local primary backend could still
        fall back to a cloud backend if that primary is unreachable (see the
        automatic-mode retry loop in chat()/run_with_actions()). So sensitive
        content is safe to include only when NO cloud backend is reachable
        anywhere in the automatic chain -- the chain must be non-empty and
        every backend registered in it (non-None) must be local.

        Note: backend_is_cloud() classifies *model strings* (e.g.
        "claude-sonnet-4-6", "gpt-4o", "openrouter:x/y") by prefix, not the
        bare backend keys ("claude", "openai", "openrouter", "ollama") used
        in the automatic policy chain -- calling it directly on those keys
        would misclassify every cloud backend as local (verified: it only
        recognizes "auto" and prefixed model strings). So this method
        classifies by backend-key membership instead: every
        _VALID_BACKEND_NAMES entry is a cloud provider except "ollama",
        mirroring backend_is_cloud's own claude/openai/openrouter-are-cloud,
        ollama-is-local convention and this module's production wiring
        (server.py always constructs the "openai"/"openrouter"/"claude"
        runners as cloud and "ollama" as local).

        Pure/deterministic, no I/O. Never raises.
        """
        try:
            bmap = self._backend_map()
            available = [name for name in self._automatic_policy if bmap.get(name) is not None]
            return bool(available) and all(name in _LOCAL_BACKEND_NAMES for name in available)
        except Exception:
            return False

    def _backend_map(self) -> dict[str, Any]:
        return {
            "claude": self._claude,
            "openai": self._openai,
            "openrouter": self._openrouter,
            "ollama": self._ollama,
        }

    def _ordered_backends(self, mode: str = "automatic") -> list[Any]:
        """Return available backends in mode-policy priority order.

        mode="chat" uses chat_policy (interactive chat); anything else
        (default "automatic") uses automatic_policy (proactive/agents).
        """
        order = self._chat_policy if mode == "chat" else self._automatic_policy
        bmap = self._backend_map()
        return [bmap[name] for name in order if bmap[name] is not None]

    def _route(self, model: str) -> Any:
        if _is_openrouter_model(model):
            return self._openrouter
        if model.startswith("claude-"):
            return self._claude
        if _is_openai_model(model):
            return self._openai
        return self._ollama

    # ------------------------------------------------------------------
    # LLM interface (mirrors ClaudeRunner)
    # ------------------------------------------------------------------

    async def chat(self, **kwargs) -> str:
        # mode selects the auto-routing policy; popped so it is never
        # forwarded to the underlying runner (runners don't accept it).
        mode = kwargs.pop("mode", "chat")
        model = kwargs.get("model", "auto")
        if model != "auto":
            runner = self._route(model)
            if runner is None:
                return "Nessun provider AI configurato per questo modello."
            return await runner.chat(**kwargs)
        # auto: try backends in mode-policy order with fallback
        for runner in self._ordered_backends(mode):
            try:
                return await runner.chat(**kwargs)
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
        return "Tutti i provider AI non disponibili. Riprova tra poco."

    async def chat_stream(self, **kwargs):
        mode = kwargs.pop("mode", "chat")
        model = kwargs.get("model", "auto")
        if model == "auto":
            # no fallback in streaming (as today): just the first pick
            backends = self._ordered_backends(mode)
            runner = backends[0] if backends else None
        else:
            runner = self._route(model)
        if runner is None:
            yield f'data: {json.dumps({"type": "error", "message": "Provider AI non configurato"})}\n\n'
            return
        async for chunk in runner.chat_stream(**kwargs):
            yield chunk

    async def run_with_actions(self, **kwargs):
        # Slice 4 backlog fix: real runners (claude_runner/openai_compat_runner)
        # return a 2-tuple (clean_text, structured), and the sole real caller
        # (server.py's `_llm_reason`, via `out = await runner.run_with_actions(...)`
        # then `out[0] if isinstance(out, tuple) else out`) tolerates either a
        # tuple or a bare string -- but both fallback returns below still use
        # the 2-tuple shape for consistency with the real runners, not the
        # old 3-tuple.
        mode = kwargs.pop("mode", "automatic")
        model = kwargs.get("model", "auto")
        if model != "auto":
            runner = self._route(model)
            if runner is None:
                return "Nessun provider AI configurato per questo modello.", {}
            return await runner.run_with_actions(**kwargs)
        for runner in self._ordered_backends(mode):
            try:
                return await runner.run_with_actions(**kwargs)
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
        return "Tutti i provider AI non disponibili. Riprova tra poco.", {}

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        runner = self._claude or self._openai or self._ollama
        if runner is None:
            return ""
        return await runner.simple_chat(messages, system=system)

    # ------------------------------------------------------------------
    # Usage (aggregated across all runners)
    # ------------------------------------------------------------------

    @property
    def last_tool_calls(self) -> list:
        """Tool calls from the call that just ran through THIS asyncio Task.

        Proxies straight to the shared per-call ContextVar (see
        claude_runner.py's module comment, review A/#3) instead of scanning
        registered backends for "whichever has a non-empty list" — the old
        scan could return a completely different caller's tool calls than
        the one that actually served this request, since every backend
        shares the router and any of them could have run moments earlier on
        another Task.
        """
        val = _current_tool_calls.get()
        return val if val is not None else []

    @property
    def last_thinking_blocks(self) -> list:
        """Extended-thinking blocks from the call that just ran through THIS
        asyncio Task. See last_tool_calls above — same ContextVar-backed
        isolation, shared with ClaudeRunner/OpenAICompatRunner."""
        val = _current_thinking_blocks.get()
        return val if val is not None else []

    @property
    def total_input_tokens(self) -> int:
        return sum(getattr(r, "total_input_tokens", 0) for r in self._all)

    @property
    def total_output_tokens(self) -> int:
        return sum(getattr(r, "total_output_tokens", 0) for r in self._all)

    @property
    def total_requests(self) -> int:
        return sum(getattr(r, "total_requests", 0) for r in self._all)

    @property
    def total_cost_usd(self) -> float:
        return sum(getattr(r, "total_cost_usd", 0.0) for r in self._all)

    @property
    def total_rate_limit_errors(self) -> int:
        return sum(getattr(r, "total_rate_limit_errors", 0) for r in self._all)

    @property
    def usage_last_reset(self) -> str:
        resets = [getattr(r, "usage_last_reset", "") for r in self._all]
        return min((s for s in resets if s), default="")

    def get_agent_usage(self, agent_id: str) -> dict:
        result = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }
        for r in self._all:
            u = r.get_agent_usage(agent_id)
            result["input_tokens"] += u.get("input_tokens", 0)
            result["output_tokens"] += u.get("output_tokens", 0)
            result["requests"] += u.get("requests", 0)
            result["cost_usd"] += u.get("cost_usd", 0.0)
            result["tokens_today"] += u.get("tokens_today", 0)
            run_at = u.get("last_run")
            if run_at and (not result["last_run"] or run_at > result["last_run"]):
                result["last_run"] = run_at
        return result

    def reset_agent_usage(self, agent_id: str) -> None:
        for r in self._all:
            r.reset_agent_usage(agent_id)

    def reset_usage(self) -> None:
        for r in self._all:
            r.reset_usage()

    # ------------------------------------------------------------------
    # Entity classification (prefers Ollama for cheap inference)
    # ------------------------------------------------------------------

    async def classify_entities(self, entities: list[dict]) -> dict[str, dict]:
        if not entities:
            return {}

        batch_text = "\n".join(
            f"- {e['id']}: state={e.get('state', 'unknown')}, "
            f"name={e.get('name', '')}, unit={e.get('unit', '')}"
            for e in entities
        )
        user_msg = (
            f"Classifica queste entità HA. Restituisci JSON:\n"
            f'{{\"entity_id\": {{\"role\": \"...\", \"label\": \"...\", \"confidence\": 0.0}}}}\n\n'
            f"Ruoli validi: {_CLASSIFY_ROLES}\n\n"
            f"Entità:\n{batch_text}\n\n"
            f"Rispondi con SOLO il JSON."
        )
        messages = [{"role": "user", "content": user_msg}]

        # Ollama is cheapest; fall back to primary runner
        runner = self._ollama or self._openrouter or self._claude or self._openai
        if runner is None:
            return {}
        raw = await runner.simple_chat(messages, system=_CLASSIFY_SYSTEM)
        # Empty reply = backend down / circuit open. Return early instead of
        # routing it through the JSON parser, which would log a "could not parse"
        # warning on every call and flood the log when a backend is unreachable.
        if not raw or not raw.strip():
            return {}
        return _parse_classify_response(raw)


_VALID_ROLES = frozenset([
    "energy_meter", "solar_production", "grid_import", "climate_sensor",
    "presence", "lighting", "appliance", "door_window", "electrical",
    "diagnostic", "other", "unknown",
])


def _parse_classify_response(raw: str) -> dict[str, dict]:
    raw = raw[:100_000]
    data: dict | None = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        for m in reversed(list(re.finditer(r'\{', raw))):
            try:
                data = json.loads(raw[m.start():])
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(data, dict):
        logger.warning("classify_entities: could not parse JSON from LLM response: %.200s", raw)
        return {}
    result: dict[str, dict] = {}
    for eid, meta in list(data.items())[:500]:
        if not isinstance(meta, dict):
            continue
        role = str(meta.get("role", "other"))
        if role not in _VALID_ROLES:
            role = "other"
        label = str(meta.get("label", ""))[:128] or eid.split(".")[-1]
        try:
            confidence = float(meta.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.8
        result[eid] = {"role": role, "label": label, "confidence": confidence}
    return result
