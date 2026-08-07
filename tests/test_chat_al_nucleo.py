"""Task 3 ("il contesto della chat viene dal nucleo"): una fonte sola.

Prima `handle_chat` montava il contesto da quattro fonti indipendenti
(handlers_chat.py:449-461 prima di questa fetta): i fatti dichiarati
(KnowledgeStore.declared()), un blocco RAG (KnowledgeStore.search()), le
sessioni precedenti, e SemanticContextMap.get_context() -- e il ritratto (lo
stato vivo della casa, l'anagrafe) non lo vedeva MAI: e' la sovrapposizione
n.1 della mappa del prodotto, vista da dentro (due intelligenze nella stessa
casa che ne vedono due diverse, vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md, §7).

Dopo: una fonte sola, il nucleo (`hiris.app.casa.nucleo.componi`, condiviso
con GET /api/nucleo tramite `handlers_casa.costruisci_nucleo` -- stessa
composizione per la rotta e per la chat, non due che potrebbero divergere).
Le sessioni precedenti restano A PARTE: sono cronologia di conversazioni
chiuse, non conoscenza sulla casa.

Segue la convenzione REST-vera gia' in tests/test_handlers_casa.py (per
`/api/nucleo`) e, prima di questa fetta, in tests/test_declared_block_chat.py
(ora rimosso -- testava esattamente la sovrapposizione che questo task
chiude, vedi il rapporto): un `client` costruito con `create_app()` +
`aiohttp_client`, che legge `context_str`/`strumenti`/`dispatcher` da
`mock_runner.chat.call_args.kwargs` -- esattamente cio' che `handle_chat`
consegna davvero al runner.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.strumenti import DispatcherConoscenza
from hiris.app.chat_store import _get_store, _TS_FMT, close_all_stores
from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot, ChatbotEngine
from hiris.app.memoria.archivio import ArchivioMemoria
from hiris.app.server import create_app


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


class _CacheFinta:
    """Sostituto minimo di `EntityCache` -- stessa forma usata da
    tests/test_handlers_casa.py per `handle_get_nucleo`: `all_states()`
    restituisce dict con chiave "id" (non "entity_id"), e `loaded` governa
    `inventario_leggibile()`."""

    def __init__(self, stati: list[dict], *, pronta: bool = True) -> None:
        self._stati = stati
        self.loaded = pronta

    def all_states(self) -> list[dict]:
        return self._stati


async def _build_chat_client(aiohttp_client, tmp_path, *, archivio_casa=None,
                             archivio_memoria=None, cache=None):
    """Stessa forma di `_build_chat_client` nei test di chat pre-esistenti
    (tests/test_memoria_ricorda.py e affini, prima che questa fetta la
    ritirasse da li'), con gli archivi del nucleo al posto di
    `knowledge_store`/`embedding_provider` -- e' cio' da cui la chat legge
    adesso."""
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="base prompt",
        allowed_tools=[], enabled=True, is_default=True,
    )

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    if archivio_casa is not None:
        app["archivio_casa"] = archivio_casa
    if archivio_memoria is not None:
        app["archivio_memoria"] = archivio_memoria
    if cache is not None:
        app["entity_cache"] = cache

    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    return client, mock_runner


def _semina_casa(tmp_path) -> ArchivioCasa:
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [],
        "entita": [{"entity_id": "light.cucina", "name": "Faretti", "area_id": "cucina"}],
        "etichette": [], "categorie": [], "integrazioni": [],
    })
    return archivio


# ---------------------------------------------------------------------------
# Step 1: il prompt contiene le sezioni del nucleo, e NON piu' "## Contesto
# casa" (l'intestazione con cui SemanticContextMap.get_context() entrava nel
# prompt prima di questa fetta).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_contesto_della_chat_e_il_nucleo(aiohttp_client, tmp_path):
    archivio_casa = _semina_casa(tmp_path)
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    # Le sezioni del nucleo -- lo stesso testo che GET /api/nucleo mostra --
    # non le quattro vecchie intestazioni.
    assert "## La casa" in context_str
    assert "## Notevole adesso" in context_str
    assert "## Cio' che la casa fa gia' da sola" in context_str
    assert "Cucina" in context_str
    assert "## Contesto casa" not in context_str
    archivio_casa.chiudi()


@pytest.mark.asyncio
async def test_il_ritratto_ora_entra_nel_contesto_della_chat(aiohttp_client, tmp_path):
    """La sovrapposizione n.1 della mappa: prima di questa fetta nessuna
    delle fonti di `handle_chat` guardava lo stato vivo -- ora "Notevole
    adesso" (dal nucleo) sa che la luce e' accesa."""
    archivio_casa = _semina_casa(tmp_path)
    cache = _CacheFinta([{"id": "light.cucina", "state": "on"}])
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa, cache=cache,
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "Faretti" in context_str  # accesa: e' notevole -- il ritratto, non solo l'anagrafe
    archivio_casa.chiudi()


# ---------------------------------------------------------------------------
# Step 1: il runner riceve esattamente cerca/guarda/ricorda/richiama --
# entrambi i punti in cui `handle_chat` puo' chiamare il runner (streaming e
# non), non solo uno.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_la_chat_offre_quattro_strumenti(aiohttp_client, tmp_path):
    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    call_kwargs = mock_runner.chat.call_args.kwargs
    nomi = {t["name"] for t in call_kwargs["strumenti"]}
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}
    assert isinstance(call_kwargs["dispatcher"], DispatcherConoscenza)


@pytest.mark.asyncio
async def test_lo_streaming_offre_gli_stessi_quattro_strumenti(aiohttp_client, tmp_path):
    """Il buco oltre il brief: la card Lovelace usa lo streaming
    (static/hiris-chat-card.js), la pagina chat no (static/chat/send.js) --
    se solo una delle due ricevesse `strumenti`/`dispatcher`, sarebbero due
    strade divergenti per la stessa conversazione (esattamente il difetto
    che questa fetta esiste per chiudere). Qui si passa dallo stesso
    `handle_chat`, ramo SSE."""
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="base prompt",
        allowed_tools=[], enabled=True, is_default=True,
    )

    catturati: dict = {}

    async def fake_chat_stream(**kwargs):
        import json
        catturati.update(kwargs)
        yield f'data: {json.dumps({"type": "token", "text": "ok"})}\n\n'
        yield f'data: {json.dumps({"type": "done", "agent_id": None, "tool_calls": []})}\n\n'

    mock_runner = AsyncMock()
    mock_runner.chat_stream = fake_chat_stream
    mock_runner.last_tool_calls = []
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    client = await aiohttp_client(app)

    resp = await client.post("/api/chat", json={"message": "ciao", "stream": True})
    assert resp.status == 200
    await resp.text()

    nomi = {t["name"] for t in catturati["strumenti"]}
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}
    assert isinstance(catturati["dispatcher"], DispatcherConoscenza)


# ---------------------------------------------------------------------------
# Step 1: "diciannovesima comparsa evitata" -- senza archivi, la chat non
# deve rispondere come se conoscesse la casa. Deve dirlo, nel contesto che
# il modello legge (non solo in un riepilogo che nessuno passa al modello).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_se_il_nucleo_non_si_compone_la_chat_lo_dice(aiohttp_client, tmp_path):
    """Nessun `archivio_casa` wired nell'app (il caso difensivo di
    `costruisci_nucleo`/`handle_get_nucleo` quando `_on_startup` non e'
    ancora girato) -- stessa lacuna che
    tests/test_handlers_casa.py::test_api_nucleo_senza_archivi_non_afferma_di_sapere
    verifica per /api/nucleo, qui verificata per il contesto che la chat
    passa davvero al modello."""
    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "Nessun piano registrato." in context_str
    assert "non si e' potuto guardare" in context_str
    # Mai un nucleo vuoto spacciato per una casa vuota: "Notevole adesso" deve
    # dire "non ho potuto guardare", non "niente di notevole".
    assert "Niente di notevole al momento." not in context_str


# ---------------------------------------------------------------------------
# Step 1: le sessioni precedenti restano -- sono cronologia, non conoscenza,
# quindi vivono A PARTE dal nucleo (non dentro di esso).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_le_sessioni_precedenti_restano(aiohttp_client, tmp_path):
    from datetime import datetime, timezone

    archivio_casa = _semina_casa(tmp_path)
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    # Stesso pattern di tests/test_chat_store.py::test_get_past_summaries_returns_closed_sessions:
    # una sessione GIA' chiusa (summary non nullo), inserita direttamente nella
    # stessa ChatStore che `handle_chat` legge per questo `data_dir`.
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    store = _get_store(str(tmp_path))
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at, summary) "
        "VALUES(?,?,?,?,?)",
        ("closed-1", DEFAULT_CHATBOT_ID, ts, ts, "parlato di irrigazione del giardino"),
    )
    store._conn.commit()

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "## Sessioni precedenti" in context_str
    assert "irrigazione del giardino" in context_str
    # Cronologia, non conoscenza: non e' dentro nessuna sezione del nucleo.
    assert "## La casa" in context_str  # il nucleo c'e' comunque, a fianco
    archivio_casa.chiudi()


@pytest.mark.asyncio
async def test_le_sessioni_precedenti_restano_anche_senza_nucleo(aiohttp_client, tmp_path):
    """Le due fonti sono indipendenti: una chat senza archivi (nucleo
    degradato) deve comunque mostrare la cronologia delle sessioni chiuse --
    non e' il nucleo a deciderne la presenza."""
    from datetime import datetime, timezone

    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    store = _get_store(str(tmp_path))
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at, summary) "
        "VALUES(?,?,?,?,?)",
        ("closed-1", DEFAULT_CHATBOT_ID, ts, ts, "parlato di irrigazione del giardino"),
    )
    store._conn.commit()

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "## Sessioni precedenti" in context_str
    assert "irrigazione del giardino" in context_str
