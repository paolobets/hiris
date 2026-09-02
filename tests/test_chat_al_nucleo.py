"""Task 3 ("il contesto della chat viene dal nucleo"): una fonte sola.

Prima `handle_chat` montava il contesto da quattro fonti indipendenti
(handlers_chat.py:449-461 prima di questa fetta): i fatti dichiarati
(KnowledgeStore.declared()), un blocco RAG (KnowledgeStore.search()), le
sessioni precedenti, e SemanticContextMap.get_context() -- e il ritratto (lo
stato vivo della casa, l'anagrafe) non lo vedeva MAI: e' la sovrapposizione
n.1 della mappa del prodotto, vista da dentro (due intelligenze nella stessa
casa che ne vedono due diverse, vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md, §7).

Dopo: una fonte sola, il nucleo (`hiris.app.casa.nucleo.compose`, condiviso
con GET /api/briefing tramite `handlers_home_space.compose_briefing` -- stessa
composizione per la rotta e per la chat, non due che potrebbero divergere).
Le sessioni precedenti restano A PARTE: sono cronologia di conversazioni
chiuse, non conoscenza sulla casa.

Fetta "esce il documentale": `KnowledgeStore` e' uscito per intero -- non
aveva piu' nessun lettore di produzione, e questo file e' la prova di quando
la chat ha smesso di leggerlo. Le due chiamate citate qui sopra restano
nominate perche' raccontano il PRIMA; non esistono piu' nel codice.

Segue la convenzione REST-vera gia' in tests/test_handlers_casa.py (per
`/api/briefing`) e, prima di questa fetta, in tests/test_declared_block_chat.py
(ora rimosso -- testava esattamente la sovrapposizione che questo task
chiude, vedi il rapporto): un `client` costruito con `create_app()` +
`aiohttp_client`, che legge `context_str`/`strumenti`/`dispatcher` da
`mock_runner.chat.call_args.kwargs` -- esattamente cio' che `handle_chat`
consegna davvero al runner.
"""
import json


def _strumenti_loggati(caplog):
    """I nomi degli strumenti dalla riga di log a livello debug che ha
    sostituito le targhette in chat (`api/handlers_chat.py`).

    Leggere QUI e non dal payload e' deliberato: e' la sola porta rimasta, e un
    test che la usa e' anche la prova che esiste. Se qualcuno rimettesse i nomi
    nella risposta, questi test resterebbero verdi -- ma il test JS
    `chat-page.test.mjs` cadrebbe, ed e' li' che quella regola vive.
    """
    righe = [r.getMessage() for r in caplog.records
             if r.levelname == "DEBUG" and "strumenti del turno" in r.getMessage()]
    return " | ".join(righe)


from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.action.actuator import ActionActuator
from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.casa.strumenti import KNOWLEDGE_TOOLS, ToolDispatcher
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import _TS_FMT, _get_store, close_all_stores
from hiris.app.claude_runner import ClaudeRunner
from hiris.app.memory.store import MemoryStore
from hiris.app.server import create_app
from tests._contratti import assert_stessa_firma
from tests.test_strumenti_conoscenza import _semina_casa as _semina_casa_con_comportamento


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


class _CacheFinta:
    """Sostituto minimo di `EntityCache` -- stessa forma usata da
    tests/test_handlers_casa.py per `handle_get_briefing`: `all_states()`
    restituisce dict con chiave "id" (non "entity_id"), e `loaded` governa
    `inventory_is_readable()`."""

    def __init__(self, stati: list[dict], *, pronta: bool = True) -> None:
        self._stati = stati
        self.loaded = pronta

    def all_states(self) -> list[dict]:
        return self._stati


async def _build_chat_client(aiohttp_client, tmp_path, *, archivio_casa=None,
                             archivio_memoria=None, cache=None):
    """Stessa forma di `_build_chat_client` nei test di chat pre-esistenti
    (tests/test_memoria_ricorda.py e affini, prima che questa fetta la
    ritirasse da li'; quel file e' poi uscito del tutto con la fetta "esce il
    documentale", insieme al `KnowledgeStore` che esercitava), con gli
    archivi del nucleo al posto di `knowledge_store`/`embedding_provider` --
    e' cio' da cui la chat legge adesso."""
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []

    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ChatSettings(system_prompt="base prompt")
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


def _semina_casa(tmp_path) -> HomeSpaceStore:
    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    archivio.replace({
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
    # Le sezioni del nucleo -- lo stesso testo che GET /api/briefing mostra --
    # non le quattro vecchie intestazioni.
    assert "## La casa" in context_str
    assert "## Notevole adesso" in context_str
    assert "## Cio' che la casa fa gia' da sola" in context_str
    assert "Cucina" in context_str
    assert "## Contesto casa" not in context_str
    archivio_casa.close()


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
    archivio_casa.close()


# ---------------------------------------------------------------------------
# Step 1: il runner riceve esattamente cerca/guarda/ricorda/richiama --
# entrambi i punti in cui `handle_chat` puo' chiamare il runner (streaming e
# non), non solo uno.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_la_chat_offre_gli_strumenti_del_catalogo(aiohttp_client, tmp_path):
    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    call_kwargs = mock_runner.chat.call_args.kwargs
    nomi = {t["name"] for t in call_kwargs["tools"]}
    # Derivati, non ricopiati: cio' che questo test prova e' che la rotta
    # passi al runner IL catalogo (`KNOWLEDGE_TOOLS`), non un elenco
    # suo -- e quella proprieta' non dipende da quante voci abbia.
    assert nomi == {d["name"] for d in KNOWLEDGE_TOOLS}
    assert isinstance(call_kwargs["dispatcher"], ToolDispatcher)


@pytest.mark.asyncio
async def test_il_ramo_sincrono_conia_un_turno_non_vuoto_per_l_officina(aiohttp_client, tmp_path):
    """fetta «costruire», review indipendente (I3): il cablaggio della
    guardia non era pinnato da nessun test sul ramo sincrono -- cancellare la
    coniatura in `handle_chat` (`handlers_chat.py`) avrebbe reso ogni
    proposta nata dalla chat sincrona inconfermabile (`self._turno` sarebbe
    tornato al default `None`), e nessun test se ne sarebbe accorto.

    Il dispatcher che arriva al runner e' un `ToolDispatcher` VERO (non
    una finta): si legge `_turno` direttamente, la stessa via che
    `propose`/`confirm` usano per passare l'identita' all'officina."""
    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    dispatcher = mock_runner.chat.call_args.kwargs["dispatcher"]
    assert isinstance(dispatcher._exchange, str) and dispatcher._exchange, (
        "il dispatcher che arriva al runner non porta un'identita' di turno "
        "non vuota: la guardia dell'officina rifiuterebbe QUALUNQUE "
        "`confirm` fatta dalla chat sincrona, anche in un turno successivo "
        "a quello della `propose`")


@pytest.mark.asyncio
async def test_lo_streaming_offre_gli_stessi_strumenti(aiohttp_client, tmp_path):
    """Il buco oltre il brief: quando questo test e' stato scritto, le due
    superfici della chat sceglievano strade diverse -- la card Lovelace
    streammava, la pagina chat no -- e se solo una delle due ricevesse
    `strumenti`/`dispatcher` sarebbero due conversazioni divergenti. La card
    e' uscita col Task 5 della E5 e oggi nessun frontend chiede lo streaming,
    ma il ramo SSE di `handle_chat` e' vivo (lo usano il ponte e questi test):
    resta pinnato qui, cosi' non riparte divergente."""
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    catturati: dict = {}

    async def fake_chat_stream(**kwargs):
        import json
        catturati.update(kwargs)
        yield f'data: {json.dumps({"type": "token", "text": "ok"})}\n\n'
        yield f'data: {json.dumps({"type": "done", "agent_id": None, "tool_calls": []})}\n\n'

    mock_runner = AsyncMock()
    mock_runner.chat_stream = fake_chat_stream
    mock_runner.last_tool_calls = []

    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ChatSettings(system_prompt="base prompt")
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    client = await aiohttp_client(app)

    resp = await client.post("/api/chat", json={"message": "ciao", "stream": True})
    assert resp.status == 200
    await resp.text()

    nomi = {t["name"] for t in catturati["tools"]}
    assert nomi == {d["name"] for d in KNOWLEDGE_TOOLS}
    assert isinstance(catturati["dispatcher"], ToolDispatcher)


# ---------------------------------------------------------------------------
# Step 1: "diciannovesima comparsa evitata" -- senza archivi, la chat non
# deve rispondere come se conoscesse la casa. Deve dirlo, nel contesto che
# il modello legge (non solo in un riepilogo che nessuno passa al modello).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_se_il_nucleo_non_si_compone_la_chat_lo_dice(aiohttp_client, tmp_path):
    """Nessun `archivio_casa` wired nell'app (il caso difensivo di
    `compose_briefing`/`handle_get_briefing` quando `_on_startup` non e'
    ancora girato) -- stessa lacuna che
    tests/test_handlers_casa.py::test_api_nucleo_senza_archivi_non_afferma_di_sapere
    verifica per /api/briefing, qui verificata per il contesto che la chat
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
# Fix E1-①: un archivio GUASTO (non semplicemente assente -- quello e' il
# test sopra) non deve mai far rispondere 500 a `POST /api/chat`. Il vecchio
# dispatcher avvolgeva OGNI fonte in un try/except con questo commento
# esplicito: "un fallimento qui non deve mai impedire alla chat di
# rispondere" (vedi git blame su handlers_chat.py). Diventare una fonte sola
# (Task 3) ha fatto sparire quel commento insieme al codice, e la regola con
# lui -- `compose_briefing()` non era protetta, quindi un `casa.db` in lock
# dopo un riavvio sporco (qui riprodotto chiudendo la connessione sotto
# l'archivio, che e' esattamente lo stesso sqlite3.ProgrammingError di un
# database inutilizzabile) faceva sollevare handle_chat per intero.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_un_archivio_guasto_non_fa_rispondere_500_alla_chat(aiohttp_client, tmp_path):
    archivio_casa = _semina_casa(tmp_path)
    archivio_casa.close()  # la connessione sotto e' chiusa: ogni query solleva
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200  # non 500: la chat risponde comunque

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    # Il modello deve SAPERE che non ha il contesto -- non riceverne uno
    # vuoto che scambierebbe per una casa vuota (diverso dal test sopra:
    # qui l'archivio C'E', solo guasto, quindi non e' lo stesso testo di
    # "nessun archivio wired").
    assert "nucleo non si e' potuto comporre" in context_str
    assert "Non e' una casa vuota" in context_str



# ---------------------------------------------------------------------------
# Step 1: le sessioni precedenti restano -- sono cronologia, non conoscenza,
# quindi vivono A PARTE dal nucleo (non dentro di esso).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_le_sessioni_precedenti_restano(aiohttp_client, tmp_path):
    from datetime import datetime

    archivio_casa = _semina_casa(tmp_path)
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    # Stesso pattern di tests/test_chat_store.py::test_get_past_summaries_returns_closed_sessions:
    # una sessione GIA' chiusa (summary non nullo), inserita direttamente nella
    # stessa ChatStore che `handle_chat` legge per questo `data_dir`. fetta E4
    # Task 5 ("un bot solo"): chat_sessions non ha piu' una colonna chatbot_id
    # -- c'e' UNA cronologia, non serve piu' un id per riga.
    ts = datetime.now(UTC).strftime(_TS_FMT)
    store = _get_store(str(tmp_path))
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, summary) "
        "VALUES(?,?,?,?)",
        ("closed-1", ts, ts, "parlato di irrigazione del giardino"),
    )
    store._conn.commit()

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "## Sessioni precedenti" in context_str
    assert "irrigazione del giardino" in context_str
    # Cronologia, non conoscenza: non e' dentro nessuna sezione del nucleo.
    assert "## La casa" in context_str  # il nucleo c'e' comunque, a fianco
    archivio_casa.close()


@pytest.mark.asyncio
async def test_le_sessioni_precedenti_restano_anche_senza_nucleo(aiohttp_client, tmp_path):
    """Le due fonti sono indipendenti: una chat senza archivi (nucleo
    degradato) deve comunque mostrare la cronologia delle sessioni chiuse --
    non e' il nucleo a deciderne la presenza."""
    from datetime import datetime

    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    ts = datetime.now(UTC).strftime(_TS_FMT)
    store = _get_store(str(tmp_path))
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, summary) "
        "VALUES(?,?,?,?)",
        ("closed-1", ts, ts, "parlato di irrigazione del giardino"),
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
# `ToolDispatcher`, gli archivi (`HomeSpaceStore`, `MemoryStore`) e
# `handle_chat` restano codice di produzione vero, esattamente come nella
# chat reale -- solo la rete verso Anthropic e' finta.
# ---------------------------------------------------------------------------

async def _build_chat_client_runner_reale(aiohttp_client, tmp_path, *, archivio_casa=None,
                                          archivio_memoria=None, cache=None, actuator=None):
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

    # Solo il client HTTP verso Anthropic e' finto (`anthropic.AsyncAnthropic`
    # patchato in costruzione, stessa forma della fixture `claude_runner` di
    # tests/test_runner_catalogo.py) -- il resto del runner (il loop
    # tool_use/tool_result dentro `chat()`) e' vero.
    with patch("anthropic.AsyncAnthropic"):
        runner = ClaudeRunner(api_key="test-key")

    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ChatSettings(system_prompt="base prompt")
    app["claude_runner"] = runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    if archivio_casa is not None:
        app["archivio_casa"] = archivio_casa
    if archivio_memoria is not None:
        app["archivio_memoria"] = archivio_memoria
    if cache is not None:
        app["entity_cache"] = cache
    # La porta dell'azione (`action/actuator.py`). Passarla e' cio' che rende
    # `execute` disponibile al dispatcher: senza, lo strumento c'e' nel
    # catalogo ma dichiara «il collegamento con Home Assistant non e'
    # disponibile» -- il degrado onesto del contratto di `dispatch()`.
    if actuator is not None:
        app["porta_azione"] = actuator

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
# bisogno di chiamare `view`. Se lo chiamasse, sarebbe il nucleo a non
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
    # `runner.last_tool_calls` E' la fonte: il payload non porta piu' i nomi
    # degli strumenti (17/08/2026, vanno nei log a debug), e asserirli due volte
    # era comunque la stessa osservazione fatta da due porte.
    assert runner.last_tool_calls == []
    assert body["response"] == "In cucina hai due luci e un sensore di temperatura."

    archivio_casa.close()


# ---------------------------------------------------------------------------
# Conversazione 2: "cosa fa l'automazione della sveglia?" -- la Legge I che
# smette di essere sulla carta. Il modello chiama `view`, il dispatcher
# VERO legge il corpo VERO dall'archivio, e il SECONDO giro della stessa
# conversazione (la seconda chiamata API vera, non una supposizione del
# test) riceve quel corpo dentro il proprio tool_result.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_2_cosa_fa_la_sveglia_chiama_guarda_e_riporta_il_corpo(
    aiohttp_client, tmp_path, caplog):
    caplog.set_level("DEBUG", logger="hiris.app.api.handlers_chat")
    archivio_casa = _semina_casa_con_comportamento(tmp_path)  # porta automation.sveglia
    # ToolDispatcher._guarda legge SEMPRE anche l'archivio della
    # memoria (per i ricordi ancorati alla cosa guardata): in produzione
    # `_on_startup` (server.py) lo cabla sempre insieme a `archivio_casa`,
    # mai l'uno senza l'altro -- qui si replica lo stesso accoppiamento,
    # non se ne fa a meno.
    archivio_memoria = MemoryStore(str(tmp_path / "memoria_conversazione_2.db"))
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
                "view", {"tipo": "automazione", "riferimento": "automation.sveglia"})
        return _falsa_risposta_testo(
            "La sveglia ha un trigger configurato, l'ho letto dal suo corpo vero.")

    runner._client.messages.create = _api_finta

    resp = await client.post(
        "/api/chat", json={"message": "cosa fa l'automazione della sveglia?"})
    assert resp.status == 200
    body = await resp.json()

    # Il tool chiamato e' esattamente quello giusto. Dal 17/08/2026 NON si
    # legge piu' dal payload -- i nomi degli strumenti non si scrivono in chat --
    # ma dal canale che li ha sostituiti: la riga di log a livello debug. Questa
    # asserzione e' quindi anche la prova che quel canale esiste davvero.
    assert "view" in _strumenti_loggati(caplog)

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

    assert body["response"] == (
        "La sveglia ha un trigger configurato, l'ho letto dal suo corpo vero."
    )

    archivio_casa.close()
    archivio_memoria.close()


# ---------------------------------------------------------------------------
# Conversazione 3: «d'inverno il soggiorno ideale e' 19.5» -- la frase esatta
# da cui e' nato l'intero refactor. HIRIS aveva risposto "preso nota" SENZA
# salvare niente: qui si verifica la scrittura vera, non che il modello
# abbia DETTO di averlo fatto -- una GET /api/memories separata, dopo che la
# risposta della chat e' gia' tornata, sulla STESSA app (stesso archivio).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_3_ricorda_salva_davvero_e_si_ritrova_in_api_memoria(
    aiohttp_client, tmp_path, caplog):
    caplog.set_level("DEBUG", logger="hiris.app.api.handlers_chat")
    archivio_casa = _semina_casa_con_comportamento(tmp_path)
    archivio_memoria = MemoryStore(str(tmp_path / "memoria_reale.db"))
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa, archivio_memoria=archivio_memoria,
    )

    frase = "d'inverno il soggiorno ideale e' 19.5"
    giro = {"n": 0}

    async def _api_finta(**kwargs):
        giro["n"] += 1
        if giro["n"] == 1:
            return _falsa_risposta_tool_use("remember", {"testo": frase, "forza": "preferenza"})
        return _falsa_risposta_testo("Preso nota -- e stavolta l'ho anche salvato.")

    runner._client.messages.create = _api_finta

    resp = await client.post("/api/chat", json={"message": frase})
    assert resp.status == 200
    await resp.json()
    assert "remember" in _strumenti_loggati(caplog)

    # La prova vera: NON il testo della risposta (che qui il modello finto
    # controlla), ma una richiesta HTTP separata sull'archivio vero.
    resp_memoria = await client.get("/api/memories")
    assert resp_memoria.status == 200
    corpo_memoria = await resp_memoria.json()
    assert corpo_memoria["available"] is True
    testi_salvati = [r["testo"] for r in corpo_memoria["memories"]]
    assert frase in testi_salvati, (
        "il difetto originale -- 'preso nota' senza salvare niente -- tornerebbe "
        "esattamente qui: la frase deve trovarsi DAVVERO nell'archivio della memoria"
    )

    archivio_casa.close()
    archivio_memoria.close()


# ---------------------------------------------------------------------------
# Conversazione 4: "spegni la luce della cucina" -- e la spegne.
#
# fetta «comandare» (Task 7). Fino a `33da82b` questa conversazione si
# chiamava `..._accendi_la_luce_non_puo_e_lo_dice` e provava che HIRIS NON
# poteva agire. Passava ancora dopo il Task 5, ma **solo perche' l'API finta
# era scritturata a rispondere «non posso»**: era il test a scrivere la
# risposta che poi verificava. Lo scenario non descriveva piu' il prodotto.
#
# Adesso descrive quello che succede davvero, e la prova NON e' piu' il testo
# della risposta -- che il finto controlla ancora -- ma la CATENA, in tre
# punti che nessun altro test copre insieme:
#
#   1. il modello riceve `execute` fra gli strumenti della chat vera;
#   2. quando lo chiama, la richiesta arriva alla PORTA (l'unico punto che
#      esegue), con l'origine dichiarata;
#   3. cio' che la porta restituisce torna al modello COME TOOL_RESULT, non
#      riassunto ne' riscritto da noi.
#
# Il punto 3 e' quello che vale: e' la stessa catena che si era gia' spezzata
# in silenzio una volta su questo prodotto -- «preso nota» senza aver salvato
# -- e qui il danno sarebbe peggiore, perche' l'azione e' successa per davvero
# e il modello racconterebbe qualcos'altro.
#
# Resta il vecchio guardiano: nessuno dei nomi del catalogo VECCHIO
# (`claude_runner.ALL_TOOL_DEFS`, i trentaquattro) deve poter rientrare da una
# porta di servizio. Quelli attuavano ciascuno per conto proprio; `execute`
# passa da una porta sola.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversazione_4_spegni_la_luce_arriva_alla_porta_e_torna_al_modello(
        aiohttp_client, tmp_path, caplog):
    caplog.set_level("DEBUG", logger="hiris.app.api.handlers_chat")
    archivio_casa = _semina_casa_con_comportamento(tmp_path)

    class _PortaFinta:
        """Sta al posto di `action/actuator.py` -- che ha i suoi test, con la
        verifica e la rilettura vere (`tests/test_azione_porta.py`). Qui
        interessa solo che la chat ci ARRIVI, e con cosa."""
        def __init__(self):
            self.chiamate = []

        async def execute(self, chiamata, *, actor):
            self.chiamate.append((chiamata, actor))
            return {"eseguito": True, "servizio": "light.turn_off",
                    "entita": ["light.cucina_1"],
                    "prima": {"light.cucina_1": "on"},
                    "dopo": {"light.cucina_1": "off"},
                    "cambiato": ["light.cucina_1"]}

    # Se `ActionActuator.execute` cambia firma, questa riga cade invece di
    # lasciare che il finto imiti un contratto che non esiste piu'.
    assert_stessa_firma(ActionActuator.execute, _PortaFinta.execute, nome="execute")

    actuator = _PortaFinta()
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa, actuator=actuator,
    )

    richieste: list[dict] = []
    giro = {"n": 0}

    async def _api_finta(**kwargs):
        richieste.append(kwargs)
        giro["n"] += 1
        if giro["n"] == 1:
            return _falsa_risposta_tool_use(
                "execute", {"servizio": "light.turn_off",
                           "bersaglio": {"entita": ["light.cucina_1"]}})
        return _falsa_risposta_testo("L'ho spenta.")

    runner._client.messages.create = _api_finta

    resp = await client.post("/api/chat", json={"message": "spegni la luce della cucina"})
    assert resp.status == 200
    await resp.json()

    # (1) il catalogo offerto e' quello unico, `execute` compreso -- e nessuno
    # dei trentaquattro e' rientrato.
    nomi_offerti = {t["name"] for t in richieste[0]["tools"]}
    assert nomi_offerti == {d["name"] for d in KNOWLEDGE_TOOLS}
    assert "execute" in nomi_offerti
    strumenti_che_scrivono = {
        "call_ha_service", "trigger_automation", "toggle_automation",
        "set_input_helper", "create_ha_config",
    }
    assert not (nomi_offerti & strumenti_che_scrivono)

    # (2) la chiamata e' arrivata ALLA PORTA, una volta sola, con l'origine.
    assert len(actuator.chiamate) == 1, (
        "la chat non ha raggiunto la porta: `execute` e' stato offerto al "
        "modello ma la sua chiamata non e' arrivata all'unico punto che esegue")
    chiamata, actor = actuator.chiamate[0]
    assert chiamata["servizio"] == "light.turn_off"
    assert chiamata["bersaglio"]["entita"] == ["light.cucina_1"]
    assert actor == "chat"

    # (3) l'esito della porta e' tornato al modello COME TOOL_RESULT, non
    # riscritto da noi. Si guarda il secondo giro: il contenuto del blocco
    # deve portare `cambiato`, che e' la chiave con cui la porta dice cosa e'
    # successo per davvero -- ed e' cio' che il prompt promette al modello.
    assert len(richieste) == 2
    blocchi = [b for m in richieste[1]["messages"]
               for b in (m["content"] if isinstance(m["content"], list) else [])
               if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert blocchi, "nessun tool_result e' tornato al modello dopo l'azione"
    assert "cambiato" in str(blocchi[0]["content"]), (
        "il modello non ha ricevuto cosa e' CAMBIATO: racconterebbe cio' che "
        "e' stato chiesto invece di cio' che e' successo")
    assert "light.cucina_1" in str(blocchi[0]["content"])

    # e l'azione resta TRACCIABILE: non piu' con una targhetta all'interfaccia
    # (uscita il 17/08/2026) ma nella riga di log a livello debug che l'ha
    # sostituita. Per un'AZIONE questa e' la tracciabilita' che conta.
    assert "execute" in _strumenti_loggati(caplog)

    archivio_casa.close()


# ---------------------------------------------------------------------------
# Il gemello: senza porta cablata `execute` non sparisce dal catalogo -- dice
# perche' non puo'. E' il contratto di `dispatch()` (non solleva mai, degrada
# in un `errore` leggibile) applicato al quinto strumento, e la ragione per
# cui il dispatcher resta SEMPRE costruibile.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_senza_porta_esegui_resta_offerto_ma_dichiara_il_motivo(
        aiohttp_client, tmp_path):
    archivio_casa = _semina_casa_con_comportamento(tmp_path)
    client, runner = await _build_chat_client_runner_reale(
        aiohttp_client, tmp_path, archivio_casa=archivio_casa,
    )

    richieste: list[dict] = []
    giro = {"n": 0}

    async def _api_finta(**kwargs):
        richieste.append(kwargs)
        giro["n"] += 1
        if giro["n"] == 1:
            return _falsa_risposta_tool_use(
                "execute", {"servizio": "light.turn_off",
                           "bersaglio": {"entita": ["light.cucina_1"]}})
        return _falsa_risposta_testo("Non riesco a raggiungere Home Assistant.")

    runner._client.messages.create = _api_finta

    resp = await client.post("/api/chat", json={"message": "spegni la luce della cucina"})
    assert resp.status == 200

    # `execute` e' offerto lo stesso: toglierlo dal catalogo quando manca la
    # porta darebbe al modello un prodotto diverso a ogni turno.
    assert "execute" in {t["name"] for t in richieste[0]["tools"]}
    blocchi = [b for m in richieste[1]["messages"]
               for b in (m["content"] if isinstance(m["content"], list) else [])
               if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert blocchi
    testo = str(blocchi[0]["content"])
    assert "errore" in testo, "un guasto deve tornare come errore leggibile, non come eccezione"
    assert "Home Assistant" in testo, (
        "il rifiuto deve portare il MOTIVO: «non posso» senza motivo e' "
        "esattamente cio' che i vincoli della fetta vietano")

    archivio_casa.close()
