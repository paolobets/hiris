from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any

from .claude_runner import (
    RunnerBackendError,
    _current_thinking_blocks,
    _current_tool_calls,
    _current_tool_leaked,
    _current_truncated,
    _current_unanswered,
)
from .providers import chain_members

logger = logging.getLogger(__name__)


#: Chi ha risposto in QUESTA chiamata. Il router e' costruito una volta e
#: vive quanto l'add-on: un attributo su di lui farebbe dire al turno
#: notturno dell'analista chi ha risposto alla chat del proprietario, se i
#: due si accavallano. E' la stessa cura, e lo stesso meccanismo, di
#: `last_tool_calls` e della misura del carico.
#:
#: Vuota finche' nessuno ha risposto: un nome presente PRIMA della chiamata
#: sarebbe quello del turno precedente, e si leggerebbe come un fatto.
_current_provider: ContextVar[str] = ContextVar(
    "hiris_provider_corrente", default="")


class LLMRouter:
    """Instrada le chiamate al modello lungo la catena, ripiegando.

    I backend arrivano per nome di provider (`LLMRouter(claude=..., ollama=...)`)
    e i nomi ammessi sono quelli che la tabella dei provider governa da
    `chain_order` (`providers.chain_members()`): un nome che la tabella non
    conosce e' un errore di chi costruisce, non un backend da ignorare. Se un
    backend solleva, si prova il successivo della catena.

    `model_chain` e' la catena che l'utente ha ordinato, gia' filtrata a chi
    puo' rispondere (`providers.providers_in_chain`, vedi `server.py`). E'
    OBBLIGATORIA, e vale per quello che dice anche quando e' vuota: una catena
    vuota significa «nessuno in catena», non «ripiega su un ordine di
    strategia».

    **Il ramo «libreria» e' uscito** (Tappa 7, Task 9; voce M-07): `strategy`,
    `chat_policy`, `_norm_policy` e `_STRATEGY_ORDER` servivano solo quando
    nessuno passava una catena, e `server.py` la passa sempre. I tre ordini
    sono rimasti come i tre preset della pagina Modelli (`providers.PRESETS`),
    che e' l'unico posto in cui erano ancora una decisione.
    """

    def __init__(
        self,
        *,
        model_chain: list[str],
        registry: Any = None,
        **backends: Any,
    ) -> None:
        # `registro` è `provider_occurrences.OccurrenceRegistry` (app["occurrence_registry"]).
        # Facoltativo perché `LLMRouter` è costruito anche da test e da codice
        # di libreria che non ha una app intorno; quando c'è, ogni giro del
        # ciclo di ripiego ci scrive che cosa ha visto. I runner non lo
        # ricevono: il turno della catena passa di qui, e due scrittori della
        # stessa osservazione sarebbero due rappresentazioni dello stesso
        # fatto. I turni del ponte, che di qui non passano, li registra chi li
        # raccoglie (`server.py`, `api/`).
        self._registry = registry
        members = chain_members()
        unknown = sorted(set(backends) - set(members))
        if unknown:
            raise TypeError(
                f"LLMRouter: provider sconosciuti alla tabella {unknown}; "
                f"ammessi {list(members)}")
        self._backends = dict(backends)
        # Una catena ESPLICITA vale per quello che dice, anche quando è vuota:
        # ricadendo su un ordine di riserva, la pagina direbbe «la catena è
        # vuota, HIRIS non può rispondere» mentre il router risponde con ogni
        # provider che ha una credenziale.
        self._chat_policy = [n for n in model_chain if n in members]

    def _backend_map(self) -> dict[str, Any]:
        return {name: self._backends.get(name) for name in chain_members()}

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

    # ------------------------------------------------------------------
    # LLM interface (mirrors ClaudeRunner)
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        """Chi ha risposto in questa chiamata, o "" se ancora nessuno.

        La legge `steering.misura_turno`: chi misura chiama il router, che e'
        un proxy, e solo il router sa quale backend ha risposto.
        """
        return _current_provider.get()

    async def chat(self, **kwargs) -> str:
        # Si chiede sempre `model="auto"` (tutti i chiamanti del prodotto, misurato
        # il 02/10/2026): il turno passa dal ciclo di ripiego, nell'ordine della
        # catena. Il ramo del modello esplicito, che sceglieva un runner una volta
        # sola e non ripiegava, e' uscito con la Tappa 0 (voce M-05 del registro).
        # Il segnale di troncatura si azzera QUI, non solo nei backend: se
        # nessuno risponde, il router torna un testo suo, e il segnale di una
        # chiamata precedente dello stesso compito si leggerebbe come di
        # questa.
        _current_truncated.set(False)
        _current_tool_leaked.set(False)
        _current_unanswered.set(False)
        ordered = self._ordered_backends_with_name()
        if not ordered:
            # Da questa fetta e' uno stato RAGGIUNGIBILE e con un significato:
            # la catena e' vuota (nessuno ce l'ha messo) oppure i nomi che
            # porta non hanno un backend costruito. «Riprova tra poco» sarebbe
            # una parola piu' larga del fatto -- non passa da solo.
            logger.warning("Nessun provider in catena: chat(model=auto) non ha a chi chiedere")
            _current_unanswered.set(True)
            return ("Nessun provider utilizzabile in catena: HIRIS non ha a chi "
                    "chiedere. Apri la pagina Modelli e mettine almeno uno in "
                    "catena.")
        last_friendly: str | None = None
        for backend_name, runner in ordered:
            # Il ciclo di ripiego è dove HIRIS vede come si comporta un
            # provider della catena: ogni esito va nel registro, così la
            # pagina Modelli può dire «sta rifiutando da quaranta richieste» e
            # non solo «è primo in catena».
            start = time.monotonic()
            try:
                answer = await runner.chat(**kwargs)
            except RunnerBackendError as exc:
                logger.warning("Backend %s failed, trying next: %s", backend_name, exc)
                if self._registry is not None:
                    self._registry.fallimento(
                        backend_name, family=getattr(exc, "family", "altro"),
                        code=getattr(exc, "code", None),
                        # Cio' che il PROVIDER ha detto, non la frase della
                        # chat: e' cio' che la pagina cita (G36-1).
                        message=getattr(exc, "said", None) or "",
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
                # **Chi ha risposto si dichiara qui**, dove si sa: e' il
                # backend che NON ha sollevato, non il primo della catena.
                # Leggere il primo direbbe «ha risposto claude» proprio nel
                # caso interessante, quello in cui claude non ha risposto.
                _current_provider.set(backend_name)
                return answer
        _current_unanswered.set(True)
        return last_friendly or "Tutti i provider AI non disponibili. Riprova tra poco."

    # ------------------------------------------------------------------
    # Per-call state (ContextVar-backed)
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
    def last_unanswered(self) -> bool:
        """Se nessun backend ha risposto alla chiamata che ha appena
        attraversato il router, in QUESTO compito: la frase restituita era la
        sua, non di un modello. La legge `steering.misura_turno`, che allora
        registra il turno `fallito`.

        Stessa ContextVar dei runner, che pero' non la accendono mai: un
        runner che non risponde solleva, e `misura_turno` lo registra
        `fallito` gia' da se'."""
        return _current_unanswered.get()

    @property
    def last_truncated(self) -> bool:
        """Se la risposta che ha appena attraversato il router, in QUESTO
        compito, e' stata troncata dal provider. Stessa ContextVar dei runner:
        il backend che ha risposto e' l'ultimo ad averla scritta, perche'
        ognuno la azzera all'ingresso di `chat()`."""
        return _current_truncated.get()

    @property
    def last_tool_leaked(self) -> bool:
        """Se la risposta che ha appena attraversato il router, in QUESTO
        compito, portava uno strumento «scappato» come testo (B22). Stessa
        ContextVar dei runner, come `last_truncated`."""
        return _current_tool_leaked.get()

    @property
    def last_thinking_blocks(self) -> list:
        """Extended-thinking blocks from the call that just ran through THIS
        asyncio Task. See last_tool_calls above — same ContextVar-backed
        isolation, shared with ClaudeRunner/OpenAICompatRunner."""
        val = _current_thinking_blocks.get()
        return val if val is not None else []
