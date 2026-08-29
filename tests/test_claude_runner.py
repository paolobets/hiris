"""fetta E2 Task 7 ("esce il dispatcher"): this file used to exercise
ClaudeRunner's tool-dispatch loop through a REAL `ToolDispatcher` -- both to
prove the loop mechanic itself (parse tool_use -> dispatch -> tool_result)
AND, for a chunk of tests, to prove ToolDispatcher's OWN routing/gating
(allowed_entities/allowed_services filtering, per-tool argument mapping to
HA service calls). `ToolDispatcher` is gone; checked test by test rather
than assumed:

  - Tests whose assertion is about the LOOP MECHANIC or something else
    entirely (prompt injection, usage tracking, thinking params, cache
    control, model resolution, catalog membership, `last_tool_calls`
    bookkeeping which is appended unconditionally regardless of dispatch
    outcome) do not need a real dispatcher at all -- `dispatcher` now
    defaults to `None` on the runner and stays that way here.
  - Tests whose assertion was specifically about ToolDispatcher's OWN
    behaviour (`test_chat_handles_tool_use`, `test_allowed_entities_*`,
    `test_allowed_services_*`, `test_dispatch_get_area_entities`,
    `test_dispatch_get_calendar_events_*`, `test_dispatch_set_input_helper_*`,
    `test_set_input_helper_blocked_by_allowed_services`) died with it: with
    `self._dispatcher` now `None` by construction, the runner's fallback
    dispatch branch returns a generic "non disponibile" error for ANY tool
    (see claude_runner.py's `chat()`), so there is no surviving path that
    still applies `allowed_entities`/`allowed_services` filtering or maps
    tool arguments onto real HA service calls the way ToolDispatcher did --
    that specific 34-tool-catalog routing has no successor (it was explicitly
    OUT of scope for this fetta per .superpowers/sdd/progress.md at the time:
    the Sentinel's EVALUATION_ONLY_TOOLS/run_with_actions catalog stayed as
    CODE, not as working dispatch -- fetta E3 Task 8 later removed that code
    too, once the Sentinella itself left in Task 7). Those tests were
    deleted, not moved.
  - The two concurrency/security tests near the end
    (`test_chat_concurrent_calls_do_not_leak_tool_calls`,
    `test_chat_concurrent_calls_do_not_leak_pseudonym_map`) needed a
    dispatcher-shaped stand-in to keep proving the runner's OWN ContextVar
    isolation under concurrency; see their own comments for what replaced
    `ToolDispatcher` there. Il secondo dei due e' poi uscito con la fetta
    "esce il documentale" (vedi la nota al suo posto): il suo soggetto,
    `last_pseudonym_map`, non esiste piu'.

fetta E4 Task 6 ("un bot solo"): the constructor `dispatcher=` kwarg (the
"scorta" stand-in the two concurrency tests above used to plug their
dispatcher into) is gone -- `self._dispatcher` and the `elif self._dispatcher
is not None` branch that read it are gone too, zero production callers ever
populated them (fetta E2 Task 7, commit 68d3670). Both tests move to the
per-call `dispatcher=` kwarg of `chat()` (the one that stays: DispatcherStrumenti's
own path) instead -- verified BEFORE moving that leaving them untouched would
have kept them GREEN for the wrong reason: `last_tool_calls.append(...)` runs
unconditionally after the tool-dispatch if/else regardless of which branch
ran, so `test_chat_concurrent_calls_do_not_leak_tool_calls` still passed with
`runner._dispatcher = MagicMock(...)` even though that mock was never called
any more (chat() no longer reads `self._dispatcher` at all) -- an illusion of
coverage, not a construction failure. Also gone from this same file: the
seven kwargs that were `elif self._dispatcher is not None`'s only readers
(`chatbot_id`, `allowed_entities`, `allowed_services`, `allowed_endpoints`,
`visible_entity_ids`, `knowledge_allow_sensitive`, `knowledge_kinds`) and
`require_confirmation` (already inert in the system prompt since fetta E2,
now gone from the signature too) plus the per-chatbot usage accounting
(`get_chatbot_usage`/`reset_chatbot_usage`/`_per_chatbot_usage`) they fed --
see task-6-report.md for the full account, including the grep evidence for
every kwarg.
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from hiris.app.claude_runner import AUTO_MODEL_MAP, RESTRICT_PROMPT, ClaudeRunner, resolve_model


def _sys_text(system) -> str:
    """Flatten system blocks list to a plain string for assertions."""
    if isinstance(system, str):
        return system
    return "\n".join(b.get("text", "") for b in system if b.get("type") == "text")


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[])
    ha.call_service = AsyncMock(return_value=True)
    return ha


@pytest.fixture
def rifiuti():
    """Le righe di rifiuto (429) che il runner scrive nell'archivio dei consumi.

    Fetta «i consumi, per modello»: `total_rate_limit_errors` era un numero
    solo per tutto il prodotto e non diceva CHI stesse rifiutando -- l'unica
    cosa che serva sapere quando succede. Adesso il fatto si scrive sulla riga
    del modello che l'ha preso, e questa lista e' la sua casa nei test.
    """
    return []


@pytest.fixture
def runner(mock_ha, rifiuti):
    # Nessun dispatcher di scorta (ToolDispatcher e' uscito): i test qui
    # sotto non ne hanno bisogno -- vedi il docstring del modulo.
    def _registra(provider, modello, **kw):
        rifiuti.append({"provider": provider, "modello": modello, **kw})

    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key", registra_consumo=_registra)
    r._ha = mock_ha  # shortcut for tests
    return r


@pytest.mark.asyncio
async def test_chat_returns_text_response(runner):
    fake_message = MagicMock()
    fake_message.stop_reason = "end_turn"
    fake_message.content = [MagicMock(type="text", text="Hello from Claude")]

    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=fake_message)

        runner._client = instance
        result = await runner.chat("Ciao")

    assert result == "Hello from Claude"


@pytest.fixture
def restricted_runner(mock_ha):
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key")
    r._ha = mock_ha
    return r


@pytest.mark.asyncio
async def test_restrict_to_home_injects_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat("Ciao", restrict_to_home=True)
    system_text = _sys_text(captured[0]["system"])
    assert "solo" in system_text.lower()
    assert RESTRICT_PROMPT in system_text


@pytest.mark.asyncio
async def test_restrict_to_home_false_does_not_inject(runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Prompt originale", restrict_to_home=False)
    system_text = _sys_text(captured[0]["system"])
    assert "Prompt originale" in system_text
    assert RESTRICT_PROMPT not in system_text


@pytest.mark.asyncio
async def test_restrict_to_home_appends_to_existing_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat(
        "Ciao", system_prompt="Sei un agente energia.", restrict_to_home=True
    )
    system_text = _sys_text(captured[0]["system"])
    assert "agente energia" in system_text
    assert RESTRICT_PROMPT in system_text


def test_resolve_model_auto_chat_returns_sonnet():
    assert resolve_model("auto", "chat") == "claude-sonnet-4-6"


def test_resolve_model_auto_agent_returns_haiku():
    assert resolve_model("auto", "agent") == "claude-haiku-4-5-20251001"


def test_resolve_model_explicit_overrides_auto():
    assert resolve_model("claude-sonnet-4-6", "agent") == "claude-sonnet-4-6"


def test_resolve_model_auto_unknown_type_defaults_to_sonnet():
    assert resolve_model("auto", "unknown_type") == "claude-sonnet-4-6"


def test_resolve_model_auto_promessa_e_agganciato_a_chat():
    """Rilievo minore della review finale dello schedulatore: il turno di una
    promessa "chiedi" (`schedulatore/turno.py::interpreta_promessa`) usa
    `agent_type="promessa"`, che prima non era in `AUTO_MODEL_MAP` -- il
    ripiego su `MODEL` coincideva col valore di "chat" solo per coincidenza,
    non perche' le due costanti fossero legate. Qui si prova il legame:
    "promessa" DEVE essere la STESSA chiave di "chat", non una stringa
    duplicata che domani potrebbe divergere senza che nessun test se ne
    accorga."""
    assert AUTO_MODEL_MAP["promessa"] == AUTO_MODEL_MAP["chat"]
    assert resolve_model("auto", "promessa") == AUTO_MODEL_MAP["chat"]


@pytest.mark.asyncio
async def test_chat_uses_resolved_model_for_agent(runner):
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 10
    success.usage.output_tokens = 5
    runner._client.messages.create = AsyncMock(return_value=success)
    await runner.chat("Test", model="auto", agent_type="agent")
    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_rate_limit_retries_once_and_succeeds(runner, rifiuti):
    """_call_api retries on 429 and succeeds on second attempt."""
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 5
    success.usage.output_tokens = 2

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise anthropic.APIStatusError(
                "rate limited",
                response=MagicMock(status_code=429),
                body={},
            )
        return success

    with patch.object(runner._client.messages, "create", side_effect=fake_create), \
         patch("hiris.app.claude_runner.asyncio.sleep", new_callable=AsyncMock):
        result = await runner._call_api(
            model="claude-sonnet-4-6", max_tokens=100, messages=[]
        )

    assert result is success
    assert call_count == 2
    assert [x for x in rifiuti if x["errori_rate_limit"] == 1], (
        "un 429 si conta ancora -- adesso sulla riga del modello che l'ha "
        "preso, invece che in un numero solo che non diceva CHI rifiutasse")


@pytest.mark.asyncio
async def test_rate_limit_exhausts_retries_raises(runner, rifiuti):
    """_call_api raises after MAX_RETRIES 429 errors."""
    from hiris.app.claude_runner import MAX_RETRIES

    call_count = 0

    async def always_rate_limit(**kwargs):
        nonlocal call_count
        call_count += 1
        raise anthropic.APIStatusError(
            "rate limited",
            response=MagicMock(status_code=429),
            body={},
        )

    with (
        patch.object(runner._client.messages, "create", side_effect=always_rate_limit),
        patch("hiris.app.claude_runner.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(anthropic.APIStatusError),
    ):
        await runner._call_api(
            model="claude-sonnet-4-6", max_tokens=100, messages=[]
        )

    assert len(rifiuti) == MAX_RETRIES, (
        "ogni tentativo rifiutato si conta, come prima: solo, adesso si sa "
        "su quale modello")
    assert call_count == MAX_RETRIES + 1


# Review finale fetta E2, I-5: `CONFIRMATION_COVERED_TOOLS` e
# `REQUIRE_CONFIRMATION_PROMPT` sono uscite da claude_runner.py -- i tre test
# che pinnavano l'iniezione del prompt sono usciti con il loro soggetto.
# fetta E4 Task 6 ("un bot solo"): il pin del comportamento successivo
# (`test_require_confirmation_no_longer_alters_system_prompt`, "non altera
# piu' il system prompt ne' quando True ne' quando False") e' uscito a sua
# volta -- il parametro `require_confirmation` stesso e' uscito dalla firma
# di `chat()`/`chat_stream()`: non c'e' piu' nulla da passare True/False a
# cui provare l'assenza di effetto. Verificato fallire per costruzione prima
# di cancellarlo: `TypeError: ClaudeRunner.chat() got an unexpected keyword
# argument 'require_confirmation'`.


# fetta E3 Task 8: `test_run_with_actions_is_plain_agentic_loop`,
# `test_run_with_actions_restricts_to_evaluation_only_tools` e
# `test_empty_allowed_tools_does_not_narrow_evaluation_set` sono usciti,
# cancellati e non spostati -- provavano `run_with_actions`/
# `EVALUATION_ONLY_TOOLS`, usciti insieme al loro unico chiamante (la
# Sentinella, uscita al Task 7). Verificato che cadessero per costruzione
# prima di cancellarli (AttributeError su `run_with_actions`, ImportError su
# `EVALUATION_ONLY_TOOLS`).


# fetta E4 Task 6 ("un bot solo"): quattro test sono usciti, cancellati e non
# spostati -- provavano `get_chatbot_usage`/`reset_chatbot_usage`/
# `_per_chatbot_usage`, usciti per intero (zero lettori di produzione dal
# Task 3, rotte usage uscite, e dal Task 4, ChatbotEngine uscito). Verificato
# fallire per costruzione prima di cancellarli:
#   test_get_chatbot_usage_returns_zeros_for_unknown_agent:
#     AttributeError: 'ClaudeRunner' object has no attribute 'get_chatbot_usage'
#   test_per_chatbot_usage_accumulates_after_chat:
#     TypeError: ClaudeRunner.chat() got an unexpected keyword argument 'chatbot_id'
#   test_reset_chatbot_usage_clears_counters / test_per_chatbot_usage_persists_
#   and_reloads:
#     AttributeError: 'ClaudeRunner' object has no attribute '_per_chatbot_usage'
# (visto girando la suite intera prima di questa pulizia -- vedi task-6-report.md).


@pytest.mark.asyncio
async def test_simple_chat_returns_text(runner):
    fake_message = MagicMock()
    fake_message.content = [MagicMock(type="text", text='{"result": "ok"}')]
    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=fake_message)
        runner._client = instance
        result = await runner.simple_chat(
            [{"role": "user", "content": "classify"}],
            system="Classify entities",
        )
    assert result == '{"result": "ok"}'


# fetta E3 Task 8: `test_get_calendar_events_in_all_tool_defs` e' uscito
# (cancellato, non spostato) -- provava l'appartenenza al catalogo
# `EVALUATION_TOOL_DEFS`, uscito insieme al suo unico chiamante
# (`run_with_actions`, la Sentinella, uscita al Task 7). La nota della E2
# Task 8 su `test_set_input_helper_in_all_tool_defs` (gia' cancellato allora)
# citava lo stesso catalogo come punto di riferimento -- non ne resta piu'
# traccia da provare.


# ---------------------------------------------------------------------------
# Extended Thinking - _build_thinking_param + chat() integration
# ---------------------------------------------------------------------------

def test_build_thinking_param_disabled_when_zero():
    from hiris.app.claude_runner import _build_thinking_param
    assert _build_thinking_param(0, "claude-sonnet-4-6", 4096) is None


def test_build_thinking_param_enabled_on_sonnet_4_6():
    from hiris.app.claude_runner import _build_thinking_param
    out = _build_thinking_param(2048, "claude-sonnet-4-6", 4096)
    assert out == {"type": "enabled", "budget_tokens": 2048}


def test_build_thinking_param_enabled_on_opus_4_7():
    from hiris.app.claude_runner import _build_thinking_param
    out = _build_thinking_param(2048, "claude-opus-4-7", 4096)
    assert out == {"type": "enabled", "budget_tokens": 2048}


def test_build_thinking_param_disabled_on_haiku():
    from hiris.app.claude_runner import _build_thinking_param
    assert _build_thinking_param(2048, "claude-haiku-4-5-20251001", 4096) is None


def test_build_thinking_param_disabled_below_anthropic_minimum():
    from hiris.app.claude_runner import _build_thinking_param
    assert _build_thinking_param(512, "claude-sonnet-4-6", 4096) is None


def test_build_thinking_param_clamps_when_geq_max_tokens():
    from hiris.app.claude_runner import _build_thinking_param
    out = _build_thinking_param(8000, "claude-sonnet-4-6", 4000)
    assert out == {"type": "enabled", "budget_tokens": 3999}


def test_build_thinking_param_returns_none_if_clamp_drops_below_minimum():
    from hiris.app.claude_runner import _build_thinking_param
    # max_tokens too small: even after clamp budget < 1024 -> disabled
    assert _build_thinking_param(2048, "claude-sonnet-4-6", 1024) is None


@pytest.mark.asyncio
async def test_chat_passes_thinking_param_when_capable(runner):
    """chat() with thinking_budget>0 on capable model passes thinking= to API."""
    text_block = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[text_block])
    msg.usage = MagicMock(input_tokens=10, output_tokens=5,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)
    await runner.chat("ciao", model="claude-sonnet-4-6", max_tokens=4096, thinking_budget=2048)
    kwargs = runner._client.messages.create.call_args.kwargs
    assert kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 2048}


@pytest.mark.asyncio
async def test_chat_no_thinking_param_when_disabled(runner):
    """chat() with thinking_budget=0 omits thinking= entirely."""
    text_block = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[text_block])
    msg.usage = MagicMock(input_tokens=10, output_tokens=5,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)
    await runner.chat("ciao", model="claude-sonnet-4-6", thinking_budget=0)
    kwargs = runner._client.messages.create.call_args.kwargs
    assert "thinking" not in kwargs


def _count_cache_breakpoints(kwargs: dict) -> int:
    """Count cache_control blocks across system, tools and message content."""
    def _count(blocks) -> int:
        if not isinstance(blocks, list):
            return 0
        return sum(1 for b in blocks if isinstance(b, dict) and b.get("cache_control"))
    n = _count(kwargs.get("system")) + _count(kwargs.get("tools"))
    for msg in kwargs.get("messages", []):
        n += _count(msg.get("content"))
    return n


@pytest.mark.asyncio
async def test_cache_control_within_limit_with_modifiers_and_history(runner):
    """Worst-case config must stay within Anthropic's hard cap of 4 cache_control.

    Regression for the v0.9.5 overflow: BASE + agent prompt + last modifier each
    carried their own breakpoint (3), which together with the tool-defs and the
    conversation-history breakpoints reached 5 on a follow-up turn and made the
    API return a 400 — surfaced to the user as the generic
    "Errore temporaneo del servizio AI" on the 2nd message of a chat.
    """
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage = MagicMock(input_tokens=5, output_tokens=2,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return m

    runner._client.messages.create = capture
    await runner.chat(
        "Domanda di follow-up",
        system_prompt="Prompt agente",
        context_str="## Contesto casa\nluce: accesa",
        conversation_history=[
            {"role": "user", "content": "prima domanda"},
            {"role": "assistant", "content": "prima risposta"},
        ],
        restrict_to_home=True,
        response_mode="compact",
    )
    n = _count_cache_breakpoints(captured[0])
    assert n <= 4, f"too many cache_control breakpoints: {n}"


@pytest.mark.asyncio
async def test_cache_control_single_system_breakpoint(runner):
    """All stable system content shares ONE cumulative breakpoint, not one each."""
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage = MagicMock(input_tokens=5, output_tokens=2,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return m

    runner._client.messages.create = capture
    await runner.chat(
        "Ciao",
        system_prompt="Prompt agente",
        restrict_to_home=True,
    )
    system = captured[0]["system"]
    n_system = sum(1 for b in system if isinstance(b, dict) and b.get("cache_control"))
    assert n_system == 1


@pytest.mark.asyncio
async def test_chat_collects_thinking_blocks(runner):
    """Thinking blocks in response.content are captured in last_thinking_blocks."""
    thinking_block = MagicMock(type="thinking", thinking="step 1: check state\nstep 2: decide")
    text_block = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[thinking_block, text_block])
    msg.usage = MagicMock(input_tokens=10, output_tokens=5,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)
    await runner.chat("ciao", model="claude-sonnet-4-6", thinking_budget=2048)
    assert runner.last_thinking_blocks == ["step 1: check state\nstep 2: decide"]


@pytest.mark.asyncio
async def test_chat_populates_last_tool_calls_single_call(runner):
    """Baseline for 'single-call behavior unchanged' (review A/#3): a lone,
    non-overlapping chat() call must still populate last_tool_calls with its
    own tool call after switching from a plain instance attribute to the
    per-call ContextVar-backed descriptor."""
    tool_block = MagicMock(type="tool_use", id="tu_x", input={"ids": ["light.living"]})
    tool_block.name = "get_entity_states"
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="ok")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._ha.get_states = AsyncMock(return_value=[])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("ciao")
    assert runner.last_tool_calls == [
        {"tool": "get_entity_states", "input": {"ids": ["light.living"]}}
    ]


@pytest.mark.asyncio
async def test_chat_processes_all_tool_use_blocks_of_one_response_in_one_iteration(runner):
    """fetta "i riferimenti" (R3+R8, Task 5): il ciclo di `chat()` processa
    OGNI blocco `tool_use` della stessa risposta prima di richiamare l'API
    di nuovo -- N chiamate parallele nella stessa risposta del modello
    costano UNA sola iterazione del `for _ in range(MAX_TOOL_ITERATIONS)`,
    non N. E' il fatto misurato che rende vero l'insegnamento aggiunto al
    prompt ("chiamale IN PARALLELO nella stessa risposta"): se non fosse
    vero, insegnarlo peggiorerebbe le cose.

    Deve poter fallire: un runner che processasse solo il PRIMO blocco della
    risposta (`for block in response.content[:1]` al posto di
    `response.content`) renderebbe rosso sia `call_count == 2` (servirebbero
    altre iterazioni per gli N-1 blocchi rimasti) sia `len(chiamate_dispatch)
    == N` -- mutazione eseguita a mano e riportata in task-5-report.md.
    """

    def _usage():
        return MagicMock(input_tokens=1, output_tokens=1,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)

    N = 5
    blocks = []
    for i in range(N):
        block = MagicMock(type="tool_use", id=f"tu-{i}", input={"area": f"stanza-{i}"})
        block.name = "guarda"
        blocks.append(block)
    multi_tool_msg = MagicMock(stop_reason="tool_use", content=blocks, usage=_usage())
    text_block = MagicMock(type="text", text="fatto")
    end_msg = MagicMock(stop_reason="end_turn", content=[text_block], usage=_usage())

    runner._client.messages.create = AsyncMock(side_effect=[multi_tool_msg, end_msg])

    chiamate_dispatch = []

    async def fake_dispatch(nome, argomenti):
        chiamate_dispatch.append((nome, argomenti))
        return {"ok": True}

    finto_dispatcher = MagicMock(dispatch=AsyncMock(side_effect=fake_dispatch))

    text = await runner.chat("guarda cinque stanze", dispatcher=finto_dispatcher)

    assert text == "fatto"
    # Due chiamate API in tutto -- il giro coi tool (UNA iterazione, N
    # blocchi) + il giro finale che scrive la risposta -- non N+1: e' la
    # prova diretta che N blocchi paralleli consumano una sola iterazione.
    assert runner._client.messages.create.call_count == 2
    assert len(chiamate_dispatch) == N
    assert runner.last_tool_calls == [
        {"tool": "guarda", "input": {"area": f"stanza-{i}"}} for i in range(N)
    ]


@pytest.mark.asyncio
async def test_chat_esaurimento_iterazioni_messaggio_italiano_e_log(runner, caplog, monkeypatch):
    """R4 (fetta "i riferimenti", Task 6): quando il modello chiede SEMPRE
    uno strumento e non arriva mai a `end_turn`, il turno esaurisce
    `MAX_TOOL_ITERATIONS` -- prima rispondeva con la stringa inglese
    hardcoded "Max tool iterations reached.", zero log. Ora deve rispondere
    col messaggio italiano `_MAX_ITERATIONS_NOTICE` e registrare un
    `logger.warning` col conto delle iterazioni e i NOMI degli strumenti
    chiamati (mai gli argomenti, che possono portare dati personali --
    "cucina"/"salotto" qui sopra sono nomi di stanza, non verificati che
    NON compaiano nel log).

    Deve poter fallire (mutazioni eseguite a mano, task-6-report.md):
    (a) ripristinare `return "Max tool iterations reached."` fa cadere il
        primo assert; (b) togliere il `logger.warning` fa cadere il secondo.
    """
    from hiris.app.claude_runner import _MAX_ITERATIONS_NOTICE
    monkeypatch.setattr("hiris.app.claude_runner.MAX_TOOL_ITERATIONS", 3)

    def _usage():
        return MagicMock(input_tokens=1, output_tokens=1,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)

    def _tool_msg(name, area):
        block = MagicMock(type="tool_use", id=f"tu-{name}-{area}", input={"area": area})
        block.name = name
        return MagicMock(stop_reason="tool_use", content=[block], usage=_usage())

    runner._client.messages.create = AsyncMock(side_effect=[
        _tool_msg("guarda", "cucina"),
        _tool_msg("guarda", "salotto"),
        _tool_msg("cerca", "termostato"),
    ])
    finto_dispatcher = MagicMock(dispatch=AsyncMock(return_value={"ok": True}))

    with caplog.at_level(logging.WARNING):
        result = await runner.chat("guarda ogni stanza", dispatcher=finto_dispatcher)

    assert result == _MAX_ITERATIONS_NOTICE
    assert "Max tool iterations reached." not in result
    assert runner._client.messages.create.call_count == 3

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("3" in m and "guarda" in m and "cerca" in m for m in warning_messages), (
        f"nessun warning col conto delle iterazioni e i nomi degli strumenti: {warning_messages}"
    )
    # gli argomenti (nomi di stanza) non devono comparire nel log -- solo i
    # nomi degli strumenti, come chiesto dal brief (possono portare dati
    # personali).
    assert not any("cucina" in m or "salotto" in m or "termostato" in m for m in warning_messages)


@pytest.mark.asyncio
async def test_chat_concurrent_calls_do_not_leak_tool_calls(runner):
    """Two overlapping chat() calls on the SAME runner instance must not
    leak or wipe each other's tool_calls (review A/#3 concurrency fix).

    Before the ContextVar-based isolation, last_tool_calls was a single
    unlocked instance attribute: both calls reset it to [] at the start and
    appended to it after awaiting the (fake) API. Interleaving two calls —
    call B resets/appends while call A is still in flight — meant the SAME
    shared list ended up holding entries from BOTH calls, and a caller
    reading `runner.last_tool_calls` right after its own `await
    runner.chat(...)` could see the other call's tool inputs (or its own
    silently wiped). This test deterministically interleaves two calls via
    asyncio.gather + real awaits and fails on the pre-fix shared-attribute
    code; it passes once collection is isolated per asyncio Task.
    """

    def _usage():
        return MagicMock(input_tokens=1, output_tokens=1,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)

    def _tool_response(tool_name: str, entity_id: str):
        block = MagicMock(type="tool_use", id=f"id-{tool_name}", input={"entity_id": entity_id})
        block.name = tool_name
        return MagicMock(stop_reason="tool_use", content=[block], usage=_usage())

    def _end_response(text: str):
        block = MagicMock(type="text", text=text)
        return MagicMock(stop_reason="end_turn", content=[block], usage=_usage())

    async def fake_create(**kwargs):
        msgs = kwargs["messages"]
        is_call_a = msgs[0]["content"] == "call-A"
        first_iteration = len(msgs) == 1
        # call B is intentionally faster than call A so their two API
        # round-trips interleave deterministically (B's iter1 resolves
        # before A's iter1; B finishes entirely before A's iter2 finishes).
        await asyncio.sleep(0.02 if is_call_a else 0.01)
        if first_iteration:
            return _tool_response(
                "get_area_entities" if is_call_a else "get_home_status",
                "entity-A" if is_call_a else "entity-B",
            )
        return _end_response("done-A" if is_call_a else "done-B")

    runner._client.messages.create = AsyncMock(side_effect=fake_create)
    # Dispatcher finto passato PER-CHIAMATA (il solo ramo che sopravvive
    # dalla fetta E4 Task 6 -- il "dispatcher di scorta" `self._dispatcher`,
    # con cui questo test costruiva il finto prima di questo task, e' uscito:
    # zero chiamanti di produzione lo popolavano, fetta E2 Task 7 commit
    # 68d3670). La meccanica sotto test (isolamento per-Task di
    # last_tool_calls) non dipende da COSA risponde il dispatch, solo dal
    # fatto che risponda.
    finto_dispatcher = MagicMock(dispatch=AsyncMock(return_value={"ok": True}))

    async def call_a():
        text = await runner.chat("call-A", dispatcher=finto_dispatcher)
        return text, list(runner.last_tool_calls)

    async def call_b():
        text = await runner.chat("call-B", dispatcher=finto_dispatcher)
        return text, list(runner.last_tool_calls)

    (text_a, tools_a), (text_b, tools_b) = await asyncio.gather(call_a(), call_b())

    assert text_a == "done-A"
    assert text_b == "done-B"
    assert tools_a == [{"tool": "get_area_entities", "input": {"entity_id": "entity-A"}}]
    assert tools_b == [{"tool": "get_home_status", "input": {"entity_id": "entity-B"}}]


# Fetta "esce il documentale": qui vivevano
# `_DispatcherPseudonimizzaDiScorta` e
# `test_chat_concurrent_calls_do_not_leak_pseudonym_map`. Cadono PER
# COSTRUZIONE: il loro soggetto -- `hiris.app.brain.privacy`
# (`VaultStore`/`Pseudonymizer`) e l'attributo `ClaudeRunner.
# last_pseudonym_map` -- e' uscito con questa fetta. Il test importava il
# modulo alla prima riga del corpo e leggeva `runner.last_pseudonym_map`:
# senza ne' l'uno ne' l'altro non c'e' niente da isolare fra due chiamate
# concorrenti.
#
# L'isolamento per-Task che questo test provava NON resta scoperto:
# `test_chat_concurrent_calls_do_not_leak_tool_calls`, qui sopra, prova lo
# STESSO meccanismo (le ContextVar per-Task di `_PerCallList`) su
# `last_tool_calls`, che resta. Ad andarsene e' solo la variante che lo
# provava attraverso la pseudonimizzazione -- che nel prodotto non girava
# piu': l'unico ramo che popolava la mappa era uscito con la fetta E2 Task 7,
# ed e' il motivo per cui questo stand-in doveva scriverci dentro a mano.


# fetta «i consumi, per modello» (22/08/2026): qui vivevano i test della
# persistenza di `usage.json` -- il silenzio dichiarato su `per_agent` di
# un'installazione precedente, la lettura-modifica-scrittura che non doveva
# perdere chiavi sconosciute, e le scritture concorrenti che non dovevano
# corrompere il file. Sono usciti col loro soggetto: i contatori globali e la
# loro persistenza non esistono piu', il consumo ha una casa sola
# (`consumi/store.py`) e ci arriva per callback.
#
# Il fatto che quei test difendevano -- «mai dati dell'utente rimossi in
# silenzio» -- non e' uscito con loro: i vecchi `usage_*.json` restano sul
# disco e vengono importati una volta sola come riga «(prima del dettaglio)».
# Lo pinna `tests/test_consumi_ancora.py`.

# --- render_template e il perimetro delle entita' ---------------------------
# fetta E2 Task 8 ("escono i trentaquattro"): i tre test che vivevano qui
# (render_template tolto sotto perimetro, lasciato senza, concedibile
# esplicitamente) sono stati cancellati, non spostati. Il loro soggetto era
# la presenza CONDIZIONATA di `render_template` nel catalogo che `chat()`
# offre quando `strumenti` non e' passato -- ma quella definizione (RENDER_
# TEMPLATE_TOOL_DEF) e' uscita da EVALUATION_TOOL_DEFS insieme al resto dei
# 34: non e' nominata da EVALUATION_ONLY_TOOLS (esclusa di proposito, vedi il
# commento su quel set in claude_runner.py), e la chat non offre piu' un
# catalogo da questo file (STRUMENTI_CONOSCENZA, casa/strumenti.py). Nessuna
# combinazione di allowed_tools/allowed_entities puo' piu' far comparire
# "render_template" in un catalogo che non lo contiene: due dei tre test
# fallivano gia' per costruzione, il terzo era diventato vacuo. Il filtro
# stesso (la riga `tools = [t for t in tools if t["name"] != "render_
# template"]` in claude_runner.chat()) resta nel codice come no-op innocuo,
# non e' stato toccato da questo task.


# ---------------------------------------------------------------------------
# L'errore porta con se' che cosa e' successo (Task 11)
#
# Claude NON HA NESSUNA PROTEZIONE -- niente circuito, niente soglia -- e
# viene ritentato integralmente a ogni turno. E' esattamente perche' il
# proprietario paga una chiamata fallita a messaggio da settimane senza che
# niente ceda mai. Questa fetta non gliene da' una (sarebbe un cambio di
# comportamento del ripiego, non una cosa che la pagina mostra): fa in modo
# che la pagina lo DICA.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_un_credito_esaurito_arriva_al_router_come_credenziale_400(runner):
    """Il caso del proprietario, misurato: Anthropic risponde `400 credit
    balance too low`. Fino a questa fetta il 400 moriva qui dentro -- ogni
    `anthropic.APIError` diventava lo stesso «Errore temporaneo del servizio
    AI», e la pagina Modelli non aveva niente da dire."""
    import anthropic

    from hiris.app.claude_runner import RunnerBackendError

    class _Credito(anthropic.APIError):
        def __init__(self):
            Exception.__init__(self, "credit balance too low")
            self.status_code = 400

    with (
        patch.object(runner, "_call_api", AsyncMock(side_effect=_Credito())),
        pytest.raises(RunnerBackendError) as info,
    ):
        await runner.chat("Ciao")

    assert info.value.famiglia == "credenziale"
    assert info.value.codice == 400
    # La frase per l'utente NON cambia: e' cio' che legge in chat, e la chat
    # non e' il posto dove si spiega un guasto di configurazione.
    assert info.value.friendly_message == (
        "Errore temporaneo del servizio AI. Riprova tra poco."
    )


@pytest.mark.asyncio
async def test_un_modello_inesistente_e_un_404_non_un_errore_temporaneo(runner):
    """404 e 400 chiedono due azioni diverse a chi legge -- scegliere un altro
    modello, oppure ricaricare il credito. Collassarli e' cio' che il codice
    faceva."""
    import anthropic

    from hiris.app.claude_runner import RunnerBackendError

    class _Sparito(anthropic.APIError):
        def __init__(self):
            Exception.__init__(self, "model not found")
            self.status_code = 404

    with (
        patch.object(runner, "_call_api", AsyncMock(side_effect=_Sparito())),
        pytest.raises(RunnerBackendError) as info,
    ):
        await runner.chat("Ciao")

    assert info.value.famiglia == "modello" and info.value.codice == 404


@pytest.mark.asyncio
async def test_anthropic_irraggiungibile_non_porta_un_codice_inventato(runner):
    """`anthropic.APIConnectionError` non ha uno stato HTTP: una risposta non
    c'e' mai stata. Il `None` e' il fatto, e la pagina lo dice con parole sue
    («non risponde all'indirizzo») invece di stampare un numero che nessuno ha
    ricevuto."""
    import anthropic
    import httpx

    from hiris.app.claude_runner import RunnerBackendError

    giu = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    with (
        patch.object(runner, "_call_api", AsyncMock(side_effect=giu)),
        pytest.raises(RunnerBackendError) as info,
    ):
        await runner.chat("Ciao")

    assert info.value.famiglia == "irraggiungibile" and info.value.codice is None
