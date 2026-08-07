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
import json

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.strumenti import DispatcherConoscenza
from hiris.app.chat_store import _get_store, _TS_FMT, close_all_stores
from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot, ChatbotEngine
from hiris.app.claude_runner import ClaudeRunner
from hiris.app.memoria.archivio import ArchivioMemoria
from hiris.app.server import create_app
from hiris.app.tools.dispatcher import ToolDispatcher
from tests.test_strumenti_conoscenza import _semina_casa as _semina_casa_con_comportamento


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
    # -- fine dei test pre-esistenti (Task 3) --


# ---------------------------------------------------------------------------
# Task 4 ("guardarla funzionare"): le quattro conversazioni che la chat
# nuova deve saper fare meglio di quella vecchia, verificate col protocollo
# VERO -- un `ClaudeRunner` reale, con SOLO la telefonata di rete
# (`_client.messages.create`) finta. Riusa la stessa forma di
# tests/test_runner_catalogo.py::test_claude_con_dispatcher_esterno_chiama_
# linterfaccia_minima (risposte MagicMock in sequenza, stop_reason
# "tool_use"/"end_turn", `runner._client.messages.create` sostituito): un
# modello che simulasse la risposta finale senza passare da li' non
# proverebbe niente -- e' il difetto che la prova di mutazione ha gia'
# trovato sette volte su questo ramo.
#
# `DispatcherConoscenza`, gli archivi (`ArchivioCasa`, `ArchivioMemoria`) e
# `handle_chat` restano codice di produzione vero, esattamente come nella
# chat reale -- solo la rete verso Anthropic e' finta.
# ---------------------------------------------------------------------------

async def _build_chat_client_runner_reale(aiohttp_client, tmp_path, *, archivio_casa=None,
                                          archivio_memoria=None, cache=None):
    """Come `_build_chat_client` sopra, ma con un `ClaudeRunner` VERO al
    posto del mock -- l'unico modo per verificare che la chat segua il
    protocollo vero degli strumenti (richiesta -> tool_use -> tool_result ->
    risposta) invece di un finto che si limita a restituire una stringa."""
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

    # Solo il client HTTP verso Anthropic e' finto (`anthropic.AsyncAnthropic`
    # patchato in costruzione, stessa forma della fixture `claude_runner` di
    # tests/test_runner_catalogo.py) -- il resto del runner (il loop
    # tool_use/tool_result dentro `chat()`) e' vero.
    with patch("anthropic.AsyncAnthropic"):
        runner = ClaudeRunner(api_key="test-key", dispatcher=ToolDispatcher(mock_ha, {}))
    engine.set_claude_runner(runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = runner
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
    return client, runner


def _falsa_risposta_testo(testo: str) -> MagicMock:
    blocco = MagicMock(type="text", text=testo)
    return MagicMock(stop_reason="end_turn", content=[blocco])


def _falsa_risposta_tool_use(nome: str, argomenti: dict, id_: str = "tu_1") -> MagicMock:
    blocco = MagicMock()
    blocco.type = "tool_use"
    blocco.id = id_
    blocco.name = nome
    blocco.input = argomenti
    return MagicMock(stop_reason="tool_use", content=[blocco])


# ---------------------------------------------------------------------------
# Conversazione 1: "cosa c'e' in cucina?" -- il nucleo conta gia' le entita'
# per area (tests/test_nucleo.py::test_il_nucleo_conta_invece_di_elencare):
# un modello che ha quel conteggio nel proprio system prompt non ha nessun
# bisogno di chiamare `guarda`. Se lo chiamasse, sarebbe il nucleo a non
# fare il suo lavoro, non il modello a sbagliare -- qui si verifica che il
# giro finisce in UNA sola chiamata API, senza tool_use.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_1_cosa_c_e_in_cucina_risponde_dal_nucleo(aiohttp_client, tmp_path):
    archivio_casa = _semina_casa_con_comportamento(tmp_path)
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    richieste: list[dict] = []

    async def _api_finta(**kwargs):
        richieste.append(kwargs)
        return _falsa_risposta_testo("In cucina hai due luci e un sensore di temperatura.")

    runner._client.messages.create = _api_finta

    resp = await client.post("/api/chat", json={"message": "cosa c'e' in cucina?"})
    assert resp.status == 200
    body = await resp.json()

    # Il conteggio per area era gia' nel prompt: e' la prova che il nucleo
    # fa il suo lavoro, non solo che il modello (finto) ha risposto bene.
    testo_sistema = "\n".join(b["text"] for b in richieste[0]["system"])
    assert "Cucina" in testo_sistema
    assert "2 luci" in testo_sistema

    # Un solo giro: il modello non ha avuto bisogno di chiamare nessuno
    # strumento -- se ne avesse avuto bisogno, il nucleo non stava facendo
    # il suo lavoro.
    assert len(richieste) == 1
    assert runner.last_tool_calls == []
    assert body["debug"]["tools_called"] == []
    assert body["response"] == "In cucina hai due luci e un sensore di temperatura."

    archivio_casa.chiudi()


# ---------------------------------------------------------------------------
# Conversazione 2: "cosa fa l'automazione della sveglia?" -- la Legge I che
# smette di essere sulla carta. Il modello chiama `guarda`, il dispatcher
# VERO legge il corpo VERO dall'archivio, e il SECONDO giro della stessa
# conversazione (la seconda chiamata API vera, non una supposizione del
# test) riceve quel corpo dentro il proprio tool_result.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_2_cosa_fa_la_sveglia_chiama_guarda_e_riporta_il_corpo(
    aiohttp_client, tmp_path,
):
    archivio_casa = _semina_casa_con_comportamento(tmp_path)  # porta automation.sveglia
    # DispatcherConoscenza._guarda legge SEMPRE anche l'archivio della
    # memoria (per i ricordi ancorati alla cosa guardata): in produzione
    # `_on_startup` (server.py) lo cabla sempre insieme a `archivio_casa`,
    # mai l'uno senza l'altro -- qui si replica lo stesso accoppiamento,
    # non se ne fa a meno.
    archivio_memoria = ArchivioMemoria(str(tmp_path / "memoria_conversazione_2.db"))
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa, archivio_memoria=archivio_memoria,
    )

    richieste: list[dict] = []
    giro = {"n": 0}

    async def _api_finta(**kwargs):
        richieste.append(kwargs)
        giro["n"] += 1
        if giro["n"] == 1:
            return _falsa_risposta_tool_use(
                "guarda", {"tipo": "automazione", "riferimento": "automation.sveglia"})
        return _falsa_risposta_testo(
            "La sveglia ha un trigger configurato, l'ho letto dal suo corpo vero.")

    runner._client.messages.create = _api_finta

    resp = await client.post(
        "/api/chat", json={"message": "cosa fa l'automazione della sveglia?"})
    assert resp.status == 200
    body = await resp.json()

    # Il tool chiamato e' esattamente quello giusto, coi giusti argomenti --
    # riportato al client nel debug payload (handlers_chat.py::handle_chat).
    assert body["debug"]["tools_called"] == [
        {"tool": "guarda", "input": {"tipo": "automazione", "riferimento": "automation.sveglia"}}
    ]

    # La prova vera: il SECONDO giro della stessa conversazione -- non
    # un'assunzione del test, la vera seconda chiamata a
    # `_client.messages.create` -- porta nel proprio `tool_result` il corpo
    # VERO letto dall'archivio VERO (ArchivioCasa.sostituisci_comportamento,
    # tests/test_strumenti_conoscenza.py -- automation.sveglia: {"trigger": []}).
    assert len(richieste) == 2
    ultimo_messaggio = richieste[1]["messages"][-1]
    assert ultimo_messaggio["role"] == "user"
    blocco_risultato = ultimo_messaggio["content"][0]
    assert blocco_risultato["type"] == "tool_result"
    corpo_ricevuto_dal_modello = json.loads(blocco_risultato["content"])
    assert corpo_ricevuto_dal_modello["esiste"] is True
    assert corpo_ricevuto_dal_modello["corpo"] == {"trigger": []}

    assert body["response"] == "La sveglia ha un trigger configurato, l'ho letto dal suo corpo vero."

    archivio_casa.chiudi()
    archivio_memoria.chiudi()


# ---------------------------------------------------------------------------
# Conversazione 3: «d'inverno il soggiorno ideale e' 19.5» -- la frase esatta
# da cui e' nato l'intero refactor. HIRIS aveva risposto "preso nota" SENZA
# salvare niente: qui si verifica la scrittura vera, non che il modello
# abbia DETTO di averlo fatto -- una GET /api/memoria separata, dopo che la
# risposta della chat e' gia' tornata, sulla STESSA app (stesso archivio).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_3_ricorda_salva_davvero_e_si_ritrova_in_api_memoria(
    aiohttp_client, tmp_path,
):
    archivio_casa = _semina_casa_con_comportamento(tmp_path)
    archivio_memoria = ArchivioMemoria(str(tmp_path / "memoria_reale.db"))
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa, archivio_memoria=archivio_memoria,
    )

    frase = "d'inverno il soggiorno ideale e' 19.5"
    giro = {"n": 0}

    async def _api_finta(**kwargs):
        giro["n"] += 1
        if giro["n"] == 1:
            return _falsa_risposta_tool_use("ricorda", {"testo": frase, "forza": "preferenza"})
        return _falsa_risposta_testo("Preso nota -- e stavolta l'ho anche salvato.")

    runner._client.messages.create = _api_finta

    resp = await client.post("/api/chat", json={"message": frase})
    assert resp.status == 200
    body = await resp.json()
    assert body["debug"]["tools_called"] == [
        {"tool": "ricorda", "input": {"testo": frase, "forza": "preferenza"}}
    ]

    # La prova vera: NON il testo della risposta (che qui il modello finto
    # controlla), ma una richiesta HTTP separata sull'archivio vero.
    resp_memoria = await client.get("/api/memoria")
    assert resp_memoria.status == 200
    corpo_memoria = await resp_memoria.json()
    assert corpo_memoria["disponibile"] is True
    testi_salvati = [r["testo"] for r in corpo_memoria["ricordi"]]
    assert frase in testi_salvati, (
        "il difetto originale -- 'preso nota' senza salvare niente -- tornerebbe "
        "esattamente qui: la frase deve trovarsi DAVVERO nell'archivio della memoria"
    )

    archivio_casa.chiudi()
    archivio_memoria.chiudi()


# ---------------------------------------------------------------------------
# Conversazione 4: "accendi la luce della cucina" -- non puo', e lo dice
# bene: fra gli strumenti offerti al modello non ce n'e' NESSUNO che scriva
# in Home Assistant. Un modello onesto, senza un tool che lo permetta, non
# ci prova nemmeno -- risponde direttamente, senza un giro di tool_use
# fallito.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_4_accendi_la_luce_non_puo_e_lo_dice(aiohttp_client, tmp_path):
    archivio_casa = _semina_casa_con_comportamento(tmp_path)
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    richieste: list[dict] = []

    async def _api_finta(**kwargs):
        richieste.append(kwargs)
        return _falsa_risposta_testo(
            "Non posso accendere la luce della cucina: non ho nessuno strumento che "
            "scriva su Home Assistant. Posso solo conoscere la casa -- cercarla, "
            "guardarla, ricordare cosa mi hai detto."
        )

    runner._client.messages.create = _api_finta

    resp = await client.post("/api/chat", json={"message": "accendi la luce della cucina"})
    assert resp.status == 200
    body = await resp.json()

    # Nessuno strumento offerto scrive in Home Assistant -- non solo i
    # quattro nomi esatti, ma esplicitamente NESSUNO dei nomi che nel
    # catalogo vecchio (claude_runner.ALL_TOOL_DEFS) attuano davvero
    # (CONFIRMATION_COVERED_TOOLS, claude_runner.py).
    nomi_offerti = {t["name"] for t in richieste[0]["tools"]}
    assert nomi_offerti == {"cerca", "guarda", "ricorda", "richiama"}
    strumenti_che_scrivono = {
        "call_ha_service", "trigger_automation", "toggle_automation",
        "set_input_helper", "create_ha_config",
    }
    assert not (nomi_offerti & strumenti_che_scrivono)

    # Non ci prova nemmeno: un solo giro, nessun tool_use tentato e fallito.
    assert len(richieste) == 1
    assert runner.last_tool_calls == []
    assert body["debug"]["tools_called"] == []
    assert "non posso" in body["response"].lower()

    archivio_casa.chiudi()
