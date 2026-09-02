from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.backends.base import LLMBackend
from hiris.app.backends.ollama import OllamaBackend
from hiris.app.claude_runner import (
    RunnerBackendError,
    _current_thinking_blocks,
    _current_tool_calls,
)
from hiris.app.llm_router import LLMRouter


def test_llm_backend_is_abstract():
    import inspect
    assert inspect.isabstract(LLMBackend)


@pytest.mark.asyncio
async def test_ollama_backend_simple_chat():
    backend = OllamaBackend(url="http://localhost:11434", model="llama3.2")
    mock_resp_data = {
        "message": {
            "content": (
                '{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}'
            )
        }
    }
    with patch("aiohttp.ClientSession") as MockSession:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.json = AsyncMock(return_value=mock_resp_data)
        ctx.raise_for_status = MagicMock()
        session_inst = MagicMock()
        session_inst.__aenter__ = AsyncMock(return_value=session_inst)
        session_inst.__aexit__ = AsyncMock(return_value=False)
        session_inst.post = MagicMock(return_value=ctx)
        MockSession.return_value = session_inst

        result = await backend.simple_chat([{"role": "user", "content": "classify"}])
        assert isinstance(result, str)
        assert "energy_meter" in result


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    runner.chat = AsyncMock(return_value="response text")
    runner.simple_chat = AsyncMock(
        return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}'
    )
    runner.last_tool_calls = []
    runner.total_input_tokens = 10
    runner.total_output_tokens = 5
    runner.total_requests = 1
    runner.total_cost_usd = 0.001
    runner.total_rate_limit_errors = 0
    runner.usage_last_reset = "2026-04-22T00:00:00Z"
    runner.reset_usage = MagicMock()
    return runner


@pytest.mark.asyncio
async def test_router_chat_delegates_to_runner(mock_runner):
    router = LLMRouter(claude=mock_runner)
    result = await router.chat(user_message="hello", system_prompt="sys")
    mock_runner.chat.assert_awaited_once()
    assert result == "response text"


# fetta «i consumi, per modello» (22/08/2026): qui viveva il test che
# pinnava le sei proprieta' aggreganti del router (`total_input_tokens` e
# compagnia) e `reset_usage`. Sono uscite: sommavano i contatori dei runner,
# e quella somma buttava via per costruzione l'unica cosa che serviva
# sapere -- DI CHI fosse il consumo. Adesso lo sa `usage/store.py`.


def test_router_last_tool_calls_reflects_current_call_not_stale_backend(mock_runner):
    """Review A/#3: LLMRouter.last_tool_calls must proxy the shared per-call
    ContextVar (the exact buffer ClaudeRunner/OpenAICompatRunner.chat()
    populate), not scan registered backends for "whichever has a non-empty
    list". The old scan could return a totally different caller's tool
    calls than the one that actually just ran through this router — a mock
    backend's stale/unrelated `last_tool_calls` attribute must NOT leak
    through the router property."""
    mock_runner.last_tool_calls = [{"tool": "stale_backend_attr", "input": {}}]
    router = LLMRouter(claude=mock_runner)
    token = _current_tool_calls.set([{"tool": "get_home_status", "input": {}}])
    try:
        assert router.last_tool_calls == [{"tool": "get_home_status", "input": {}}]
    finally:
        _current_tool_calls.reset(token)


def test_router_last_thinking_blocks_reflects_current_call(mock_runner):
    """LLMRouter previously had NO last_thinking_blocks property at all, so
    handlers_chat.py's `getattr(runner, "last_thinking_blocks", None)`
    silently returned None whenever chat went through the router — the
    debug payload's thinking_blocks was always empty. Now it proxies the
    same shared per-call ContextVar as ClaudeRunner."""
    router = LLMRouter(claude=mock_runner)
    assert router.last_thinking_blocks == []
    token = _current_thinking_blocks.set(["step 1: ..."])
    try:
        assert router.last_thinking_blocks == ["step 1: ..."]
    finally:
        _current_thinking_blocks.reset(token)


def test_router_strategy_defaults_to_balanced(mock_runner):
    router = LLMRouter(claude=mock_runner)
    assert router._strategy == "balanced"


def test_router_strategy_invalid_falls_back_to_balanced(mock_runner):
    router = LLMRouter(claude=mock_runner, strategy="unknown_strategy")
    assert router._strategy == "balanced"


def test_router_strategy_cost_first_orders_ollama_first(mock_runner):
    mock_ollama = MagicMock()
    mock_ollama.chat = AsyncMock(return_value="ollama response")
    router = LLMRouter(claude=mock_runner, ollama=mock_ollama, strategy="cost_first")
    backends = router._ordered_backends()
    assert backends[0] is mock_ollama
    assert backends[1] is mock_runner


def test_router_strategy_quality_first_orders_claude_first(mock_runner):
    mock_ollama = MagicMock()
    router = LLMRouter(claude=mock_runner, ollama=mock_ollama, strategy="quality_first")
    backends = router._ordered_backends()
    assert backends[0] is mock_runner
    assert backends[1] is mock_ollama


@pytest.mark.asyncio
async def test_router_chat_fallback_on_exception(mock_runner):
    failing_runner = MagicMock()
    failing_runner.chat = AsyncMock(side_effect=Exception("backend down"))
    mock_ollama = MagicMock()
    mock_ollama.chat = AsyncMock(return_value="ollama fallback")
    router = LLMRouter(claude=failing_runner, ollama=mock_ollama, strategy="quality_first")
    result = await router.chat(user_message="hello", model="auto")
    assert result == "ollama fallback"
    failing_runner.chat.assert_awaited_once()
    mock_ollama.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_chat_all_fail_returns_error_message(mock_runner):
    failing_runner = MagicMock()
    failing_runner.chat = AsyncMock(side_effect=Exception("down"))
    router = LLMRouter(claude=failing_runner, strategy="balanced")
    result = await router.chat(user_message="hello", model="auto")
    assert "non disponibili" in result


# ---------------------------------------------------------------------------
# Review C/#13: runners now RAISE RunnerBackendError on API failure instead
# of returning a friendly string — these prove the fallback loop actually
# engages on that exception (it was previously dead code: a returned string
# never raised, so the primary "succeeded" and the healthy secondary was
# never tried).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_chat_fails_over_on_runner_backend_error(mock_runner):
    """Primary raises RunnerBackendError (e.g. rate limit) -> router tries
    the next configured backend and returns ITS reply, not a degraded string.
    Fails on the pre-fix code, where chat() swallowed the API error into a
    returned string and the fallback loop never ran."""
    failing_runner = MagicMock()
    failing_runner.chat = AsyncMock(
        side_effect=RunnerBackendError("Errore temporaneo del servizio AI. Riprova tra poco.")
    )
    mock_ollama = MagicMock()
    mock_ollama.chat = AsyncMock(return_value="ollama fallback")
    router = LLMRouter(claude=failing_runner, ollama=mock_ollama, strategy="quality_first")
    result = await router.chat(user_message="hello", model="auto")
    assert result == "ollama fallback"
    failing_runner.chat.assert_awaited_once()
    mock_ollama.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_chat_all_backends_raise_returns_last_friendly_message(mock_runner):
    """Every backend raises RunnerBackendError -> router returns the LAST
    failure's friendly_message (no exception propagates to the caller)."""
    first = MagicMock()
    first.chat = AsyncMock(side_effect=RunnerBackendError("Errore Claude, riprova."))
    second = MagicMock()
    second.chat = AsyncMock(side_effect=RunnerBackendError("Crediti OpenRouter esauriti."))
    router = LLMRouter(claude=first, openrouter=second, strategy="balanced")
    result = await router.chat(user_message="hello", model="auto")
    assert result == "Crediti OpenRouter esauriti."


# fetta E3 Task 8: `test_router_run_with_actions_fails_over_on_runner_
# backend_error` e `test_router_run_with_actions_all_fail_returns_last_
# friendly_message` sono usciti, cancellati e non spostati -- provavano
# `LLMRouter.run_with_actions`, uscito insieme al suo unico chiamante
# (server.py's `_llm_reason`, la Sentinella, uscita al Task 7). La prova
# gemella sul fallback di `chat()` (test_router_chat_fails_over_on_runner_
# backend_error / test_router_chat_all_backends_raise_returns_last_friendly_
# message, sopra) resta: quel meccanismo e' vivo, `chat()` non e' uscito.


# ---------------------------------------------------------------------------
# OpenRouter routing (v0.9.6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_routes_openrouter_prefix_colon(mock_runner):
    or_runner = MagicMock()
    or_runner.chat = AsyncMock(return_value="from openrouter")
    or_runner.last_tool_calls = []
    router = LLMRouter(openrouter=or_runner, strategy="balanced")
    result = await router.chat(
        user_message="hi",
        model="openrouter:meta-llama/llama-3.3-70b-instruct:free",
    )
    assert result == "from openrouter"
    or_runner.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_routes_openrouter_prefix_slash(mock_runner):
    or_runner = MagicMock()
    or_runner.chat = AsyncMock(return_value="from openrouter")
    or_runner.last_tool_calls = []
    router = LLMRouter(openrouter=or_runner, strategy="balanced")
    result = await router.chat(
        user_message="hi",
        model="openrouter/anthropic/claude-sonnet-4-6",
    )
    assert result == "from openrouter"
    or_runner.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_claude_prefix_skips_openrouter(mock_runner):
    """Plain 'claude-*' must still route to Claude runner, not OpenRouter."""
    claude_runner = MagicMock()
    claude_runner.chat = AsyncMock(return_value="from claude")
    claude_runner.last_tool_calls = []
    or_runner = MagicMock()
    or_runner.chat = AsyncMock()
    or_runner.last_tool_calls = []
    router = LLMRouter(claude=claude_runner, openrouter=or_runner, strategy="balanced")
    result = await router.chat(user_message="hi", model="claude-sonnet-4-6")
    assert result == "from claude"
    or_runner.chat.assert_not_awaited()


def test_router_strategy_includes_openrouter_in_chain():
    or_runner = MagicMock()
    claude_runner = MagicMock()
    router = LLMRouter(claude=claude_runner, openrouter=or_runner, strategy="balanced")
    backends = router._ordered_backends()
    # balanced: claude > openrouter > openai > ollama
    assert backends[0] is claude_runner
    assert or_runner in backends


def test_openrouter_runner_strips_prefix_in_resolve_model():
    from hiris.app.backends.openrouter_runner import _strip_openrouter_prefix
    assert _strip_openrouter_prefix("openrouter:foo/bar:free") == "foo/bar:free"
    assert _strip_openrouter_prefix("openrouter/foo/bar") == "foo/bar"
    assert _strip_openrouter_prefix("anthropic/claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"


def test_openrouter_runner_init(tmp_path):
    """OpenRouterRunner constructs with OpenRouter base URL + max_retries default."""
    from hiris.app.backends.openrouter_runner import OpenRouterRunner
    runner = OpenRouterRunner(
        api_key="sk-or-test",
    )
    assert "openrouter.ai/api/v1" in str(runner._client.base_url)
    # local=False -> cloud retry profile
    assert runner._client.max_retries == 2


# `test_backend_is_cloud` e' uscito con la funzione che provava (censimento del
# 17/08/2026): diceva se un modello uscisse verso il cloud, e serviva alle
# STRATEGIE -- il preset che sceglieva l'ordine dei provider, uscito con la
# fetta «la catena diventa l'unica verita'». Un test che difende una funzione
# morta e' morto anche lui.


class _Dummy:
    async def chat(self, **k): return "ok"


# fetta E4 Task 7 ("un bot solo"): la modalita' "automatic" e' uscita insieme
# all'ultimo chiamante che passava mode="automatic" (chatbot_engine.py, uscito
# al Task 4) -- con lei sono uscite la seconda policy (automatic_policy) e
# automatic_allows_sensitive(), gia' solo-test dal censimento prima di questo
# task. `test_model_chain_all_local_allows_sensitive`,
# `test_model_chain_with_cloud_blocks_sensitive` e
# `test_none_model_chain_preserves_legacy_two_policies` sono usciti, cancellati
# e non spostati -- provavano `automatic_allows_sensitive()` e/o la doppia
# policy chat/automatic di `_ordered_backends(mode)`: nessuno dei due soggetti
# esiste piu'. Verificato che cadessero per costruzione
# (`AttributeError: 'LLMRouter' object has no attribute 'automatic_allows_sensitive'`,
# `TypeError: LLMRouter.__init__() got an unexpected keyword argument
# 'automatic_policy'`) prima della cancellazione.
#
# fix round 1 (review indipendente): `test_all_inactive_fails_closed_for_
# sensitive_egress` era stato cancellato per intero, ma due delle sue cinque
# asserzioni avevano un soggetto vivo che cambiava solo la via d'accesso --
# "nessun runner registrato -> _ordered_backends() e' vuota", sui due rami del
# costruttore (`model_chain` falsy e legacy). Le tre su
# `automatic_allows_sensitive()` restano morte; le due superstiti si spostano
# qui sotto, senza la meta' egress uscita col suo soggetto.


def test_model_chain_sets_single_chain_for_both_modes():
    claude, ollama = _Dummy(), _Dummy()
    r = LLMRouter(claude=claude, ollama=ollama, strategy="balanced",
                  model_chain=["ollama", "claude"])
    # un'unica policy (chat_policy), nell'ordine dato dalla catena
    assert r._ordered_backends() == [ollama, claude]


def test_ordered_backends_empty_when_no_runners_registered():
    """Nessun runner registrato (ogni provider inattivo) -> _ordered_backends()
    e' vuota, su entrambi i rami del costruttore: model_chain esplicitamente
    vuoto e il ramo legacy (nessun model_chain, nessun chat_policy). Meta' viva
    di `test_all_inactive_fails_closed_for_sensitive_egress` (Slice 6b Task 1),
    spostata qui -- la meta' su `automatic_allows_sensitive()` e' uscita col
    suo soggetto (fetta E4 Task 7)."""
    r_model_chain = LLMRouter(strategy="balanced", model_chain=[])
    assert r_model_chain._ordered_backends() == []
    r_legacy = LLMRouter(strategy="quality_first")
    assert r_legacy._ordered_backends() == []


# fetta «la catena diventa l'unica verita'»: `LLMRouter.simple_chat` e' uscito,
# e con lui `test_simple_chat_senza_runner_non_finge_una_risposta_vuota` e
# `test_simple_chat_con_runner_resta_trasparente`. Provavano un SECONDO
# instradamento (`self._claude or self._openai or self._ollama` scritto a mano:
# OpenRouter escluso, nessun ripiego, catena ignorata), non una proprieta' del
# router che sopravviva al suo soggetto. Verificato che cadessero per
# costruzione (`AttributeError: 'LLMRouter' object has no attribute
# 'simple_chat'`) prima della cancellazione. Le implementazioni nei backend
# restano e restano provate dai loro file (`tests/test_claude_runner.py`,
# `tests/test_openai_compat_runner.py`): li' `simple_chat` e' la firma di un
# backend, non una decisione di instradamento.


def test_il_router_non_porta_una_seconda_regola_di_instradamento():
    """Il metodo non deve poter rientrare: era l'unico punto del prodotto in cui
    la scelta del provider NON passava dalla catena."""
    assert not hasattr(LLMRouter, "simple_chat")


def test_una_catena_esplicitamente_vuota_non_ripiega_sull_ordine_di_strategia():
    """Il difetto che questa fetta chiude, visto da dentro il router. Con
    `if model_chain:` una catena vuota ricadeva su `_STRATEGY_ORDER`, cioe' su
    OGNI provider costruito: la pagina avrebbe detto «la catena e' vuota, HIRIS
    non puo' rispondere» mentre la chat rispondeva. E' la regola `legacy`
    appena tolta, rientrata da un'altra porta."""
    claude, ollama = _Dummy(), _Dummy()
    r = LLMRouter(claude=claude, ollama=ollama, strategy="balanced", model_chain=[])
    assert r._chat_policy == []
    assert r._ordered_backends() == []


def test_senza_catena_passata_il_ripiego_di_libreria_resta():
    """`model_chain=None` e' il ramo di libreria: nessuno ha passato una
    catena, quindi l'ordine di strategia e' l'unica cosa che c'e'. Distinguere
    «catena vuota» da «nessuna catena» e' tutto cio' che il cambio fa."""
    claude, ollama = _Dummy(), _Dummy()
    r = LLMRouter(claude=claude, ollama=ollama, strategy="balanced")
    assert r._ordered_backends() == [claude, ollama]


@pytest.mark.asyncio
async def test_niente_in_catena_non_e_una_risposta_che_invita_a_riprovare():
    """«Tutti i provider AI non disponibili. Riprova tra poco» dice che il
    guasto e' transitorio. Con la catena vuota non lo e': non c'e' niente da
    aspettare, c'e' qualcosa da mettere in catena."""
    r = LLMRouter(claude=_Dummy(), strategy="balanced", model_chain=[])
    risposta = await r.chat(model="auto")
    assert "catena" in risposta.lower()
    assert "riprova" not in risposta.lower()


# ---------------------------------------------------------------------------
# La scrittura a caldo vista da un turno CHE E' GIA' PARTITO (Task 10)
#
# Da questa fetta `app["recompute_chain"]` riassegna `_chat_policy` mentre
# l'add-on gira, quindi una PUT puo' arrivare nel mezzo di un turno di chat.
# E' il tipo di cosa che non si riproduce mai su un banco e si vede una volta
# al mese in produzione, quindi si guarda apposta e si dichiara.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_un_turno_finisce_con_la_catena_con_cui_e_partito():
    """`chat()` calcola `_ordered_backends()` UNA volta, in cima, e il
    ricalcolo RIASSEGNA l'attributo invece di mutare la lista: il turno in
    volo tiene in mano la lista di prima e la percorre tutta. Senza questo --
    per esempio con un `_chat_policy[:] = ...` che muta sul posto -- un turno
    partito su due anelli potrebbe ritrovarsene uno solo a meta' ripiego, e il
    messaggio morirebbe con un errore che nessun log spiega."""
    from hiris.app.claude_runner import RunnerBackendError
    from hiris.app.llm_router import LLMRouter

    class _Rotto:
        async def chat(self, **k):
            # La PUT arriva ESATTAMENTE adesso: fra il primo tentativo e il
            # ripiego. E' l'istante scomodo, ed e' per questo che la finta lo
            # sceglie invece di aspettare che capiti.
            router._chat_policy = []
            raise RunnerBackendError("giu'")

    class _Buono:
        async def chat(self, **k):
            return "risposta"

    router = LLMRouter(claude=_Rotto(), openrouter=_Buono(),
                       model_chain=["claude", "openrouter"])
    assert await router.chat(model="auto") == "risposta"
    # E il turno DOPO usa la catena nuova: la scrittura non e' andata persa,
    # e' solo arrivata dopo la partenza di quel turno.
    assert router._chat_policy == []


# ---------------------------------------------------------------------------
# Il ciclo di ripiego REGISTRA (Task 11)
#
# E' il solo posto in cui HIRIS vede davvero come si comporta un provider, e
# fino a questa fetta lo buttava via: un `logger.warning` e avanti. La pagina
# Modelli sapeva dire «Claude e' primo in catena» e non «e sta rifiutando da
# quaranta richieste» -- che e' il caso del proprietario per intero.
#
# L'orologio del registro e' INIETTATO in ogni test qui sotto: senza, «quando»
# sarebbe un numero che nessuna asserzione puo' nominare.
# ---------------------------------------------------------------------------


def _registro_fermo(t0=1000.0):
    from hiris.app.provider_occurrences import OccurrenceRegistry
    adesso = [t0]
    return OccurrenceRegistry(clock=lambda: adesso[0]), adesso


@pytest.mark.asyncio
async def test_il_ripiego_scrive_chi_ha_rifiutato_e_chi_ha_risposto():
    """Un turno che ripiega lascia DUE fatti, non uno: il primo ha rifiutato,
    il secondo ha risposto. Prima di questa fetta ne lasciava zero."""
    registro, _ = _registro_fermo()
    rotto = MagicMock()
    rotto.chat = AsyncMock(side_effect=RunnerBackendError(
        "Errore temporaneo del servizio AI. Riprova tra poco.",
        family="credenziale", code=400))
    buono = MagicMock()
    buono.chat = AsyncMock(return_value="risposta")
    router = LLMRouter(claude=rotto, openrouter=buono,
                       model_chain=["claude", "openrouter"], registry=registro)

    assert await router.chat(model="auto") == "risposta"
    claude = registro.occurrence("claude")
    assert claude["tipo"] == "rifiutato"
    assert claude["famiglia"] == "credenziale" and claude["codice"] == 400
    assert claude["quando"] == 1000.0 and claude["da_quante"] == 1
    assert registro.occurrence("openrouter")["tipo"] == "risposto"


@pytest.mark.asyncio
async def test_il_registro_distingue_openai_da_openrouter():
    """LA MUTAZIONE CHE QUESTO TEST ESISTE PER PRENDERE: registrare con
    `type(runner).__name__`. `OpenRouterRunner` E' UNA SOTTOCLASSE di
    `OpenAICompatRunner`, quindi un rifiuto di OpenRouter finirebbe scritto
    sulla riga di OpenAI -- un difetto silenzioso dentro la funzione nata per
    toglierne uno. Le due finte sono di classi che si somigliano APPOSTA."""
    class _Compat:
        async def chat(self, **k):
            raise RunnerBackendError("giu'", family="modello", code=404)

    class _Router(_Compat):
        pass

    registro, _ = _registro_fermo()
    router = LLMRouter(openai=_Compat(), openrouter=_Router(),
                       model_chain=["openrouter"], registry=registro)
    await router.chat(model="auto")

    assert registro.occurrence("openrouter")["codice"] == 404
    assert registro.occurrence("openai") is None, (
        "OpenAI non e' stato interrogato: sulla sua riga non deve comparire "
        "il rifiuto di un altro provider"
    )


@pytest.mark.asyncio
async def test_un_guasto_che_non_e_un_RunnerBackendError_si_registra_lo_stesso():
    """Un bug nel runner (un `TypeError` su una firma cambiata) non porta ne'
    famiglia ne' codice, e prima di questa fetta non lasciava traccia. Un
    provider che esplode in modo imprevisto deve comparire nella pagina come
    uno che ha rifiutato, non come uno di cui non si sa niente."""
    registro, _ = _registro_fermo()
    rotto = MagicMock()
    rotto.chat = AsyncMock(side_effect=TypeError("firma cambiata"))
    router = LLMRouter(claude=rotto, model_chain=["claude"], registry=registro)
    await router.chat(model="auto")

    e = registro.occurrence("claude")
    assert e["tipo"] == "rifiutato" and e["famiglia"] == "altro" and e["codice"] is None
    assert "firma cambiata" in e["messaggio"]


@pytest.mark.asyncio
async def test_chi_non_e_stato_interrogato_non_compare_nel_registro():
    """La regola che il registro esiste per rispettare: chi legge deve poter
    distinguere «non ha risposto» da «non l'ho interrogato». Il primo anello
    risponde, il secondo non viene nemmeno chiamato -- e sulla sua riga non
    deve comparire niente."""
    registro, _ = _registro_fermo()
    buono = MagicMock()
    buono.chat = AsyncMock(return_value="risposta")
    mai = MagicMock()
    mai.chat = AsyncMock(return_value="mai chiamato")
    router = LLMRouter(claude=buono, ollama=mai,
                       model_chain=["claude", "ollama"], registry=registro)
    await router.chat(model="auto")

    assert set(registro.occurrences()) == {"claude"}


@pytest.mark.asyncio
async def test_quaranta_turni_di_rifiuto_si_leggono_come_quaranta():
    """Il caso del proprietario. Il registro non e' «l'ultimo errore»: e' «da
    quante richieste dura», ed e' la differenza fra «ah, un errore» e «ah, sto
    buttando via una chiamata a messaggio da settimane». L'orologio avanza
    SOLO quando lo dice il test."""
    registro, adesso = _registro_fermo()
    rotto = MagicMock()
    rotto.chat = AsyncMock(side_effect=RunnerBackendError(
        "Errore temporaneo del servizio AI. Riprova tra poco.",
        family="credenziale", code=400))
    buono = MagicMock()
    buono.chat = AsyncMock(return_value="risposta")
    router = LLMRouter(claude=rotto, openrouter=buono,
                       model_chain=["claude", "openrouter"], registry=registro)
    for _ in range(40):
        adesso[0] += 60
        await router.chat(model="auto")

    e = registro.occurrence("claude")
    assert e["da_quante"] == 40 and e["quando"] == 1000.0 + 40 * 60


@pytest.mark.asyncio
async def test_senza_registro_il_router_funziona_come_prima():
    """`registro=None` e' il ramo di libreria (e di ogni test che non parla di
    esiti): il ciclo di ripiego non deve cambiare comportamento, ne' esplodere
    su un `None`."""
    rotto = MagicMock()
    rotto.chat = AsyncMock(side_effect=RunnerBackendError("giu'"))
    buono = MagicMock()
    buono.chat = AsyncMock(return_value="risposta")
    router = LLMRouter(claude=rotto, ollama=buono, strategy="quality_first")
    assert await router.chat(model="auto") == "risposta"


@pytest.mark.asyncio
async def test_la_durata_misurata_e_quella_del_tentativo_fallito():
    """`durata_s` e' quanto e' costato il rifiuto, e si misura con l'orologio
    MONOTONO invece che con quello di parete: un tentativo che dura otto
    secondi prima di fallire e' un'altra cosa rispetto a uno che fallisce
    subito, e le due si distinguono solo cosi'. Il tempo di parete puo'
    saltare all'indietro; una durata no."""
    import hiris.app.llm_router as modulo

    passi = iter([100.0, 108.0])
    registro, _ = _registro_fermo()
    rotto = MagicMock()
    rotto.chat = AsyncMock(side_effect=RunnerBackendError("giu'"))
    router = LLMRouter(claude=rotto, model_chain=["claude"], registry=registro)
    with patch.object(modulo.time, "monotonic", lambda: next(passi)):
        await router.chat(model="auto")

    assert registro.occurrence("claude")["durata_s"] == 8.0


def test_l_ordine_coi_nomi_e_l_ordine_senza_sono_LO_STESSO_calcolo():
    """`_ordered_backends` e' DERIVATA da `_ordered_backends_with_name`. Due
    implementazioni della stessa lista sarebbero due rappresentazioni della
    stessa cosa, libere di divergere -- e la seconda sceglie a chi chiedere
    mentre la prima decide su chi si scrive."""
    import ast
    import inspect

    from hiris.app import llm_router as modulo

    claude, ollama = _Dummy(), _Dummy()
    r = LLMRouter(claude=claude, ollama=ollama, model_chain=["ollama", "claude"])
    assert r._ordered_backends() == [ollama, claude]
    assert [n for n, _ in r._ordered_backends_with_name()] == ["ollama", "claude"]

    import textwrap
    albero = ast.parse(textwrap.dedent(
        inspect.getsource(modulo.LLMRouter._ordered_backends)))
    chiamate = [n.func.attr for n in ast.walk(albero)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "_ordered_backends_with_name" in chiamate, (
        "_ordered_backends deve derivare dall'altra, non rifare il giro sulla "
        "policy per conto proprio"
    )
