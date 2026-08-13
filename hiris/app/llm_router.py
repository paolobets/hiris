from __future__ import annotations
import json
import logging
import re
from typing import Any

from .claude_runner import (
    RunnerBackendError,
    _current_tool_calls,
    _current_thinking_blocks,
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

    A single ordered policy, chat_policy, selects the backend chain when
    model="auto". If not supplied (None/empty), it derives from
    _STRATEGY_ORDER[strategy] — unchanged behavior for existing callers.
    When the caller instead passes `model_chain` (the chain the user ordered,
    filtered to credentialed providers by model_activation.provider_in_catena
    — see server.py), that list supersedes chat_policy, and it does so ALSO
    when it is empty: an explicit empty chain means "nobody is in the chain",
    not "fall back to the strategy order".

    fetta E4 Task 7 ("un bot solo"): la modalità "automatic" (usata dai bot
    proattivi/schedulati per instradare su una politica diversa da quella
    della chat interattiva) è uscita insieme all'ultimo chiamante che
    passava mode="automatic" a chat()/chat_stream() — il Test Run
    (chatbot_engine.py, uscito al Task 4 di questa fetta). Con lei sono
    uscite la seconda policy (automatic_policy) e automatic_allows_sensitive()
    (già solo-test dal censimento prima di questo task, senza chiamante di
    produzione).

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
        chat_policy: list[str] | None = None,
        model_chain: list[str] | None = None,
    ) -> None:
        self._claude = claude
        self._openai = openai
        self._openrouter = openrouter
        self._ollama = ollama
        self._strategy = strategy if strategy in _STRATEGY_ORDER else "balanced"
        self._all = [r for r in [claude, openai, openrouter, ollama] if r is not None]
        # Se model_chain è fornito, sostituisce chat_policy col suo ordine
        # (fetta E4 Task 7: non esiste più una seconda policy da tenere
        # allineata -- automatic_policy è uscita con l'ultimo chiamante che
        # passava mode="automatic").
        #
        # fetta «la catena diventa l'unica verità»: una catena ESPLICITA vale
        # per quello che dice, anche quando è vuota. Fino alla 2.4.1 il ramo
        # era `if model_chain:` e una catena vuota ricadeva sull'ordine di
        # strategia -- innocuo finché `reconcile_chain` non poteva restituire
        # una lista vuota, letale adesso che può: la pagina avrebbe detto
        # «la catena è vuota, HIRIS non può rispondere» mentre il router
        # rispondeva usando OGNI provider con una credenziale. Sarebbe stata
        # la regola `legacy` appena tolta, rientrata da dentro il router --
        # cioè lo stesso difetto, per un'altra porta. `model_chain=None`
        # (nessuna catena passata) resta il ramo di libreria e ripiega come
        # prima.
        if model_chain is not None:
            self._chat_policy = [n for n in model_chain if n in _VALID_BACKEND_NAMES]
        else:
            self._chat_policy = _norm_policy(chat_policy, self._strategy)

    def _backend_map(self) -> dict[str, Any]:
        return {
            "claude": self._claude,
            "openai": self._openai,
            "openrouter": self._openrouter,
            "ollama": self._ollama,
        }

    def _ordered_backends(self) -> list[Any]:
        """Return available backends in chat_policy priority order."""
        bmap = self._backend_map()
        return [bmap[name] for name in self._chat_policy if bmap[name] is not None]

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
        model = kwargs.get("model", "auto")
        if model != "auto":
            runner = self._route(model)
            if runner is None:
                return "Nessun provider AI configurato per questo modello."
            return await runner.chat(**kwargs)
        # auto: try backends in chat_policy order with fallback
        ordinati = self._ordered_backends()
        if not ordinati:
            # Da questa fetta e' uno stato RAGGIUNGIBILE e con un significato:
            # la catena e' vuota (nessuno ce l'ha messo) oppure i nomi che
            # porta non hanno un backend costruito. «Riprova tra poco» sarebbe
            # una parola piu' larga del fatto -- non passa da solo.
            logger.warning("Nessun provider in catena: chat(model=auto) non ha a chi chiedere")
            return ("Nessun provider utilizzabile in catena: HIRIS non ha a chi "
                    "chiedere. Apri la pagina Modelli e mettine almeno uno in "
                    "catena.")
        last_friendly: str | None = None
        for runner in ordinati:
            try:
                return await runner.chat(**kwargs)
            except RunnerBackendError as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
                last_friendly = exc.friendly_message
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
        return last_friendly or "Tutti i provider AI non disponibili. Riprova tra poco."

    async def chat_stream(self, **kwargs):
        model = kwargs.get("model", "auto")
        if model == "auto":
            # no fallback in streaming (as today): just the first pick
            backends = self._ordered_backends()
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

    # fetta «la catena diventa l'unica verita'»: `simple_chat` e' uscita.
    # Sceglieva con `self._claude or self._openai or self._ollama` scritto a
    # mano -- OpenRouter escluso, nessun ripiego, catena ignorata: una SECONDA
    # regola di instradamento, che aspettava solo di contraddire la pagina.
    # Nessun chiamante di produzione la raggiungeva (le sole altre occorrenze
    # del nome sono le implementazioni nei backend, che restano: `base.py`,
    # `ollama.py`, `claude_runner.py`, `openai_compat_runner.py` -- li' e' la
    # firma di un backend, non una decisione di instradamento). Il censimento
    # non l'aveva segnalata: il nome e' definito in cinque punti e lo strumento
    # salta gli omonimi, limite che dichiara da se'.

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

    # Fetta "esce il documentale": qui viveva la proprieta'
    # `last_pseudonym_map`, che rileggeva la ContextVar omonima di
    # claude_runner.py. Esce con la pseudonimizzazione (brain/privacy.py).

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

    # fetta E4 Task 6 ("un bot solo"): `get_chatbot_usage`/`reset_chatbot_usage`
    # sono usciti -- aggregavano la stessa contabilita' per-chatbot uscita dai
    # due runner (claude_runner.py/openai_compat_runner.py, stessa mossa),
    # zero chiamanti di produzione.

    def reset_usage(self) -> None:
        for r in self._all:
            r.reset_usage()
