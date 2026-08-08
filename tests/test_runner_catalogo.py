"""Task 2: i runner accettano un catalogo di strumenti (e un dispatcher) dall'esterno.

Oggi il catalogo e' DENTRO il runner (`ALL_TOOL_DEFS`, claude_runner.py) e si
filtra con quattro passaggi in cascata (allowed_tools, render_template contro
il perimetro delle entita', http_request contro allowed_endpoints,
recall_memory/save_memory contro has_memory). Perche' la chat nuova
(`DispatcherConoscenza`, casa/strumenti.py -- quattro strumenti che conoscono
la casa e non la toccano) ne offra quattro invece di trentaquattro, i runner
devono poterli ricevere dall'esterno.

Additivita': quando `strumenti` non e' passato tutto resta com'era prima --
gli altri chiamanti (sorveglianza, agenti, ponte push, test run) non se ne
accorgono. Quando `strumenti` e' passato, i quattro filtri in cascata NON si
applicano: il catalogo passato e' gia' la decisione, applicarli sopra sarebbe
una seconda regola nascosta. Stessa cosa per `dispatcher`: se passato, il
runner lo chiama con `dispatch(nome, argomenti)` -- l'interfaccia minima di
`DispatcherConoscenza` -- non con le kwargs che il dispatcher di scorta del
runner accetta (allowed_entities, chatbot_id, visible_entity_ids, ...; era
`ToolDispatcher`, uscito -- fetta E2 Task 7).
"""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA
from hiris.app.claude_runner import ALL_TOOL_DEFS, ClaudeRunner
from hiris.app.tools.http_tools import HTTP_REQUEST_TOOL_DEF
from hiris.app.tools.memory_tools import RECALL_MEMORY_TOOL_DEF


def test_i_due_runner_accettano_gli_stessi_argomenti():
    """Il vincolo di CLAUDE.md: un kwarg che solo ClaudeRunner accetta rompe i
    backend non-Claude in silenzio. Qui si confronta con inspect, cosi' se uno
    dei due cambia il test cade invece di lasciare divergere."""
    a = set(inspect.signature(ClaudeRunner.chat).parameters)
    b = set(inspect.signature(OpenAICompatRunner.chat).parameters)
    assert {"strumenti", "dispatcher"} <= a
    assert {"strumenti", "dispatcher"} <= b


def test_i_due_runner_accettano_gli_stessi_argomenti_anche_in_streaming():
    """Task 3 della fetta "il contesto della chat viene dal nucleo": il buco
    oltre il brief -- `chat_stream()` non riceveva `strumenti`/`dispatcher`,
    quindi la card Lovelace (che streamma, static/hiris-chat-card.js) sarebbe
    rimasta sul catalogo di trentaquattro strumenti mentre la pagina chat
    (che non streamma, static/chat/send.js) passava ai quattro del nucleo --
    due strade divergenti per la stessa conversazione. Stesso confronto via
    inspect del test gemello sopra, sul metodo streaming."""
    a = set(inspect.signature(ClaudeRunner.chat_stream).parameters)
    b = set(inspect.signature(OpenAICompatRunner.chat_stream).parameters)
    assert {"strumenti", "dispatcher"} <= a
    assert {"strumenti", "dispatcher"} <= b


# --- fixture condivise, stesso pattern di test_claude_runner.py / -----------
# --- test_openai_compat_runner.py -------------------------------------------

@pytest.fixture
def claude_runner():
    # Nessun dispatcher di scorta -> self._dispatcher e' None -> has_memory
    # degrada a False (vedi claude_runner.py): serve al test che verifica
    # che i quattro filtri NON si applichino quando `strumenti` e' passato
    # (senza `strumenti`, recall_memory/save_memory sparirebbero da qui).
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key")
    return r


@pytest.fixture
def openai_runner(tmp_path):
    return OpenAICompatRunner(
        base_url="https://api.openai.com/v1", api_key="sk-test",
        usage_path=str(tmp_path / "u.json"),
    )


async def _tools_di_chat_claude(runner, **kw) -> set:
    catturati: dict = {}

    async def capture(**kwargs):
        catturati.update(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", **kw)
    return {t["name"] for t in catturati["tools"]}


def _risposta_openai_senza_tool():
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = "ok"
    choice.message.tool_calls = []
    resp.choices = [choice]
    resp.usage.prompt_tokens = 5
    resp.usage.completion_tokens = 2
    return resp


async def _tools_di_chat_openai(runner, **kw) -> set:
    catturati: dict = {}

    async def capture(**kwargs):
        catturati.update(kwargs)
        return _risposta_openai_senza_tool()

    runner._client.chat.completions.create = capture
    await runner.chat(user_message="Ciao", model="gpt-4o", max_tokens=64, **kw)
    return {t["function"]["name"] for t in catturati.get("tools", [])}


# --- senza `strumenti`: nessuna regressione ---------------------------------

@pytest.mark.asyncio
async def test_claude_senza_strumenti_offre_il_catalogo_di_sempre(claude_runner):
    """Additivita': non passando `strumenti`, il catalogo resta ALL_TOOL_DEFS
    filtrato dai quattro passaggi in cascata come oggi -- has_memory=False
    qui toglie recall_memory/save_memory, non essendoci `strumenti`."""
    nomi = await _tools_di_chat_claude(claude_runner)
    # has_memory=False toglie recall_memory/save_memory; allowed_endpoints
    # non passato (None di default) toglie http_request -- stessi due filtri
    # che oggi si applicano SEMPRE quando `strumenti` non c'e'.
    attesi = {t["name"] for t in ALL_TOOL_DEFS} - {"recall_memory", "save_memory", "http_request"}
    assert nomi == attesi


@pytest.mark.asyncio
async def test_openai_senza_strumenti_offre_il_catalogo_di_sempre(openai_runner):
    nomi = await _tools_di_chat_openai(openai_runner)
    attesi = {t["name"] for t in ALL_TOOL_DEFS} - {"recall_memory", "save_memory", "http_request"}
    assert nomi == attesi


# --- con `strumenti`: esattamente quelli, nessun altro ----------------------

@pytest.mark.asyncio
async def test_claude_con_strumenti_offre_esattamente_quelli(claude_runner):
    nomi = await _tools_di_chat_claude(claude_runner, strumenti=STRUMENTI_CONOSCENZA)
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}


@pytest.mark.asyncio
async def test_openai_con_strumenti_offre_esattamente_quelli(openai_runner):
    nomi = await _tools_di_chat_openai(openai_runner, strumenti=STRUMENTI_CONOSCENZA)
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}


# --- con `strumenti`, i quattro filtri in cascata NON si applicano ---------
# http_request verrebbe tolto da `allowed_endpoints is None`; recall_memory
# verrebbe tolto da `not dispatcher.has_memory` (qui False, vedi fixture). Con
# `strumenti` passato esplicitamente il catalogo e' gia' la decisione: nessuno
# dei due va tolto.

@pytest.mark.asyncio
async def test_claude_con_strumenti_i_filtri_non_si_applicano(claude_runner):
    nomi = await _tools_di_chat_claude(
        claude_runner,
        strumenti=[HTTP_REQUEST_TOOL_DEF, RECALL_MEMORY_TOOL_DEF],
        allowed_endpoints=None,
    )
    assert nomi == {"http_request", "recall_memory"}


@pytest.mark.asyncio
async def test_openai_con_strumenti_i_filtri_non_si_applicano(openai_runner):
    nomi = await _tools_di_chat_openai(
        openai_runner,
        strumenti=[HTTP_REQUEST_TOOL_DEF, RECALL_MEMORY_TOOL_DEF],
        allowed_endpoints=None,
    )
    assert nomi == {"http_request", "recall_memory"}


# --- con `dispatcher`, si chiama dispatch(nome, argomenti) ------------------
# Non le kwargs pensate per ToolDispatcher (allowed_entities, chatbot_id,
# visible_entity_ids, ...): DispatcherConoscenza espone solo l'interfaccia
# minima dichiarata in casa/strumenti.py.

@pytest.mark.asyncio
async def test_claude_con_dispatcher_esterno_chiama_linterfaccia_minima(claude_runner):
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.id = "tu_1"
    tool_use_block.name = "cerca"
    tool_use_block.input = {"testo": "bagno"}
    text_block = MagicMock(type="text", text="trovato")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_use_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])

    finto_dispatcher = MagicMock()
    finto_dispatcher.dispatch = AsyncMock(return_value={"trovati": []})

    claude_runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await claude_runner.chat(
        "cerca il bagno", strumenti=STRUMENTI_CONOSCENZA, dispatcher=finto_dispatcher,
    )

    assert result == "trovato"
    finto_dispatcher.dispatch.assert_awaited_once_with("cerca", {"testo": "bagno"})


@pytest.mark.asyncio
async def test_openai_con_dispatcher_esterno_chiama_linterfaccia_minima(openai_runner):
    tc = MagicMock()
    tc.id = "tc_1"
    tc.function.name = "cerca"
    tc.function.arguments = '{"testo": "bagno"}'
    choice1 = MagicMock(finish_reason="tool_calls")
    choice1.message.content = None
    choice1.message.tool_calls = [tc]
    resp1 = MagicMock(choices=[choice1])
    resp1.usage.prompt_tokens = 5
    resp1.usage.completion_tokens = 2

    choice2 = MagicMock(finish_reason="stop")
    choice2.message.content = "trovato"
    choice2.message.tool_calls = []
    resp2 = MagicMock(choices=[choice2])
    resp2.usage.prompt_tokens = 5
    resp2.usage.completion_tokens = 2

    finto_dispatcher = MagicMock()
    finto_dispatcher.dispatch = AsyncMock(return_value={"trovati": []})

    openai_runner._client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    result = await openai_runner.chat(
        user_message="cerca il bagno", model="gpt-4o",
        strumenti=STRUMENTI_CONOSCENZA, dispatcher=finto_dispatcher,
    )

    assert result == "trovato"
    finto_dispatcher.dispatch.assert_awaited_once_with("cerca", {"testo": "bagno"})


# --- Task 3: lo stesso, ma per `chat_stream()` -------------------------------
# `ClaudeRunner.chat_stream` e' gia' un guscio sottile attorno a `chat()`
# (vedi il suo docstring): il pass-through e' quindi coperto per transitivita'
# dai test sopra, e replicarlo qui aggiungerebbe solo rumore. `OpenAICompat
# Runner.chat_stream` invece costruisce il proprio loop agentico da zero --
# qui sotto gli stessi due comportamenti (catalogo esatto, dispatch minimo)
# verificati sul VERO metodo streaming, non per estrapolazione da chat().

def _fake_delta(content=None, tool_calls=None):
    d = MagicMock()
    d.content = content
    d.tool_calls = tool_calls
    return d


def _fake_chunk(*, content=None, tool_calls=None, finish_reason=None):
    choice = MagicMock()
    choice.delta = _fake_delta(content=content, tool_calls=tool_calls)
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _fake_tc_delta(index, *, id_=None, name=None, arguments=None):
    d = MagicMock()
    d.index = index
    d.id = id_
    d.function = MagicMock()
    d.function.name = name
    d.function.arguments = arguments
    return d


async def _fake_stream(chunks):
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_openai_stream_con_strumenti_offre_esattamente_quelli(openai_runner):
    catturati: dict = {}

    async def capture(**kwargs):
        catturati.update(kwargs)
        return _fake_stream([_fake_chunk(content="ok", finish_reason="stop")])

    openai_runner._client.chat.completions.create = capture
    async for _ in openai_runner.chat_stream(
        user_message="ciao", model="gpt-4o", strumenti=STRUMENTI_CONOSCENZA,
    ):
        pass

    nomi = {t["function"]["name"] for t in catturati.get("tools", [])}
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}


@pytest.mark.asyncio
async def test_openai_stream_con_dispatcher_esterno_chiama_linterfaccia_minima(openai_runner):
    finto_dispatcher = MagicMock()
    finto_dispatcher.dispatch = AsyncMock(return_value={"trovati": []})

    chiamate = {"n": 0}

    async def capture(**kwargs):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            tc = _fake_tc_delta(0, id_="tc_1", name="cerca", arguments='{"testo": "bagno"}')
            return _fake_stream([_fake_chunk(tool_calls=[tc], finish_reason="tool_calls")])
        return _fake_stream([_fake_chunk(content="trovato", finish_reason="stop")])

    openai_runner._client.chat.completions.create = capture
    async for _ in openai_runner.chat_stream(
        user_message="cerca il bagno", model="gpt-4o",
        strumenti=STRUMENTI_CONOSCENZA, dispatcher=finto_dispatcher,
    ):
        pass

    finto_dispatcher.dispatch.assert_awaited_once_with("cerca", {"testo": "bagno"})
