from __future__ import annotations
import json
import logging
import re
from typing import Any

from .claude_runner import (
    RunnerBackendError,
    _current_tool_calls,
    _current_thinking_blocks,
    _current_pseudonym_map,
)

logger = logging.getLogger(__name__)


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
    model="auto", picked via the `mode` kwarg on chat/chat_stream
    ("chat" → chat_policy, else → automatic_policy).
    If a policy is not supplied (None/empty), it derives from
    _STRATEGY_ORDER[strategy] — unchanged behavior for existing callers.
    When the caller instead passes `model_chain` (the boot-time reconciled
    chain built by model_activation.reconcile_chain — see server.py), that
    single list is used as the unified chain for BOTH chat_policy and
    automatic_policy, superseding the two-policy split above.

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
        model_chain: list[str] | None = None,
    ) -> None:
        self._claude = claude
        self._openai = openai
        self._openrouter = openrouter
        self._ollama = ollama
        self._strategy = strategy if strategy in _STRATEGY_ORDER else "balanced"
        self._all = [r for r in [claude, openai, openrouter, ollama] if r is not None]
        # Two ordered backend policies (proactive/agents vs interactive chat).
        # Each falls back to the strategy's default order when not provided.
        # SP-2: una catena unica. Se model_chain è fornito, sostituisce ENTRAMBE
        # le policy (chat + automatic) con lo stesso ordine, così _ordered_backends
        # e automatic_allows_sensitive restano corretti invariati. Se None,
        # comportamento legacy (due policy indipendenti).
        if model_chain:
            chain = _norm_policy(model_chain, self._strategy)
            self._automatic_policy = list(chain)
            self._chat_policy = list(chain)
        else:
            self._automatic_policy = _norm_policy(automatic_policy, self._strategy)
            self._chat_policy = _norm_policy(chat_policy, self._strategy)

    def automatic_allows_sensitive(self) -> bool:
        """True only if the whole *available* automatic chain is local.

        Rationale: a prompt composed for a local primary backend could still
        fall back to a cloud backend if that primary is unreachable (see the
        automatic-mode retry loop in chat()). So sensitive
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
        last_friendly: str | None = None
        for runner in self._ordered_backends(mode):
            try:
                return await runner.chat(**kwargs)
            except RunnerBackendError as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
                last_friendly = exc.friendly_message
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
        return last_friendly or "Tutti i provider AI non disponibili. Riprova tra poco."

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

    # fetta E3 Task 8: `run_with_actions` e' uscito. Il "sole real caller" che
    # il commento qui sopra citava (server.py's `_llm_reason`) era la
    # Sentinella, uscita per intero al Task 7 di questa fetta -- senza di lei
    # nessun chiamante di produzione arrivava piu' fin qui.

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Nessun provider configurato NON e' una risposta vuota del modello.

        Prima si tornava "", che il chiamante non puo' distinguere da un
        modello che ha davvero taciuto: il guasto veniva trattato come
        risposta valida. Si risponde con lo stesso messaggio esplicito gia'
        usato da `chat` in questo file. Quando un runner
        c'e', la sua risposta passa cosi' com'e' -- anche vuota, perche' li' e'
        davvero il modello ad aver taciuto.
        """
        runner = self._claude or self._openai or self._ollama
        if runner is None:
            logger.warning("simple_chat: nessun provider AI configurato")
            return "Nessun provider AI configurato."
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
    def last_pseudonym_map(self) -> dict:
        """Per-request pseudonymization token map (review B/#7) from the call
        that just ran through THIS asyncio Task. Same ContextVar-backed
        isolation as last_tool_calls/last_thinking_blocks above — callers
        must thread this into ``pseudonymizer.detokenize(text, mapping)`` so
        only tokens THIS exchange minted can ever be expanded back."""
        val = _current_pseudonym_map.get()
        return val if val is not None else {}

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

    def get_chatbot_usage(self, chatbot_id: str) -> dict:
        result = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }
        for r in self._all:
            u = r.get_chatbot_usage(chatbot_id)
            result["input_tokens"] += u.get("input_tokens", 0)
            result["output_tokens"] += u.get("output_tokens", 0)
            result["requests"] += u.get("requests", 0)
            result["cost_usd"] += u.get("cost_usd", 0.0)
            result["tokens_today"] += u.get("tokens_today", 0)
            run_at = u.get("last_run")
            if run_at and (not result["last_run"] or run_at > result["last_run"]):
                result["last_run"] = run_at
        return result

    def reset_chatbot_usage(self, chatbot_id: str) -> None:
        for r in self._all:
            r.reset_chatbot_usage(chatbot_id)

    def reset_usage(self) -> None:
        for r in self._all:
            r.reset_usage()
