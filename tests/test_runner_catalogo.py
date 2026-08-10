"""Task 2: i runner accettano un catalogo di strumenti (e un dispatcher) dall'esterno.

fetta E3 Task 8: il catalogo che una volta viveva DENTRO il runner
(`EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS`, claude_runner.py -- la
Sentinella, filtrata con quattro passaggi in cascata: allowed_tools,
render_template contro il perimetro delle entita', http_request contro
allowed_endpoints, recall_memory/save_memory contro has_memory) e' uscito
insieme al suo unico chiamante, `run_with_actions` (la Sentinella e' uscita
al Task 7). Senza `strumenti`, `chat()` non offre piu' nessun tool -- i due
test che pinnavano il vecchio fallback (`EVALUATION_TOOL_DEFS` filtrato) sono
usciti con lui, non spostati: il loro soggetto non esiste piu'.

Il soggetto di QUESTO file pero' e' un altro, ed e' vivo: perche' la chat
(`DispatcherConoscenza`, casa/strumenti.py -- quattro strumenti che conoscono
la casa e non la toccano) offra quattro strumenti invece del catalogo
interno, i runner devono poterli ricevere dall'esterno. Quando `strumenti` e'
passato, i quattro filtri in cascata (gia' spariti insieme al catalogo che
filtravano) NON si applicano comunque: il catalogo passato e' gia' la
decisione. Stessa cosa per `dispatcher`: se passato, il runner lo chiama con
`dispatch(nome, argomenti)` -- l'interfaccia minima di `DispatcherConoscenza`
-- non con le kwargs che il dispatcher di scorta del runner accetta
(allowed_entities, chatbot_id, visible_entity_ids, ...; era `ToolDispatcher`,
uscito -- fetta E2 Task 7).
"""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA
from hiris.app.claude_runner import ClaudeRunner

# fetta E2 Task 8: `tools/http_tools.py` e' uscito per intero (HTTP_REQUEST_
# TOOL_DEF non serve a EVALUATION_ONLY_TOOLS, e `http_request` era gia'
# orfana dal Task 7). I due test sotto che lo usavano non provano
# `http_request` in se': provano che i quattro filtri in cascata (qui quello
# su `allowed_endpoints`) NON si applicano quando `strumenti` e' passato
# esplicitamente -- serve solo un tool_def qualunque il cui NOME sia uno che
# quel filtro toglierebbe. Un dizionario minimo locale, non importato da
# nessun modulo di produzione, prova esattamente la stessa cosa.
_FINTO_HTTP_REQUEST_TOOL_DEF = {
    "name": "http_request",
    "description": "finto, solo per provare il bypass dei filtri a cascata",
    "input_schema": {"type": "object", "properties": {}},
}

# fetta E3 Task 8: `tools/memory_tools.py` (da cui veniva RECALL_MEMORY_TOOL_
# DEF) e' uscito per intero insieme all'intera cartella `tools/` -- stesso
# ragionamento del finto http_request sopra: al test sotto non serve la
# definizione VERA, solo un tool_def il cui nome sia "recall_memory".
_FINTO_RECALL_MEMORY_TOOL_DEF = {
    "name": "recall_memory",
    "description": "finto, solo per provare il bypass dei filtri a cascata",
    "input_schema": {"type": "object", "properties": {}},
}


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
    # fix round 1 (Important 3 della review indipendente): questo commento
    # diceva "Nessun dispatcher di scorta -> self._dispatcher e' None" -- ma
    # `self._dispatcher` non esiste piu' come attributo, ne' il costruttore
    # accetta piu' un `dispatcher=` (fetta E4 Task 6: il "dispatcher di
    # scorta" e' uscito per intero, non solo reso inerte come alla fetta E3
    # Task 8 quando questo commento fu scritto). Resta il pattern minimo
    # condiviso con test_claude_runner.py, senza piu' nulla da tacere sopra.
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


# --- senza `strumenti`: nessun catalogo di scorta ---------------------------
# fetta E3 Task 8: `EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS` (il vecchio
# fallback) sono usciti insieme al loro unico chiamante, `run_with_actions`
# (la Sentinella, uscita al Task 7). L'"additivita'" che questi due test
# pinnavano -- "senza `strumenti` tutto resta com'era prima" -- non descrive
# piu' nessun chiamante reale: chatbot_engine.py e api/handlers_chat.py
# passano sempre `strumenti=STRUMENTI_CONOSCENZA`. Il nuovo comportamento e'
# piu' semplice da dichiarare che da giustificare: senza `strumenti`, nessun
# tool.

@pytest.mark.asyncio
async def test_claude_senza_strumenti_non_offre_alcun_tool(claude_runner):
    nomi = await _tools_di_chat_claude(claude_runner)
    assert nomi == set()


@pytest.mark.asyncio
async def test_openai_senza_strumenti_non_offre_alcun_tool(openai_runner):
    nomi = await _tools_di_chat_openai(openai_runner)
    assert nomi == set()


# --- con `strumenti`: esattamente quelli, nessun altro ----------------------

@pytest.mark.asyncio
async def test_claude_con_strumenti_offre_esattamente_quelli(claude_runner):
    nomi = await _tools_di_chat_claude(claude_runner, strumenti=STRUMENTI_CONOSCENZA)
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}


@pytest.mark.asyncio
async def test_openai_con_strumenti_offre_esattamente_quelli(openai_runner):
    nomi = await _tools_di_chat_openai(openai_runner, strumenti=STRUMENTI_CONOSCENZA)
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}


# --- con `strumenti`, nessun filtro in cascata (mai esistito su questo ramo) -
# fetta E3 Task 8: i quattro filtri che un tempo restringevano il fallback
# (allowed_endpoints contro http_request, has_memory contro recall_memory,
# ecc.) sono usciti insieme al fallback stesso -- non sono mai esistiti sul
# ramo `strumenti is not None`, che passa il catalogo del chiamante cosi'
# com'e' da prima di questo task. Il test prova esattamente questo: nomi
# "sensibili" come http_request/recall_memory, se dentro `strumenti`, NON
# vengono tolti -- non c'e' nessuna seconda regola nascosta sopra la
# decisione del chiamante. fetta E4 Task 6: il kwarg `allowed_endpoints`
# stesso (passato qui sotto come prova esplicita del non-filtro) e' uscito
# dalla firma di `chat()` -- non c'e' piu' nulla da passare, la prova resta
# la stessa senza di lui: nessun secondo filtro di NESSUN tipo si applica.

@pytest.mark.asyncio
async def test_claude_con_strumenti_nessun_filtro_si_applica(claude_runner):
    nomi = await _tools_di_chat_claude(
        claude_runner,
        strumenti=[_FINTO_HTTP_REQUEST_TOOL_DEF, _FINTO_RECALL_MEMORY_TOOL_DEF],
    )
    assert nomi == {"http_request", "recall_memory"}


@pytest.mark.asyncio
async def test_openai_con_strumenti_nessun_filtro_si_applica(openai_runner):
    nomi = await _tools_di_chat_openai(
        openai_runner,
        strumenti=[_FINTO_HTTP_REQUEST_TOOL_DEF, _FINTO_RECALL_MEMORY_TOOL_DEF],
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
