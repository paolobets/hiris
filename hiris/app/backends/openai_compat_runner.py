from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import suppress
from typing import Any

import httpx as _httpx

from ..chat_store import LEAKED_TOOL_NAME_RE
from ..claude_runner import (
    _MAX_ITERATIONS_NOTICE,
    BASE_SYSTEM_PROMPT,
    COMPACT_PROMPT,
    MINIMAL_PROMPT,
    RESTRICT_PROMPT,
    RunnerBackendError,
    _current_tool_calls,
    _PerCallList,
)
from ..esiti_provider import error_family
from .pricing import get_price as _prezzo

# Circuit-breaker: after this many consecutive connection-class failures, skip
# the backend for the cooldown instead of hammering a dead endpoint. The
# observed failure mode was a stale Ollama tunnel (DNS no longer resolving)
# flooding the log with "Connection error" once per classify_entities call.
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SEC = 60


# fetta E4 Task 6 ("un bot solo"): `_estimate_tokens` e' uscita -- il suo
# unico chiamante (`_track_usage`'s per-chatbot estimate branch) e' uscito
# con lei, vedi il commento su `_track_usage` piu' sotto.


def _status_code(exc: Exception) -> int | None:
    """Lo stato HTTP di un errore d'API, o `None` se non ne porta uno.

    `openai.APIError` espone `status_code` sulle sottoclassi che nascono da una
    risposta; `APIConnectionError`/`APITimeoutError` no, perché una risposta non
    c'è mai stata. Il `None` di quel caso NON è un valore di comodo: è il fatto,
    e la pagina lo dice con parole diverse («non risponde all'indirizzo»).
    """
    status_code = getattr(exc, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _is_conn_error(exc: Exception) -> bool:
    """True for connection/timeout-class errors (endpoint unreachable), as
    opposed to API/validation errors which should NOT trip the breaker.

    Dalla fetta «cosa è successo davvero» questa funzione ha un secondo
    lettore, `esiti_provider.famiglia_errore`, che le chiede la stessa cosa per
    un altro scopo: dire «non risponde all'indirizzo» invece di «errore
    temporaneo». Da lì l'aggiunta di `anthropic` accanto a `openai` -- le due
    SDK hanno la stessa coppia di eccezioni con lo stesso significato, e
    riconoscerne una sola avrebbe fatto leggere «ha rifiutato» a un Claude che
    non si era nemmeno raggiunto. È una definizione sola di
    «irraggiungibile», che è il punto: due sarebbero libere di divergere.
    """
    for modulo in ("openai", "anthropic"):
        # `Exception` e non le sole ImportError/AttributeError: questo blocco SONDA quali
        # SDK sono installate, e gira dentro un `except` gia' in corso. Una libreria
        # presente ma rotta a basso livello (conflitto ABI di una sua dipendenza) puo'
        # sollevare qualunque cosa all'import: farla risalire da qui salterebbe la
        # costruzione del RunnerBackendError, cioe' romperebbe la gestione dell'errore
        # proprio mentre la si sta facendo. Il silenzio qui e' totale e voluto --
        # dichiararlo con `suppress` e' cio' che lo distingue da un `except: pass`.
        with suppress(Exception):
            sdk = __import__(modulo)
            if isinstance(exc, (sdk.APIConnectionError, sdk.APITimeoutError)):
                return True
    return isinstance(exc, (_httpx.ConnectError, _httpx.ConnectTimeout, ConnectionError))

logger = logging.getLogger(__name__)


def warn_thinking_ignored(backend_noun: str, thinking_budget: int) -> None:
    """Dice nel log che `thinking_budget` non viene applicato su questo backend.

    fetta E5 Task 2, fix round 1 (I-2). Fino a qui le due `del
    thinking_budget` qui sotto erano MUTE, col commento «intentionally ignored
    here (no warning: legitimately unused)» -- ed era vero finche' quel valore
    non poteva essere cambiato da nessuna interfaccia. Dal Task 2 della fetta
    E5 l'utente lo imposta dalla pagina «Impostazioni chat», legge «Salvato», e
    su OpenAI/OpenRouter/Ollama non succede niente: nessun ragionamento esteso
    e nessuna riga che lo dica. E' il difetto n.1 di questo prodotto -- il
    silenzio -- nella sua forma peggiore, perche' l'impostazione risulta
    salvata.

    Non si tenta di emulare il ragionamento esteso: il protocollo
    OpenAI-compatibile non espone un budget per richiesta, e inventarne uno
    sarebbe peggio. Si dichiara, una volta per turno e solo se il valore e'
    diverso da zero (a 0 non c'e' niente da dire: e' il default).
    """
    if thinking_budget:
        logger.warning(
            "thinking_budget=%d NON viene applicato: %s parla il protocollo "
            "OpenAI-compatibile, che non espone un budget di ragionamento per "
            "richiesta. L'impostazione resta salvata ma non ha effetto qui: il "
            "ragionamento esteso vale solo con i modelli Claude sul percorso "
            "diretto (claude_runner.py).",
            thinking_budget, backend_noun,
        )

AUTO_MODEL_MAP: dict[str, str] = {
    "chat":  "gpt-4o",
    "agent": "gpt-4o-mini",
}

# fetta "i riferimenti" (R3): stesso tetto e stessa ragione di
# claude_runner.MAX_TOOL_ITERATIONS -- 10 round-trip morivano garantiti
# contro 8 stanze da guardare una a una, senza margine per il giro finale
# della risposta. Sale a 50.
MAX_TOOL_ITERATIONS = int(os.environ.get("MAX_TOOL_ITERATIONS", "50"))
# Ollama tende a fare più iterazioni a vuoto; limite ridotto per contenere la
# latenza. La proporzione resta quella di sempre -- meta' del tetto sincrono
# (10 -> 5, ora 50 -> 25) -- non un nuovo giudizio su Ollama.
_OLLAMA_MAX_TOOL_ITERATIONS = int(os.environ.get("OLLAMA_MAX_TOOL_ITERATIONS", "25"))


def _to_openai_tools(tool_defs: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_defs
    ]


# Heuristic: identifier of 3+ chars at the start of content immediately
# followed by a non-ASCII non-whitespace codepoint. Some Mistral/Hermes
# routings on OpenRouter fail to translate the model's native special tool
# tokens (e.g. [TOOL_CALLS], rendered as isolated Hebrew/Vietnamese
# codepoints in UTF-8) into the OpenAI tool_calls schema, so the response
# arrives as plain text content like:
#   get_ha_healthיׂ{"sections":["all"]}
#   await_user_confirmationיׄ**Confermi di...**
# Persisting this verbatim into chat history poisons later turns.
# La stessa regola di `chat_store.LEAKED_TOOL_NAME_RE`, IMPORTATA.
#
# Erano due regex identiche tranne che per uno spazio tollerato in testa: qui
# si tollerava, la' no. La differenza contava sul disco -- `_purge_toxic_turns`
# ripulisce le righe GIA' scritte, e una avvelenata con uno spazio iniziale non
# veniva mai riconosciuta e tornava al modello a ogni turno, per sempre.
_TOOL_LEAK_RE = LEAKED_TOOL_NAME_RE

TOOL_LEAK_USER_MSG = (
    "Il modello selezionato non gestisce correttamente i tool tramite questo "
    "provider (la chiamata al tool è arrivata come testo invece che come "
    "tool_call). Cambia modello — preferisci quelli con tool use nativo "
    "OpenAI — oppure disattiva i tool dell'agente."
)


def detect_leaked_tool_call(content: str, tool_names) -> str | None:
    """Return the matched tool name if `content` is a leaked tool call, else None.

    The identifier must exactly match one of the runner's currently-available
    tool names so legitimate prose mentioning Latin punctuation/em-dashes does
    not trigger.
    """
    if not content or not tool_names:
        return None
    if not isinstance(tool_names, (set, frozenset)):
        tool_names = frozenset(tool_names)
    m = _TOOL_LEAK_RE.match(content)
    if not m:
        return None
    candidate = m.group(1)
    return candidate if candidate in tool_names else None


# OpenRouter 402 'Payment Required' messages embed the maximum affordable
# completion tokens for the current API-key credit balance, e.g.:
#   "You requested up to 4096 tokens, but can only afford 3907."
# (Note: real messages have no 'tokens' word after the number — just the
# integer followed by a period.) We parse this once and retry the same call
# with a clamped value so a transient credit shortage does not produce an
# opaque "Errore temporaneo".
_AFFORD_RE = re.compile(r"can only afford (\d+)", re.IGNORECASE)


def parse_afford_limit(exc: Any) -> int | None:
    """If `exc` carries an OpenRouter 402 'afford X tokens' message, return X
    reduced by a small safety margin. Returns ``None`` if the message does
    not match — caller falls back to generic error handling.
    """
    msg = getattr(exc, "message", None) or str(exc) or ""
    m = _AFFORD_RE.search(msg)
    if not m:
        return None
    try:
        affordable = int(m.group(1))
    except ValueError:
        return None
    # 5% margin leaves room for tokeniser variation between request and
    # OpenRouter's own counting.
    return max(1, int(affordable * 0.95))


# OpenRouter free-tier rate-limit messages embed the upstream provider error
# verbatim under metadata.raw, e.g.:
#   "qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream.
#    Please retry shortly, or add your own key..."
# We surface this clearer message instead of the opaque "Errore temporaneo".
_UPSTREAM_RATELIMIT_RE = re.compile(
    r"([\w\-./]+:free)\s+is\s+temporarily\s+rate-limited\s+upstream",
    re.IGNORECASE,
)


def parse_upstream_rate_limit(exc: Any) -> str | None:
    """Detect free-tier upstream rate limit and return an actionable Italian
    message. Returns ``None`` if the exception is not this specific case.
    """
    msg = getattr(exc, "message", None) or str(exc) or ""
    m = _UPSTREAM_RATELIMIT_RE.search(msg)
    if not m:
        # Some providers emit the plain phrase without naming the model.
        if "rate-limited upstream" in msg.lower():
            # NON si dice `:free`. Il provider non ha nominato il modello,
            # quindi non sappiamo QUALE sia -- e non sapendo quale, non
            # possiamo sapere che sia gratuito. Visto dal vivo il 21/08/2026:
            # il modello dell'utente era `mistralai/mistral-large`, a
            # pagamento, e questa riga gli diceva che era un `:free`,
            # mandandolo a cercare un problema che non aveva. E' lo stesso
            # difetto della diagnosi inventata di `azione/porta.py` («probabile
            # problema di comunicazione col dispositivo»), che gli fece cercare
            # un guasto inesistente: una frase che afferma piu' del misurato.
            #
            # Il consiglio resta -- e' cio' che serve a chi legge -- ma senza
            # nominare la fascia gratuita nemmeno come ipotesi: il caso e'
            # frequente, non certo, e il test lo controlla con un `not in`
            # netto. Una guardia che deve distinguere un'ipotesi da
            # un'affermazione e' piu' debole di una che vieta la parola.
            return (
                "Il modello selezionato ha esaurito il rate limit upstream — "
                "OpenRouter non ha detto quale. Riprova tra qualche minuto, "
                "oppure scegli un altro modello nella pagina Modelli (o "
                "aggiungi una tua API key del provider su "
                "openrouter.ai/settings/integrations)."
            )
        return None
    model_name = m.group(1)
    return (
        f"Il modello {model_name} ha esaurito il rate limit upstream. "
        "Riprova tra qualche minuto oppure passa a un modello a pagamento "
        "(o aggiungi una tua API key del provider su "
        "openrouter.ai/settings/integrations)."
    )


class OpenAICompatRunner:
    """Agentic LLM runner for OpenAI-compatible APIs (OpenAI cloud + Ollama local)."""

    # Per-call, per-asyncio-Task isolated — shares the SAME ContextVar as
    # ClaudeRunner (review A/#3 — see claude_runner.py's module comment for
    # the full rationale). No last_thinking_blocks here: OpenAI-compatible
    # backends don't support Anthropic Extended Thinking (thinking_budget is
    # accepted-and-ignored in chat() below).
    last_tool_calls = _PerCallList(_current_tool_calls)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        local: bool = False,
        read_model=None,
        timeout_s: float = 0.0,
        log_usage=None,
    ) -> None:
        # fetta «la catena diventa l'unica verita'» (Task 10): `fixed_model`
        # era UN parametro per TRE cose insieme -- «questo e' Ollama»,
        # «valida l'URL», «usa sempre questo modello». Le prime due sono la
        # MODALITA' e restano legate a `local`; la terza e' una DECISIONE
        # dell'utente, cambia da una PUT all'altra e adesso si LEGGE al
        # momento dell'uso (`leggi_modello`) invece di essere cotta nel
        # costruttore -- era il motivo per cui cambiare il modello di Ollama
        # non poteva avere effetto senza riavviare l'add-on.
        if local:
            from ..backends.ollama import _validate_ollama_url
            _validate_ollama_url(base_url)
        self._api_key = api_key
        self._base_url = base_url
        self._local = local
        self._read_model = read_model
        self._is_cloud = not local  # True = cloud (OpenAI); False = local (Ollama)
        # Il runner non conosce l'archivio dei consumi: conosce una funzione.
        # Stessa disciplina di `leggi_modello`. Ed e' la regola non negoziabile
        # di CLAUDE.md: un kwarg nuovo di `ClaudeRunner` lo accetta ANCHE
        # questa classe, o i backend non-Claude si rompono in silenzio.
        self._log_usage = log_usage
        # Il nome AUTOREVOLE del provider. `type(self).__name__` non lo
        # distingue: `OpenRouterRunner` e' una sottoclasse di questa classe, e
        # un consumo di OpenRouter finirebbe scritto sulla riga di OpenAI --
        # lo stesso difetto che `LLMRouter._ordered_backends_con_nome` e' gia'
        # stato scritto per evitare nel registro degli esiti, e per la stessa
        # ragione.
        self.provider_name = "ollama" if local else "openai"
        # Circuit-breaker message noun, so a cloud backend doesn't report
        # itself as "il backend locale" (review backlog #7).
        self._backend_noun = "Il servizio AI" if self._is_cloud else "Il backend locale"
        # Ollama su hardware lento: timeout esplicito per evitare hang infiniti.
        # Cloud OpenAI: 600s (rispetta default SDK per risposte lunghe). Il
        # numero arriva dal chiamante -- per Ollama e' `ollama.timeout_s`
        # dell'archivio, la stessa casa da cui la pagina Modelli lo mostra:
        # fino a questa fetta veniva da `OLLAMA_REQUEST_TIMEOUT`, cioe' una
        # SECONDA rappresentazione dello stesso numero accanto alla copia
        # d'archivio (invariante 1), e le due potevano dire cose diverse.
        self._timeout_s = 0.0
        self.apply_timeout(float(timeout_s) if timeout_s else (120.0 if local else 600.0))
        # Circuit-breaker state for connection-class failures (dead endpoint).
        self._conn_fail_count = 0
        self._circuit_open_until = 0.0
        # last_tool_calls is intentionally NOT initialized here — it's a
        # per-call/per-Task class-level descriptor (see above); chat() resets
        # it at the start of every call, scoped to the calling Task.
        # fetta «i consumi, per modello» (22/08/2026): qui vivevano i contatori
        # globali (`total_input_tokens`, `total_output_tokens`,
        # `total_requests`, `total_cost_usd`, `total_rate_limit_errors`,
        # `usage_last_reset`), la loro persistenza (`_load_usage`/`_save_usage`
        # su `usage.json`, col lock che ne serializzava le scritture) e
        # `reset_usage`. Erano la SECONDA casa del consumo -- quella che
        # sommava tutto insieme e non sapeva dire di quale modello parlasse --
        # e sono uscite col loro `usage_path`. Il consumo si scrive adesso in
        # `consumi/store.py` attraverso `registra_consumo`, e i vecchi
        # `usage_*.json` ci entrano una volta sola all'avvio come riga
        # «(prima del dettaglio)»: i file restano sul disco, mai dati
        # dell'utente cancellati in silenzio.

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    # fetta E4 Task 6 ("un bot solo"): `_ensure_today_reset`/`get_chatbot_usage`/
    # `reset_chatbot_usage` sono usciti -- stessa mossa e stessa storia del
    # commento gemello in claude_runner.py.

    def _track_usage(self, response: Any, model: str) -> None:
        """Aggiorna i contatori GLOBALI (total_input_tokens/total_output_tokens/
        total_cost_usd) e persiste. fetta E4 Task 6: la stima per-chatbot che
        viveva qui (quando `response` non porta `usage`, tipico di OpenRouter/
        Ollama, stimata da `est_input_chars` -- il conteggio caratteri dei
        messaggi inviati) esisteva SOLO per far "mordere" un budget
        per-esecuzione che leggeva `get_chatbot_usage` -- quel lettore e'
        uscito al Task 3 (rotte usage) insieme a `server.py`'s
        `agent_run_usage`, gia' morto prima di questo task (verificato: zero
        occorrenze in produzione). Con lui muore anche lo scopo dell'unico
        chiamante di `_estimate_tokens` (uscita insieme, verificato zero altri
        chiamanti) e il parametro `est_input_chars` (nessun altro lettore):
        senza `usage` non c'e' piu' nulla da stimare o da scrivere, solo da
        dichiarare in log. Anche PRIMA di questo task il ramo "nessun usage"
        non alimentava i contatori globali (solo quelli per-chatbot, ora
        usciti): nessuna regressione sui totali globali.
        """
        usage = getattr(response, "usage", None)
        if not usage:
            logger.debug("Model %s: risposta senza 'usage' -- nessun contatore aggiornato", model)
            return
        inp = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        prices = _prezzo(model)
        cost = (inp * prices["input"] + out * prices["output"]) / 1_000_000

        # OpenRouter dichiara il costo VERO in ogni risposta -- `usage.cost`,
        # sempre presente, anche in streaming (Usage Accounting, verificato
        # sulla loro documentazione il 21/08/2026). Leggerlo trasforma in un
        # fatto quella che era una stima, e la stima valeva ZERO: `_prezzo` non
        # conosce nessun identificativo OpenRouter e cadeva su `_default`. E'
        # il difetto da cui nasce l'intera fetta.
        if self._log_usage is None:
            return
        from ..consumi.vocabulary import cost_state_and_value

        declared = getattr(usage, "cost", None)
        state, cost = cost_state_and_value(self.provider_name, model,
                                     cost_dichiarato=declared,
                                     cost_da_listino=cost)
        self._log_usage(
            self.provider_name, model, token_in=inp, token_out=out,
            cache_read=getattr(usage, "cached_tokens", 0) or 0,
            cache_write=getattr(usage, "cache_write_tokens", 0) or 0,
            cost_usd=cost, cost_state=state, now=time.time())

    def _write_rejection(self, model: str) -> None:
        """Un 429 si conta sulla riga del modello che l'ha preso.

        `richieste=0`: un rifiuto non e' una richiesta servita. Oggi
        `total_rate_limit_errors` e' un numero solo per tutto il prodotto e
        non dice CHI stia rifiutando -- che e' l'unica cosa che serve sapere
        quando succede.
        """
        if self._log_usage is None:
            return
        self._log_usage(
            self.provider_name, model, richieste=0, errori_rate_limit=1,
            cost_usd=None, cost_state="non_noto", now=time.time())

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------

    def _chosen_model(self) -> str:
        """Il modello scelto ADESSO, letto dove vive (l'archivio)."""
        return (self._read_model() if self._read_model else "") or ""

    def _resolve_current_model(self) -> str:
        """Il modello che questo runner userebbe adesso con `model="auto"`.

        Esiste per rendere OSSERVABILE la lettura a caldo: senza, l'unico modo
        di provarla sarebbe intercettare la chiamata all'API."""
        return self._resolve_model("auto", "chat")

    def _resolve_model(self, model: str, agent_type: str) -> str:
        # Ollama: il modello scelto vince SEMPRE, anche su un modello passato
        # esplicitamente -- era gia' cosi' (`if self._fixed_model: return
        # self._fixed_model` come primo ramo) e resta, perche' l'istanza locale
        # ne ha scaricato uno solo e chiedergliene un altro fallirebbe. La sola
        # differenza e' che adesso il valore si LEGGE.
        chosen = self._chosen_model()
        if self._local:
            return chosen
        if model == "auto":
            return chosen or AUTO_MODEL_MAP.get(agent_type, "gpt-4o-mini")
        return model

    def apply_timeout(self, seconds: float) -> None:
        """Rifa' il client con un nuovo timeout.

        E' l'unico valore di questa fetta che non si puo' leggere al momento
        dell'uso: `AsyncOpenAI` cuoce `_httpx.Timeout(...)` nel client alla
        costruzione. Rifarlo e' a costo locale (nessuna connessione viene
        aperta finche' non parte una richiesta), e la sola alternativa --
        dichiarare questo campo «solo al riavvio» -- rimetterebbe in pagina la
        didascalia che questa fetta toglie.

        NON si tocca il client vecchio: una richiesta puo' essere in volo su di
        lui proprio adesso, e chiuderlo la ucciderebbe a meta' turno. Resta al
        garbage collector, che lo raccoglie quando l'ultima richiesta finisce.
        Per questo il rifacimento e' un NO-OP quando il numero non e' cambiato:
        senza quella guardia ogni salvataggio della pagina Modelli lascerebbe
        dietro un pool di connessioni, anche quando l'utente ha solo riordinato
        la catena."""
        seconds = float(seconds)
        if seconds == self._timeout_s:
            return
        import openai as _openai
        self._timeout_s = seconds
        # Ollama: disabilita auto-retry SDK. Default openai 2.x = 2 retry, che
        # cumulativamente possono superare il wrapper chatbot_engine 300s
        # producendo "Timeout dopo 300s" generico senza log specifici. Con
        # max_retries=0 il primo APIError/Timeout viene loggato e ritornato.
        # Cloud OpenAI: lascia il default (2) — la rete cloud è meno volatile.
        self._client = _openai.AsyncOpenAI(
            api_key=self._api_key, base_url=self._base_url,
            timeout=_httpx.Timeout(seconds, connect=5.0),
            max_retries=0 if self._local else 2,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def circuit_state(self) -> float:
        """Secondi che mancano alla riapertura, 0 se il circuito è chiuso.

        Esiste da prima di questa fetta (`_circuit_open_until`, soglia 3,
        raffreddamento 60 s) e NESSUNA rotta lo restituiva: la pagina non poteva
        dire «lo sto saltando» di un provider che il prodotto stava
        effettivamente saltando.

        È la SOLA lettura dello stato del circuito -- `_circuit_is_open` ne
        deriva, invece di confrontare l'orologio una seconda volta: due
        confronti sullo stesso numero sono due rappresentazioni della stessa
        cosa, e questa fetta esiste per non averne.
        """
        return max(0.0, self._circuit_open_until - time.monotonic())

    def _circuit_is_open(self) -> bool:
        return self.circuit_state() > 0.0

    def _record_conn_failure(self) -> None:
        self._conn_fail_count += 1
        if self._conn_fail_count >= _CIRCUIT_THRESHOLD and not self._circuit_is_open():
            self._circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN_SEC
            logger.warning(
                "Backend %s unreachable (%d consecutive connection failures) — "
                "circuit open for %ds, skipping calls.",
                self._base_url, self._conn_fail_count, _CIRCUIT_COOLDOWN_SEC,
            )

    def _record_success(self) -> None:
        if self._conn_fail_count or self._circuit_open_until:
            self._conn_fail_count = 0
            self._circuit_open_until = 0.0

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        # Skip the network entirely while the breaker is open — this is what
        # stops a dead backend (e.g. a stale Ollama tunnel) from flooding the
        # log and wasting connect timeouts once per classify_entities call.
        if self._circuit_is_open():
            return ""
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        try:
            kwargs: dict = {
                # Cloud: lo stesso "gpt-4o-mini" scritto qui da sempre (questa
                # chiamata non passa da `_resolve_model` e non ha un
                # agent_type). Locale: il modello scelto, letto adesso.
                "model": (self._chosen_model() if self._local else "") or "gpt-4o-mini",
                "messages": msgs,
                "max_tokens": 1024,
            }
            if self._local:
                kwargs["extra_body"] = {"think": False}
            resp = await self._client.chat.completions.create(**kwargs)
            self._record_success()
            return resp.choices[0].message.content or ""
        except Exception as exc:
            if _is_conn_error(exc):
                self._record_conn_failure()
                # Log the first failures, then go quiet (the open-circuit warning
                # is logged once) so a dead endpoint doesn't flood the log.
                if self._conn_fail_count < _CIRCUIT_THRESHOLD:
                    logger.warning("simple_chat connection error: %s", exc)
            else:
                logger.error("simple_chat failed: %s", exc)
            return ""

    # fetta E4 Task 6, fix round 1 (Important 1 della review indipendente):
    # `user_id` e' uscito da `chat()`/`chat_stream()` -- stessa mossa, stessa
    # storia del commento gemello in claude_runner.py (il suo unico lettore
    # era il ramo di scorta rimosso da questo stesso task, sfuggito al primo
    # giro).
    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: list[dict] | None = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        tools: list[dict] | None = None,
        dispatcher: Any | None = None,
    ) -> str:
        # thinking_budget is part of the runner contract since v0.9.5 because
        # ClaudeRunner uses it for Anthropic Extended Thinking. OpenAI/Ollama/
        # OpenRouter don't surface a comparable per-request budget knob in the
        # OpenAI-compatible spec — Ollama uses `extra_body={"think": False}`
        # for reasoning-default models, applied unconditionally below.
        # The kwarg is accepted to match the LLMRouter common signature. Fino
        # al fix round 1 del Task 2 della fetta E5 qui c'era scritto
        # "intentionally ignored here (no warning: legitimately unused)": la
        # seconda meta' e' diventata falsa nel momento in cui l'utente ha
        # potuto impostare quel valore dalla pagina. Vedi
        # `warn_thinking_ignored` in cima al file.
        warn_thinking_ignored(self._backend_noun, thinking_budget)
        del thinking_budget
        import openai as _openai

        # review M3/#2: the connection-failure circuit breaker used to guard
        # simple_chat() only. The agentic loop below never consulted it, so a
        # dead Ollama endpoint was retried at full timeout every single turn
        # instead of failing fast like simple_chat() already does.
        if self._circuit_is_open():
            # Il circuito aperto è «non l'ho interrogato», e si registra come
            # tale: la famiglia è `irraggiungibile` (è l'unica cosa che fa
            # scattare il circuito, vedi `_record_conn_failure`) e non c'è
            # nessun codice, perché non c'è stata nessuna risposta da cui
            # prenderlo. Senza questo, un provider che il prodotto sta
            # saltando comparirebbe nella pagina come uno che ha avuto un
            # «errore temporaneo» -- la parola più larga del fatto.
            raise RunnerBackendError(
                f"{self._backend_noun} non risponde da diversi tentativi "
                "consecutivi (circuito aperto). Riprova tra qualche istante.",
                family="irraggiungibile", code=None,
            )

        self.last_tool_calls = []

        effective_model = self._resolve_model(model, agent_type)

        # Build system message (OpenAI uses a single system message)
        #
        # Fix della review totale della fetta "il ponte riceve il nucleo"
        # (parita' A, m-4): qui i modificatori stavano DOPO `context_str`, e
        # in `claude_runner.py::ClaudeRunner.chat` stanno PRIMA, con un
        # commento che dichiara l'ordine obbligatorio ("must precede
        # context_str"). Due composizioni divergenti della stessa cosa, con
        # l'invariante scritta in un posto solo. Verificato prima di
        # muovere: l'invariante e' VERA e ha una ragione meccanica, cioe' che
        # i blocchi STABILI (BASE, persona, modificatori -- fissi per
        # configurazione) devono stare prima del blocco VOLATILE
        # (`context_str`, che cambia a ogni turno perche' e' il nucleo). Di
        # la' quella ragione e' l'unico breakpoint di cache cumulativo, che
        # va posato sull'ultimo blocco stabile; qui non ci sono breakpoint
        # espliciti, ma il caching di prefisso di OpenAI/OpenRouter (e la
        # cache di prompt di Ollama/llama.cpp) e' anch'esso PER PREFISSO: un
        # blocco volatile messo prima dei modificatori butta i modificatori
        # fuori dal prefisso riusabile a ogni singolo turno. Stessa
        # invariante, stessa ragione, mezzo diverso.
        #
        # E in piu': `agent/prompts.py::build_chat_messages` (il ponte)
        # compone gia' BASE -> persona -> modificatori -> guida -> contesto.
        # Con questa correzione i TRE composizioni del prodotto mettono i
        # modificatori nello stesso posto, e la parita' non e' piu' vera solo
        # per due su tre. Pinnato da
        # `tests/test_ordine_di_composizione.py`.
        system_parts = [BASE_SYSTEM_PROMPT]
        if system_prompt:
            system_parts.append(system_prompt)
        # I modificatori di comportamento -- stabili per configurazione,
        # DEVONO precedere `context_str` (vedi sopra).
        if restrict_to_home:
            system_parts.append(RESTRICT_PROMPT)
        # fetta E4 Task 6 ("un bot solo"): il parametro `require_confirmation`
        # stesso e' uscito da `chat()`/`chat_stream()` -- vedi il commento
        # gemello in claude_runner.py per il perche' non aveva gia' piu'
        # alcun effetto sul system prompt da prima di questo task.
        if response_mode == "compact":
            system_parts.append(COMPACT_PROMPT)
        elif response_mode == "minimal":
            system_parts.append(MINIMAL_PROMPT)
        if context_str:
            system_parts.append(context_str)

        messages: list[dict] = [{"role": "system", "content": "\n\n---\n\n".join(system_parts)}]
        for msg in (conversation_history or []):
            messages.append({"role": msg["role"], "content": str(msg["content"])})
        messages.append({"role": "user", "content": user_message})

        # Build tool list
        if tools is not None:
            # Il catalogo arriva gia' deciso dal chiamante. Stessa regola di
            # ClaudeRunner.chat() (vedi il suo commento gemello).
            tools = list(tools)
        else:
            # fetta E3 Task 8: nessun catalogo di scorta da cui pescare --
            # vedi il commento gemello in claude_runner.chat().
            tools = []
        oai_tools = _to_openai_tools(tools) if tools else None
        tool_name_set = frozenset(t["name"] for t in tools)

        # I modelli locali (Ollama) tendono a inventare nomi di tool non presenti nello schema.
        # Iniettare la lista esplicita nel system prompt riduce fortemente le allucinazioni.
        if self._local and tools:
            tool_names = ", ".join(t["name"] for t in tools)
            messages[0]["content"] += (
                f"\n\n---\n\nTool disponibili: {tool_names}.\n"
                "NON chiamare tool non presenti in questa lista."
            )

        max_iter = _OLLAMA_MAX_TOOL_ITERATIONS if self._local else MAX_TOOL_ITERATIONS
        for iter_idx in range(max_iter):
            try:
                kwargs: dict = {
                    "model": effective_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if oai_tools:
                    kwargs["tools"] = oai_tools
                # Ollama-specific: disabilita reasoning/thinking di default per
                # modelli che lo abilitano on-by-default (Gemma 4, Qwen QwQ,
                # DeepSeek R1, ecc.). Questi modelli emettono token "thinking"
                # per molti secondi prima di emettere "content"; in modalita'
                # non-streaming la risposta non arriva mai entro il timeout
                # HTTP e la chiamata HIRIS finisce in timeout 300s senza log
                # specifici. `think: false` e' un parametro non-OpenAI che
                # viene passato via extra_body al body JSON: i modelli senza
                # thinking lo ignorano, quelli con thinking lo disattivano.
                if self._local:
                    kwargs["extra_body"] = {"think": False}
                if self._local:
                    msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
                    logger.info(
                        "Ollama call: model=%s iter=%d/%d tools=%d msg_chars=%d",
                        effective_model, iter_idx + 1, max_iter,
                        len(oai_tools or []), msg_chars,
                    )
                response = await self._client.chat.completions.create(**kwargs)
                if self._local:
                    _content = (
                        (response.choices[0].message.content or "") if response.choices else ""
                    )
                    logger.info(
                        "Ollama response: finish=%s content_len=%d tools=%d",
                        response.choices[0].finish_reason if response.choices else "?",
                        len(_content),
                        (
                            len(response.choices[0].message.tool_calls or [])
                            if response.choices else 0
                        ),
                    )
            except _openai.RateLimitError as exc:
                self._write_rejection(effective_model)
                logger.error("OpenAI rate limit: %s", exc)
                upstream = parse_upstream_rate_limit(exc)
                # Un 429 è famiglia `altro`: è un guasto vero, ma non dice a
                # chi legge che cosa fare, e inventargli un'azione sarebbe
                # l'ipotesi sulla causa che questo prodotto non fa. Il codice
                # invece si porta, perché è un fatto.
                raise RunnerBackendError(
                    upstream or "Errore temporaneo del servizio AI. Riprova tra poco.",
                    family=error_family(exc),
                    code=_status_code(exc) or 429,
                ) from exc
            except _openai.APIError as exc:
                # OpenRouter 402: the API key has insufficient credit for the
                # current max_tokens. The error message tells us the highest
                # affordable budget — retry once with that lower value before
                # giving up so a transient credit shortage doesn't kill the
                # turn with an opaque "Errore temporaneo".
                affordable = parse_afford_limit(exc)
                if affordable and affordable < kwargs.get("max_tokens", 0):
                    logger.warning(
                        "OpenRouter 402 on %s: requested max_tokens=%d, "
                        "retrying with %d (key credit limit).",
                        effective_model, kwargs["max_tokens"], affordable,
                    )
                    kwargs["max_tokens"] = affordable
                    try:
                        response = await self._client.chat.completions.create(**kwargs)
                    except _openai.APIError as retry_exc:
                        logger.error(
                            "OpenRouter 402 retry failed: %s", retry_exc,
                        )
                        raise RunnerBackendError(
                            f"Crediti OpenRouter insufficienti per max_tokens={max_tokens}. "
                            f"Riduci max_tokens dell'agente sotto {affordable} "
                            f"oppure aggiungi credito su openrouter.ai.",
                            family=error_family(retry_exc),
                            code=_status_code(retry_exc),
                        ) from retry_exc
                else:
                    # review M3/#2: connection-class failures (dead endpoint)
                    # must trip the same breaker simple_chat() uses, so a
                    # stale Ollama tunnel fails fast on the NEXT turn instead
                    # of being retried at full timeout forever.
                    if _is_conn_error(exc):
                        self._record_conn_failure()
                    logger.error("OpenAI/Ollama API error: %s", exc)
                    # La frase per l'utente resta la stessa; il codice e la
                    # famiglia smettono di andare persi. Era questo il punto
                    # in cui «404, quel modello non esiste più» e «402, credito
                    # finito» diventavano la stessa identica riga.
                    raise RunnerBackendError(
                        "Errore temporaneo del servizio AI. Riprova tra poco.",
                        family=error_family(exc),
                        code=_status_code(exc),
                    ) from exc

            self._record_success()
            self._track_usage(response, effective_model)
            choice = response.choices[0]

            if choice.finish_reason == "stop":
                raw_content = choice.message.content or ""
                leaked = detect_leaked_tool_call(raw_content, tool_name_set)
                if leaked:
                    logger.warning(
                        "Model %s leaked tool call '%s' as text content "
                        "(provider does not translate native tool tokens). Sample: %r",
                        effective_model, leaked, raw_content[:160],
                    )
                    return TOOL_LEAK_USER_MSG
                return raw_content

            if choice.finish_reason == "tool_calls":
                tool_calls = choice.message.tool_calls or []
                # Reconstruct assistant message cleanly.
                # content is None per OpenAI spec when finish_reason=="tool_calls";
                # omit it to avoid rejection by strict OpenAI-compatible endpoints.
                assistant_msg: dict = {"role": "assistant"}
                if choice.message.content is not None:
                    assistant_msg["content"] = choice.message.content
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant_msg)
                for tc in tool_calls:
                    try:
                        tool_input = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as json_exc:
                        logger.warning(
                            "Tool %s: argomenti JSON non validi %r: %s",
                            tc.function.name, tc.function.arguments[:120], json_exc,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({
                                "error": (
                                    f"Argomenti JSON non validi per '{tc.function.name}'. "
                                    "Correggi il JSON e riprova."
                                )
                            }),
                        })
                        continue
                    if dispatcher is not None:
                        # DispatcherStrumenti (e affini): stessa interfaccia
                        # minima dispatch(nome, argomenti). fetta E4 Task 6:
                        # il ramo "dispatcher di scorta" (self._dispatcher,
                        # con le kwargs allowed_entities/allowed_services/
                        # allowed_endpoints/chatbot_id/visible_entity_ids/
                        # knowledge_allow_sensitive/knowledge_kinds) e' uscito
                        # -- vedi il commento gemello in ClaudeRunner.chat().
                        result = await dispatcher.dispatch(tc.function.name, tool_input)
                    else:
                        # ne' un dispatcher per-chiamata -- vedi il commento
                        # gemello in ClaudeRunner.chat().
                        logger.debug(
                            "Strumento '%s' richiesto ma nessun dispatcher disponibile "
                            "(degradazione dichiarata, non un errore)", tc.function.name)
                        result = {"error": f"Strumento '{tc.function.name}' non disponibile."}
                    self.last_tool_calls.append({"tool": tc.function.name, "input": tool_input})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
            else:
                if choice.finish_reason == "length":
                    # OpenAI's analog of Anthropic max_tokens: generation cut off
                    # (possibly mid tool call). Surface the truncation instead of
                    # returning a misleading partial preamble with nothing executed.
                    from ..claude_runner import _max_tokens_message
                    return _max_tokens_message([choice.message.content or ""])
                raw_content = choice.message.content or f"Stopped: {choice.finish_reason}"
                leaked = detect_leaked_tool_call(raw_content, tool_name_set)
                if leaked:
                    logger.warning(
                        "Model %s leaked tool call '%s' as text content "
                        "(finish_reason=%s). Sample: %r",
                        effective_model, leaked, choice.finish_reason, raw_content[:160],
                    )
                    return TOOL_LEAK_USER_MSG
                return raw_content

        # fetta "i riferimenti" (R4, Task 6): l'esaurimento non e' piu' muto
        # -- vedi il commento gemello in claude_runner.chat(). `self.
        # last_tool_calls` e' gia' in mano, riusato qui, non un secondo
        # tracciamento; solo i NOMI degli strumenti, mai gli argomenti.
        logger.warning(
            "chat(): esaurite %d iterazioni senza risposta finale -- strumenti chiamati: %s",
            max_iter, [c["tool"] for c in self.last_tool_calls],
        )
        return _MAX_ITERATIONS_NOTICE

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: list[dict] | None = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        tools: list[dict] | None = None,
        dispatcher: Any | None = None,
    ):
        """Vero streaming SSE: i token arrivano mentre il modello genera.
        Le iterazioni tool-call vengono risolte prima di cedere il controllo
        al loop successivo; il testo finale è streamato token per token.

        `strumenti`/`dispatcher` (Task 3 della fetta "il contesto della chat
        viene dal nucleo"): a differenza di `ClaudeRunner.chat_stream`, che e'
        gia' un guscio sottile attorno a `chat()`, questo metodo costruisce il
        proprio loop agentico da zero -- quindi i due punti dove `chat()`
        applica la stessa regola (catalogo tool, dispatch) sono replicati qui
        sotto uno per uno, non ereditati per delega. Senza questo, il ramo SSE
        (la card Lovelace) sarebbe rimasto sul catalogo di trentaquattro
        strumenti mentre la pagina chat (che non streamma, vedi
        static/chat/send.js) passava ai quattro del nucleo -- due strade
        divergenti per la stessa conversazione, esattamente il difetto che
        questa fetta esiste per chiudere.
        """
        # See chat() for rationale on accepting+ignoring thinking_budget here
        # -- avviso incluso (fix round 1, I-2): il ramo SSE serve la card
        # Lovelace, dove il silenzio sarebbe identico.
        warn_thinking_ignored(self._backend_noun, thinking_budget)
        del thinking_budget
        import openai as _openai

        # review M3/#2: see chat() above -- the streaming agentic loop must
        # also consult the circuit breaker instead of hammering a dead
        # endpoint at full timeout on every turn.
        if self._circuit_is_open():
            yield (
                'data: '
                + json.dumps({
                    "type": "error",
                    "message": (
                        f"{self._backend_noun} non risponde da diversi tentativi "
                        "consecutivi (circuito aperto). Riprova tra qualche istante."
                    ),
                })
                + '\n\n'
            )
            return

        self.last_tool_calls = []

        effective_model = self._resolve_model(model, agent_type)
        # Stesso ordine di `chat()` qui sopra: blocchi stabili, poi il
        # volatile `context_str` (fix m-4 della review totale della fetta --
        # la motivazione per esteso e' nel commento gemello in `chat()`; lo
        # streaming non e' una porta di servizio).
        system_parts = [BASE_SYSTEM_PROMPT]
        if system_prompt:
            system_parts.append(system_prompt)
        if restrict_to_home:
            system_parts.append(RESTRICT_PROMPT)
        # fetta E4 Task 6 ("un bot solo"): il parametro `require_confirmation`
        # stesso e' uscito -- vedi il commento gemello in chat() sopra.
        if response_mode == "compact":
            system_parts.append(COMPACT_PROMPT)
        elif response_mode == "minimal":
            system_parts.append(MINIMAL_PROMPT)
        if context_str:
            system_parts.append(context_str)

        messages: list[dict] = [{"role": "system", "content": "\n\n---\n\n".join(system_parts)}]
        for msg in (conversation_history or []):
            messages.append({"role": msg["role"], "content": str(msg["content"])})
        messages.append({"role": "user", "content": user_message})

        if tools is not None:
            # Il catalogo arriva gia' deciso dal chiamante -- stessa regola di
            # chat() (vedi il suo commento gemello).
            tools = list(tools)
        else:
            # fetta E3 Task 8: nessun catalogo di scorta da cui pescare --
            # vedi il commento gemello in claude_runner.chat(). Lo streaming
            # non e' una porta di servizio: stessa regola di chat().
            tools = []
        oai_tools = _to_openai_tools(tools) if tools else None
        tool_name_set = frozenset(t["name"] for t in tools)

        if self._local and tools:
            tool_names = ", ".join(t["name"] for t in tools)
            messages[0]["content"] += (
                f"\n\n---\n\nTool disponibili: {tool_names}.\n"
                "NON chiamare tool non presenti in questa lista."
            )

        max_iter = _OLLAMA_MAX_TOOL_ITERATIONS if self._local else MAX_TOOL_ITERATIONS
        try:
            for _ in range(max_iter):
                kwargs: dict = {
                    "model": effective_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": True,
                }
                if oai_tools:
                    kwargs["tools"] = oai_tools
                # Ollama-specific: vedi commento in chat() per think:false.
                if self._local:
                    kwargs["extra_body"] = {"think": False}

                try:
                    stream = await self._client.chat.completions.create(**kwargs)
                except _openai.RateLimitError as exc:
                    self._write_rejection(effective_model)
                    logger.error("OpenAI rate limit (stream): %s", exc)
                    upstream = parse_upstream_rate_limit(exc)
                    err_msg = upstream or "Rate limit — riprova tra poco."
                    yield f'data: {json.dumps({"type": "error", "message": err_msg})}\n\n'
                    return
                except _openai.APIError as exc:
                    # OpenRouter 402: see chat() for full rationale.
                    affordable = parse_afford_limit(exc)
                    if affordable and affordable < kwargs.get("max_tokens", 0):
                        logger.warning(
                            "OpenRouter 402 stream on %s: requested max_tokens=%d, "
                            "retrying with %d (key credit limit).",
                            effective_model, kwargs["max_tokens"], affordable,
                        )
                        kwargs["max_tokens"] = affordable
                        try:
                            stream = await self._client.chat.completions.create(**kwargs)
                        except _openai.APIError as retry_exc:
                            logger.error(
                                "OpenRouter 402 stream retry failed: %s", retry_exc,
                            )
                            err = (
                                f"Crediti OpenRouter insufficienti per max_tokens={max_tokens}. "
                                f"Riduci max_tokens dell'agente sotto {affordable} "
                                f"oppure aggiungi credito su openrouter.ai."
                            )
                            yield f'data: {json.dumps({"type": "error", "message": err})}\n\n'
                            return
                    else:
                        # review M3/#2: see chat() for full rationale — trip
                        # the breaker on connection-class failures so a dead
                        # endpoint fails fast on subsequent turns.
                        if _is_conn_error(exc):
                            self._record_conn_failure()
                        logger.error("OpenAI/Ollama API error (stream): %s", exc)
                        yield (
                "data: "
                f'{json.dumps({"type": "error", "message": "Errore temporaneo del servizio AI."})}'
                "\n\n"
                        )
                        return

                self._record_success()
                collected_text = ""
                finish_reason: str | None = None
                # {index: {id, name, args}} — assembla i frammenti tool-call dallo stream
                tc_fragments: dict[int, dict] = {}

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta

                    if delta.content:
                        collected_text += delta.content
                        yield f'data: {json.dumps({"type": "token", "text": delta.content})}\n\n'

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tc_fragments:
                                tc_fragments[idx] = {"id": "", "name": "", "args": ""}
                            if tc_delta.id:
                                tc_fragments[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc_fragments[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tc_fragments[idx]["args"] += tc_delta.function.arguments

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                if not tc_fragments:
                    # Risposta testuale finale — stream completato.
                    # Verifica leak di tool call come testo (Mistral/Hermes su
                    # OpenRouter): se rilevato, dì al frontend di scartare i
                    # token già renderizzati e mostra un errore esplicito,
                    # così la chat history non viene avvelenata al prossimo
                    # turno.
                    leaked = detect_leaked_tool_call(collected_text, tool_name_set)
                    if leaked:
                        logger.warning(
                            "Stream from %s leaked tool call '%s' as text content. "
                            "Sample: %r",
                            effective_model, leaked, collected_text[:160],
                        )
                        yield f'data: {json.dumps({"type": "discard_collected"})}\n\n'
                        yield (
                            "data: "
                            f'{json.dumps({"type": "error", "message": TOOL_LEAK_USER_MSG})}'
                            "\n\n"
                        )
                        return
                    if finish_reason == "length":
                        # review M3/#1: chat() surfaces _TRUNCATION_NOTICE
                        # when finish_reason=='length' (see the "else" branch
                        # below the tool_calls check there); this streaming
                        # path used to just `break` silently, leaving the
                        # client with a truncated response and no warning.
                        from ..claude_runner import _TRUNCATION_NOTICE
                        notice = f"\n\n{_TRUNCATION_NOTICE}"
                        yield f'data: {json.dumps({"type": "token", "text": notice})}\n\n'
                    break

                # Ci sono tool calls: eseguili e continua il loop
                tcs = sorted(tc_fragments.items())
                assistant_msg: dict = {"role": "assistant"}
                if collected_text:
                    assistant_msg["content"] = collected_text
                assistant_msg["tool_calls"] = [
                    {
                        "id": d["id"],
                        "type": "function",
                        "function": {"name": d["name"], "arguments": d["args"]},
                    }
                    for _, d in tcs
                ]
                messages.append(assistant_msg)

                for _, tc_data in tcs:
                    try:
                        tool_input = json.loads(tc_data["args"])
                    except json.JSONDecodeError as json_exc:
                        logger.warning(
                            "chat_stream tool %s: JSON non valido %r: %s",
                            tc_data["name"], tc_data["args"][:120], json_exc,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_data["id"],
                            "content": json.dumps({
                                "error": (
                                    f"Argomenti JSON non validi per '{tc_data['name']}'. "
                                    "Correggi il JSON e riprova."
                                )
                            }),
                        })
                        continue
                    if dispatcher is not None:
                        # DispatcherStrumenti (e affini): stessa interfaccia
                        # minima dispatch(nome, argomenti). fetta E4 Task 6:
                        # il ramo "dispatcher di scorta" (self._dispatcher) e'
                        # uscito -- vedi il commento gemello in chat().
                        result = await dispatcher.dispatch(tc_data["name"], tool_input)
                    else:
                        # ne' un dispatcher per-chiamata -- vedi il commento
                        # gemello in chat().
                        logger.debug(
                            "Strumento '%s' richiesto ma nessun dispatcher disponibile "
                            "(degradazione dichiarata, non un errore)", tc_data["name"])
                        result = {"error": f"Strumento '{tc_data['name']}' non disponibile."}
                    self.last_tool_calls.append({"tool": tc_data["name"], "input": tool_input})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_data["id"],
                        "content": json.dumps(result),
                    })
            else:
                # fetta "i riferimenti" (R4, Task 6): il `for...else` di
                # Python scatta SOLO se il ciclo si esaurisce senza mai
                # incontrare il `break` di qui sopra (quello che segna una
                # risposta testuale finale, `if not tc_fragments`) -- cioe'
                # esattamente quando il modello ha chiesto uno strumento in
                # OGNI iterazione fino al tetto, senza mai concludere. Prima
                # il generatore cadeva dritto sul "done" finale qui sotto
                # senza dire nulla: un done muto. Riusa la STESSA forma con
                # cui questo generatore segnala gia' gli altri errori (vedi
                # il ramo circuito aperto piu' sopra e l'`except` qui sotto)
                # invece di inventarne una nuova, e si ferma li' -- senza il
                # "done" finale, come gli altri rami d'errore. `self.
                # last_tool_calls` e' gia' in mano, riusato qui, non un
                # secondo tracciamento; solo i NOMI degli strumenti, mai gli
                # argomenti.
                logger.warning(
                    "chat_stream(): esaurite %d iterazioni senza risposta finale -- "
                    "strumenti chiamati: %s",
                    max_iter, [c["tool"] for c in self.last_tool_calls],
                )
                yield (
                    "data: "
                    f'{json.dumps({"type": "error", "message": _MAX_ITERATIONS_NOTICE})}'
                    "\n\n"
                )
                return

        except Exception as exc:
            logger.error("chat_stream error: %s", exc)
            yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        # fetta E4 Task 6: il campo `agent_id` esce -- vedi il commento
        # gemello nel docstring di ClaudeRunner.chat_stream() (nessun lettore
        # in static/, grep verificato).
        yield f'data: {json.dumps({"type": "done", "tool_calls": self.last_tool_calls})}\n\n'

    # fetta E3 Task 8: `run_with_actions` e' uscito -- vedi il commento
    # gemello in claude_runner.py (stesso motivo: il suo unico chiamante, la
    # Sentinella, e' uscito al Task 7 di questa fetta).
