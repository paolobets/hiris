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
    COMPACT_PROMPT,
    MINIMAL_PROMPT,
    RESTRICT_PROMPT,
    RunnerBackendError,
    _current_tool_calls,
    _current_tool_leaked,
    _current_truncated,
    _current_unanswered,
    _misura_corrente,
    _PerCallFlag,
    _PerCallList,
    dispatch_calls,
)
from ..model_resolution import failure_reply
from ..provider_occurrences import error_family, provider_said
from ..providers import OLLAMA, OPENAI
from ..usage.giro import openai_turn_tokens, pesa_carico, testo_canonico
from .pricing import get_price as _prezzo

# Circuit-breaker: after this many consecutive connection-class failures, skip
# the backend for the cooldown instead of hammering a dead endpoint. The
# observed failure mode was a stale Ollama tunnel (DNS no longer resolving)
# flooding the log with "Connection error" once per classify_entities call.
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SEC = 60


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
    lettore, `provider_occurrences.error_family`, che le chiede la stessa cosa per
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

TOOL_LEAK_USER_MSG = (
    "Il modello selezionato non gestisce correttamente i tool tramite questo "
    "provider (la chiamata al tool è arrivata come testo invece che come "
    "tool_call). Cambia modello nella pagina Modelli — preferisci quelli con "
    "tool use nativo OpenAI."
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
    m = LEAKED_TOOL_NAME_RE.match(content)
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
            # difetto della diagnosi inventata di `action/actuator.py` («probabile
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


def _pesa_carico_catena(messages: list, tools, context_str: str) -> dict:
    """Di cosa e' fatto il carico di UN giro sulla catena, nella forma OpenAI.

    Qui la casa compone **un solo messaggio di sistema**, con il nucleo
    DENTRO (`system_parts.append(context_str)`): si separano i messaggi per
    ruolo -- `system`, `tool` (i risultati), il resto -- e la regola e' la
    stessa di ogni canale (`usage.giro.pesa_carico`), che toglie il nucleo
    dal testo dell'impronta.
    """
    by_role: dict[str, list] = {"system": [], "tool": [], "altro": []}
    for msg in messages or []:
        role = msg.get("role")
        by_role[role if role in ("system", "tool") else "altro"].append(msg.get("content"))
    return pesa_carico(system=[testo_canonico(c) for c in by_role["system"]],
                       core=context_str, conversation=by_role["altro"],
                       results=by_role["tool"], tools=tools)


def _cache_counts(usage: Any) -> tuple[int, int]:
    """I token letti dalla cache e quelli scritti, presi DOVE stanno davvero.

    **Misurato il 09/09/2026, due fonti che concordano.** In `openai` 3.1.0
    (la versione installata) `CompletionUsage` non ha nessun `cached_tokens`
    al primo livello: i due contatori vivono dentro `prompt_tokens_details`
    (`openai.types.completion_usage.PromptTokensDetails`, campi
    `cached_tokens` e `cache_write_tokens`) -- verificato istanziando il tipo,
    con 80 token cachati un `getattr(usage, "cached_tokens", 0)` risponde 0.
    OpenRouter documenta la stessa identica forma (Prompt Caching):
    `usage.prompt_tokens_details.{cached_tokens, cache_write_tokens}`.

    Fino all'09/09/2026 si leggevano dal primo livello, quindi `cache_read` e
    `cache_write` uscivano SEMPRE zero e quello zero arrivava all'archivio dei
    consumi marcato `misurato`: un numero mai misurato scritto come misurato
    (audit delle fondamenta, rilievo 8).

    `prompt_tokens_details` assente significa «il fornitore non ha dichiarato
    niente sulla cache» -- Ollama, e OpenAI quando nessun prefisso e' stato
    riusato. Zero e' la risposta giusta, ed e' l'unica che l'archivio dei
    consumi sappia rappresentare: `UsageStore.log` prende due interi, non due
    «forse».

    **Cosa questa funzione NON corregge, ed e' scritto qui perche' non si
    perda.** Il costo (`_track_usage`, poco sotto) moltiplica `prompt_tokens`
    -- che secondo OpenAI COMPRENDE i token cachati -- per il prezzo pieno
    dell'input, perche' `backends/pricing.PRICING` porta `cache_read`/
    `cache_write` solo per i modelli Claude e non per i `gpt-*`. Non e' un
    numero inventato, e' il listino che abbiamo applicato per intero; ma un
    input cachato viene fatturato a prezzo pieno finche' quel listino non
    impara le due tariffe. E' un debito della tabella dei prezzi, non di
    questa lettura.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0, 0
    return (getattr(details, "cached_tokens", 0) or 0,
            getattr(details, "cache_write_tokens", 0) or 0)


class OpenAICompatRunner:
    """Agentic LLM runner for OpenAI-compatible APIs (OpenAI cloud + Ollama local)."""

    # Per-call, per-asyncio-Task isolated — shares the SAME ContextVar as
    # ClaudeRunner (review A/#3 — see claude_runner.py's module comment for
    # the full rationale). No last_thinking_blocks here: OpenAI-compatible
    # backends don't support Anthropic Extended Thinking (thinking_budget is
    # accepted-and-ignored in chat() below).
    last_tool_calls = _PerCallList(_current_tool_calls)
    last_truncated = _PerCallFlag(_current_truncated)
    last_tool_leaked = _PerCallFlag(_current_tool_leaked)
    last_unanswered = _PerCallFlag(_current_unanswered)

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
        # `local` e' la MODALITA' («questo e' Ollama», «valida l'URL»). Il
        # modello e' una DECISIONE dell'utente, cambia da una PUT all'altra e
        # si LEGGE al momento dell'uso (`read_model`) invece di essere cotto
        # nel costruttore: cosi' cambiare il modello di Ollama ha effetto
        # senza riavviare l'add-on.
        if local:
            from ..backends.ollama import _validate_ollama_url
            _validate_ollama_url(base_url)
        self._api_key = api_key
        self._base_url = base_url
        self._local = local
        self._read_model = read_model
        self._is_cloud = not local  # True = cloud (OpenAI); False = local (Ollama)
        # Il runner non conosce l'archivio dei consumi: conosce una funzione.
        # Stessa disciplina di `read_model`. Ed e' la regola non negoziabile
        # di CLAUDE.md: un kwarg nuovo di `ClaudeRunner` lo accetta ANCHE
        # questa classe, o i backend non-Claude si rompono in silenzio.
        self._log_usage = log_usage
        # Il nome AUTOREVOLE del provider. `type(self).__name__` non lo
        # distingue: `OpenRouterRunner` e' una sottoclasse di questa classe, e
        # un consumo di OpenRouter finirebbe scritto sulla riga di OpenAI --
        # lo stesso difetto che `LLMRouter._ordered_backends_with_name` e' gia'
        # stato scritto per evitare nel registro degli esiti, e per la stessa
        # ragione.
        self.provider_name = OLLAMA.id if local else OPENAI.id
        # Circuit-breaker message noun, so a cloud backend doesn't report
        # itself as "il backend locale" (review backlog #7).
        self._backend_noun = "Il servizio AI" if self._is_cloud else "Il backend locale"
        # Ollama su hardware lento: timeout esplicito per evitare hang infiniti
        # (`OLLAMA.reply_timeout_s`, il valore della tabella dei provider).
        # Cloud: il predefinito dell'SDK, CHIESTO all'SDK e non ricopiato
        # (Tappa 7 T10, F-16): `openai` 3.26.0, `_constants.py`, letto il
        # 07/10/2026 -- `DEFAULT_TIMEOUT = Timeout(timeout=600, connect=5.0)`.
        # Fino ad allora qui c'era un `600.0` senza unita' e senza fonte. Il
        # numero arriva dal chiamante -- per Ollama e' `ollama.timeout_s`
        # dell'archivio, la stessa casa da cui la pagina Modelli lo mostra:
        # fino a questa fetta veniva da `OLLAMA_REQUEST_TIMEOUT`, cioe' una
        # SECONDA rappresentazione dello stesso numero accanto alla copia
        # d'archivio (invariante 1), e le due potevano dire cose diverse.
        self._timeout_s = 0.0
        if not timeout_s:
            import openai as _openai
            timeout_s = (OLLAMA.reply_timeout_s or 0) if local else _openai.DEFAULT_TIMEOUT.read
        self.apply_timeout(float(timeout_s))
        # Circuit-breaker state for connection-class failures (dead endpoint).
        self._conn_fail_count = 0
        self._circuit_open_until = 0.0
        # last_tool_calls is intentionally NOT initialized here — it's a
        # per-call/per-Task class-level descriptor (see above); chat() resets
        # it at the start of every call, scoped to the calling Task.
        # Il consumo non si somma qui: si scrive in `usage/store.py`
        # attraverso `log_usage`, una riga per modello.

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def _cost_state(self, usage: Any, model: str) -> tuple[str, float | None, int, int]:
        """Stato del costo, costo, token IN e OUT -- per UNA `usage` gia'
        presente (il chiamante ha gia' escluso `None`).

        Un solo calcolo del listino e dello stato, una volta per giro
        (`_track_usage`): lo stesso valore va all'archivio dei consumi e alla
        misura del giro. Erano due chiamate della stessa regola (D-60), e due
        copie della stessa regola sono gia' costate care a questo prodotto
        una volta (vedi il commento sul difetto OpenRouter, sotto in
        `_track_usage`)."""
        from ..usage.vocabulary import cost_state_and_value

        inp = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        prices = _prezzo(model)
        listino = (inp * prices["input"] + out * prices["output"]) / 1_000_000
        state, cost = cost_state_and_value(self.provider_name, model,
                                           cost_dichiarato=getattr(usage, "cost", None),
                                           cost_da_listino=listino)
        return state, cost, inp, out

    def _track_usage(self, response: Any, model: str, *,
                     measuring: bool) -> float | None:
        """Scrive il consumo di UNA risposta nell'archivio dei consumi
        (`log_usage`): token, cache, costo e stato del costo, per modello. E
        torna il costo, calcolato qui UNA volta, per la misura del giro
        (D-60): la misura non dipende dal gancio dei consumi (spec «le misure
        complete» §3), per questo il costo si calcola anche senza archivio
        quando qualcuno misura (`measuring`).

        Una risposta senza `usage` non si stima: non si scrive niente, e lo
        si dichiara nel log. Un guasto dell'archivio non fa cadere il turno
        (`usage.store.log_safely`, S-11).
        """
        usage = getattr(response, "usage", None)
        if not usage:
            logger.debug("Model %s: risposta senza 'usage' -- nessun contatore aggiornato", model)
            return None
        if self._log_usage is None and not measuring:
            return None

        # OpenRouter dichiara il costo VERO in ogni risposta -- `usage.cost`,
        # sempre presente, anche in streaming (Usage Accounting, verificato
        # sulla loro documentazione il 21/08/2026). Leggerlo trasforma in un
        # fatto quella che era una stima, e la stima valeva ZERO: `_prezzo` non
        # conosce nessun identificativo OpenRouter e cadeva su `_default`. E'
        # il difetto da cui nasce l'intera fetta.
        state, cost, inp, out = self._cost_state(usage, model)
        cache_read, cache_write = _cache_counts(usage)
        from ..usage.store import log_safely

        log_safely(
            self._log_usage, self.provider_name, model, token_in=inp, token_out=out,
            cache_read=cache_read, cache_write=cache_write,
            cost_usd=cost, cost_state=state, now=time.time())
        return cost

    def _write_rejection(self, model: str) -> None:
        """Un 429 si conta sulla riga del modello che l'ha preso.

        `richieste=0`: un rifiuto non e' una richiesta servita. Un numero solo
        per tutto il prodotto non direbbe CHI stia rifiutando -- che e'
        l'unica cosa che serve sapere quando succede.
        """
        from ..usage.store import log_safely

        log_safely(
            self._log_usage, self.provider_name, model, richieste=0, errori_rate_limit=1,
            cost_usd=None, cost_state="non_noto", now=time.time())

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------

    def _chosen_model(self) -> str:
        """Il modello scelto ADESSO, letto dove vive (l'archivio)."""
        return (self._read_model() if self._read_model else "") or ""

    def _resolve_model(self, model: str) -> str:
        """Il modello di questo turno. Il mestiere non lo sceglie (Tappa 7,
        T10; D11a): fino ad allora, con `"auto"` e nessuna scelta, la chat
        andava su `gpt-4o` e osservatore e promesse su `gpt-4o-mini`, mentre
        analista e proponente -- che il mestiere non lo dicevano -- su
        `gpt-4o`. Adesso tutti il modello scelto, o l'automatico del
        provider (`OPENAI.auto_model`)."""
        # Ollama: il modello scelto vince SEMPRE, anche su un modello passato
        # esplicitamente -- era gia' cosi' (`if self._fixed_model: return
        # self._fixed_model` come primo ramo) e resta, perche' l'istanza locale
        # ne ha scaricato uno solo e chiedergliene un altro fallirebbe. La sola
        # differenza e' che adesso il valore si LEGGE.
        chosen = self._chosen_model()
        if self._local:
            return chosen
        if model == "auto":
            return chosen or OPENAI.auto_model
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
        # Ollama: nessun ritentativo dell'SDK -- un'istanza locale lenta che
        # ritenta moltiplica l'attesa del turno, e il primo errore va loggato
        # e restituito. Cloud: i predefiniti dell'SDK (ritentativi e tempo di
        # connessione), chiesti all'SDK come il tempo di risposta in
        # `__init__`: `DEFAULT_MAX_RETRIES = 2`, `connect=5.0` (stessa
        # lettura del 07/10/2026).
        self._client = _openai.AsyncOpenAI(
            api_key=self._api_key, base_url=self._base_url,
            timeout=_httpx.Timeout(seconds, connect=_openai.DEFAULT_TIMEOUT.connect),
            max_retries=0 if self._local else _openai.DEFAULT_MAX_RETRIES,
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

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: list[dict] | None = None,
        model: str = "auto",
        max_tokens: int = 4096,
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

        # review M3/#2: the agentic loop below did not consult the
        # connection-failure circuit breaker, so a dead Ollama endpoint was
        # retried at full timeout every single turn instead of failing fast.
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
        self.last_truncated = False
        self.last_tool_leaked = False
        self.last_unanswered = False

        effective_model = self._resolve_model(model)

        # Build system message (OpenAI uses a single system message)
        #
        # Fix della review totale della fetta "il ponte riceve il core"
        # (parita' A, m-4): qui i modificatori stavano DOPO `context_str`, e
        # in `claude_runner.py::ClaudeRunner.chat` stanno PRIMA, con un
        # commento che dichiara l'ordine obbligatorio ("must precede
        # context_str"). Due composizioni divergenti della stessa cosa, con
        # l'invariante scritta in un posto solo. Verificato prima di
        # muovere: l'invariante e' VERA e ha una ragione meccanica, cioe' che
        # i blocchi STABILI (BASE, persona, modificatori -- fissi per
        # configurazione) devono stare prima del blocco VOLATILE
        # (`context_str`, che cambia a ogni turno perche' e' il core). Di
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
        # `tests/test_composition_order.py`.
        # Il compositore unico, come `ClaudeRunner.chat` (Tappa 6, Task 7).
        from ..steering import compose_base

        if tools is not None:
            tools = list(tools)
        system_parts = [compose_base(t["name"] for t in tools or ())]
        if system_prompt:
            system_parts.append(system_prompt)
        # I modificatori di comportamento -- stabili per configurazione,
        # DEVONO precedere `context_str` (vedi sopra).
        if restrict_to_home:
            system_parts.append(RESTRICT_PROMPT)
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
            # ClaudeRunner.chat().
            tools = list(tools)
        else:
            # Nessun catalogo di scorta da cui pescare.
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
            # **Il giro si conta e si pesa PRIMA di partire** (misure,
            # 23/09/2026), come nel gemello di `claude_runner`. Qui la casa
            # compone UN SOLO messaggio di sistema (e' la forma di OpenAI),
            # quindi la guida e il core si separano sul `context_str` che il
            # chiamante ha passato -- non su blocchi distinti.
            #
            # E questo percorso conta piu' dell'altro, oggi: il ponte e'
            # spento, e il 74% della materia in ingresso di questa catena si
            # paga a prezzo pieno.
            _raccoglitore = _misura_corrente()
            if _raccoglitore is not None:
                _raccoglitore(iter_idx + 1,
                              _pesa_carico_catena(messages, oai_tools,
                                                  context_str))
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
                family, code = error_family(exc), _status_code(exc) or 429
                said = provider_said(exc)
                raise RunnerBackendError(
                    upstream or failure_reply(family, code, said), family=family,
                    code=code, said=said,
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
                        # Nessuna azione impossibile (X-64): fino al 07/10/2026
                        # la frase chiedeva di ridurre «max_tokens
                        # dell’agente», un numero che nessuna pagina espone.
                        raise RunnerBackendError(
                            f"Crediti OpenRouter insufficienti: la risposta chiede fino a "
                            f"{max_tokens} token e il credito ne copre meno di "
                            f"{affordable}. Aggiungi credito su openrouter.ai, oppure "
                            f"scegli un modello meno costoso nella pagina Modelli.",
                            family=error_family(retry_exc),
                            code=_status_code(retry_exc),
                        ) from retry_exc
                else:
                    # review M3/#2: connection-class failures (dead endpoint)
                    # must trip the circuit breaker, so a
                    # stale Ollama tunnel fails fast on the NEXT turn instead
                    # of being retried at full timeout forever.
                    if _is_conn_error(exc):
                        self._record_conn_failure()
                    logger.error("OpenAI/Ollama API error: %s", exc)
                    # Il codice e la famiglia smettono di andare persi, e la
                    # frase li dice (`failure_reply`, S-37). Era questo il
                    # punto in cui «404, quel modello non esiste più» e «402,
                    # credito finito» diventavano la stessa identica riga.
                    family, code = error_family(exc), _status_code(exc)
                    said = provider_said(exc)
                    raise RunnerBackendError(
                        failure_reply(family, code, said), family=family, code=code,
                        said=said,
                    ) from exc

            self._record_success()
            _raccoglitore = _misura_corrente()
            cost_usd = self._track_usage(response, effective_model,
                                         measuring=_raccoglitore is not None)

            # La seconda consegna del giro: i token, dopo la risposta.
            if _raccoglitore is not None:
                _raccoglitore(iter_idx + 1, {
                    **openai_turn_tokens(getattr(response, "usage", None)),
                    "cost_usd": cost_usd,
                    # Chi ha risposto con QUALE modello: lo sa solo questo
                    # punto (la chat non lo passa all'imbuto).
                    "model": effective_model})

            choice = response.choices[0]

            # **Le chiamate di strumento si guardano, non il motivo**
            # (Tappa 7, T10; S-14): una risposta che porta `tool_calls` con
            # `finish_reason == "stop"` finiva in questo ramo come risposta
            # finale, e le chiamate si perdevano -- il turno restituiva un
            # testo spesso vuoto mentre il modello aspettava i risultati. Il
            # caso e' dedotto dalla lettura del codice (registro, S-14), non
            # misurato su un provider: per questo la regola guarda la cosa
            # che conta, le chiamate, e non presume quale provider la produca.
            if choice.finish_reason == "stop" and not choice.message.tool_calls:
                raw_content = choice.message.content or ""
                leaked = detect_leaked_tool_call(raw_content, tool_name_set)
                if leaked:
                    logger.warning(
                        "Model %s leaked tool call '%s' as text content "
                        "(provider does not translate native tool tokens). Sample: %r",
                        effective_model, leaked, raw_content[:160],
                    )
                    self.last_tool_leaked = True  # B22: un esito suo
                    return TOOL_LEAK_USER_MSG
                return raw_content

            if choice.finish_reason in ("tool_calls", "stop"):
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
                # Gli argomenti si leggono prima: un JSON rotto e' una
                # risposta pronta, non una chiamata. Le altre partono con la
                # regola dei due runner (`dispatch_calls`: le letture insieme,
                # le scritture una alla volta), e i risultati tornano al
                # modello nell'ordine delle sue chiamate.
                answers: list = [None] * len(tool_calls)
                to_serve: list[tuple[int, str, Any]] = []
                for index, tc in enumerate(tool_calls):
                    try:
                        tool_input = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as json_exc:
                        logger.warning(
                            "Tool %s: argomenti JSON non validi %r: %s",
                            tc.function.name, tc.function.arguments[:120], json_exc,
                        )
                        answers[index] = {
                            "error": (
                                f"Argomenti JSON non validi per '{tc.function.name}'. "
                                "Correggi il JSON e riprova."
                            )
                        }
                        continue
                    to_serve.append((index, tc.function.name, tool_input))
                served = await dispatch_calls(
                    dispatcher, [(name, args) for _, name, args in to_serve])
                for (index, name, tool_input), result in zip(to_serve, served, strict=True):
                    answers[index] = result
                    self.last_tool_calls.append({"tool": name, "input": tool_input})
                for tc, result in zip(tool_calls, answers, strict=True):
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
                    # E lo si DICE (D-58): la fonte di `"length"` e' scritta
                    # accanto a `_current_truncated` in `claude_runner`.
                    self.last_truncated = True
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
                    self.last_tool_leaked = True  # B22: un esito suo
                    return TOOL_LEAK_USER_MSG
                return raw_content

        # fetta "i riferimenti" (R4, Task 6): l'esaurimento non e' muto, come
        # in `ClaudeRunner.chat()`. `self.
        # last_tool_calls` e' gia' in mano, riusato qui, non un secondo
        # tracciamento; solo i NOMI degli strumenti, mai gli argomenti.
        logger.warning(
            "chat(): esaurite %d iterazioni senza risposta finale -- strumenti chiamati: %s",
            max_iter, [c["tool"] for c in self.last_tool_calls],
        )
        return _MAX_ITERATIONS_NOTICE
