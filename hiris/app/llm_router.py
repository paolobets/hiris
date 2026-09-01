from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from .claude_runner import (
    RunnerBackendError,
    _current_thinking_blocks,
    _current_tool_calls,
)

logger = logging.getLogger(__name__)


def _is_openai_model(model: str) -> bool:
    return bool(re.match(r"^(gpt-|o[1-9])", model))


def _is_openrouter_model(model: str) -> bool:
    """User-facing prefix to route a model through OpenRouter.

    Accepts both 'openrouter:provider/model' and 'openrouter/provider/model'
    so users coming from LiteLLM-style naming feel at home.
    """
    return model.startswith(("openrouter:", "openrouter/"))


# `backend_is_cloud` e' USCITO (censimento del 17/08/2026, zero chiamanti di
# produzione). Diceva se un modello uscisse verso un provider cloud, e serviva
# alle STRATEGIE -- il preset che sceglieva l'ordine dei provider. Quel concetto
# e' uscito con la fetta «la catena diventa l'unica verita'»: l'ordine adesso e'
# esplicito e si riordina dalla pagina Modelli. La funzione era rimasta a
# rispondere a una domanda che nessuno fa piu'.


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
        registry: Any = None,
    ) -> None:
        # `registro` è `esiti_provider.RegistroEsiti` (app["registro_esiti"]).
        # Facoltativo perché `LLMRouter` è costruito anche da test e da codice
        # di libreria che non ha una app intorno; quando c'è, ogni giro del
        # ciclo di ripiego ci scrive che cosa ha visto. È l'UNICO scrittore:
        # i runner non lo ricevono, perché il turno vero passa di qui e due
        # scrittori della stessa osservazione sarebbero due rappresentazioni
        # dello stesso fatto.
        self._registry = registry
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

    def _ordered_backends_with_name(self) -> list[tuple[str, Any]]:
        """Gli anelli in ordine di catena, CON IL NOME DEL PROVIDER.

        Il nome serve perché il registro degli esiti è per provider, e
        `type(runner).__name__` non lo distingue: OpenAI e OpenRouter sono
        `OpenAICompatRunner` e `OpenRouterRunner`, e il secondo è una
        sottoclasse del primo -- un rifiuto di OpenRouter finirebbe scritto
        sulla riga di OpenAI, cioè un difetto silenzioso dentro la funzione
        nata per toglierne uno. Il nome autorevole è quello di
        `self._chat_policy`, che è la catena che l'utente ha ordinato.
        """
        bmap = self._backend_map()
        return [(name, bmap[name]) for name in self._chat_policy
                if bmap[name] is not None]

    def _ordered_backends(self) -> list[Any]:
        """Return available backends in chat_policy priority order.

        DERIVATA da `_ordered_backends_con_nome`, non una seconda
        implementazione: due liste ordinate dalla stessa policy sono due
        rappresentazioni della stessa cosa, libere di divergere.
        """
        return [runner for _, runner in self._ordered_backends_with_name()]

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
        ordered = self._ordered_backends_with_name()
        if not ordered:
            # Da questa fetta e' uno stato RAGGIUNGIBILE e con un significato:
            # la catena e' vuota (nessuno ce l'ha messo) oppure i nomi che
            # porta non hanno un backend costruito. «Riprova tra poco» sarebbe
            # una parola piu' larga del fatto -- non passa da solo.
            logger.warning("Nessun provider in catena: chat(model=auto) non ha a chi chiedere")
            return ("Nessun provider utilizzabile in catena: HIRIS non ha a chi "
                    "chiedere. Apri la pagina Modelli e mettine almeno uno in "
                    "catena.")
        last_friendly: str | None = None
        for backend_name, runner in ordered:
            # Il ciclo di ripiego è il SOLO posto in cui HIRIS vede davvero
            # come si comporta un provider, e fino a questa fetta lo buttava
            # via: un `logger.warning` e avanti. La pagina Modelli poteva dire
            # «Claude è primo in catena» e non «e sta rifiutando da quaranta
            # richieste» -- che è il caso del proprietario per intero.
            start = time.monotonic()
            try:
                answer = await runner.chat(**kwargs)
            except RunnerBackendError as exc:
                logger.warning("Backend %s failed, trying next: %s", backend_name, exc)
                if self._registry is not None:
                    self._registry.fallimento(
                        backend_name, family=getattr(exc, "family", "altro"),
                        code=getattr(exc, "code", None), message=str(exc),
                        durata_s=time.monotonic() - start)
                last_friendly = exc.friendly_message
            except Exception as exc:
                # Il ramo che c'era già: un guasto che NON è un
                # `RunnerBackendError` (un bug nel runner, un `TypeError` su una
                # firma cambiata) non porta né famiglia né codice. Si registra
                # come `"altro"` invece di essere buttato: un provider che
                # esplode in modo imprevisto deve comparire nella pagina come
                # uno che ha rifiutato, non come uno di cui non si sa niente.
                logger.warning("Backend %s failed, trying next: %s", backend_name, exc)
                if self._registry is not None:
                    self._registry.fallimento(
                        backend_name, family="altro", code=None,
                        message=str(exc), durata_s=time.monotonic() - start)
            else:
                if self._registry is not None:
                    self._registry.successo(backend_name)
                return answer
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
            yield (
                "data: "
                f'{json.dumps({"type": "error", "message": "Provider AI non configurato"})}'
                "\n\n"
            )
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

    # fetta E4 Task 6 ("un bot solo"): `get_chatbot_usage`/`reset_chatbot_usage`
    # sono usciti -- aggregavano la stessa contabilita' per-chatbot uscita dai
    # due runner (claude_runner.py/openai_compat_runner.py, stessa mossa),
    # zero chiamanti di produzione.
    #
    # fetta «i consumi, per modello» (22/08/2026): con loro escono anche le SEI
    # proprieta' aggreganti (`total_input_tokens`, `total_output_tokens`,
    # `total_requests`, `total_cost_usd`, `total_rate_limit_errors`,
    # `usage_last_reset`) e `reset_usage`. Sommavano i contatori dei runner,
    # e quei contatori non esistono piu': il consumo ha una casa sola,
    # `consumi/store.py`, che sa anche DI CHI sia -- cosa che questa somma
    # buttava via per costruzione. Zero chiamanti di produzione al momento
    # della cancellazione (`handlers_usage` legge l'archivio).
