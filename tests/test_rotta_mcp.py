"""La rotta `POST /api/mcp`: un adattatore, non un secondo prodotto.

Questi test tengono ferme le due cose che rendono la rotta cio' che dice di
essere:

1. **un catalogo solo e un dispatcher solo.** `tools/list` ri-forma
   `STRUMENTI_CONOSCENZA` (nessun nome scritto a mano qui dentro: una lista
   scritta a mano sarebbe il secondo catalogo che nasce) e `tools/call` passa
   dal `DispatcherStrumenti` vero -- provato dal fatto che un `ricorda` fatto
   attraverso la rotta si ritrova in `memoria.db`;
2. **l'autenticazione, con le valvole della suite RIMOSSE.** `conftest.py`
   imposta `HIRIS_ALLOW_NO_TOKEN=1` e `HIRIS_ALLOW_NO_CSRF=1` per tutta la
   suite: senza toglierle, questi test passerebbero anche col guasto in piedi.
   Il modello e' `tests/test_token_interno.py::ponte_con_configurazione_
   predefinita`. Qui si esercitano **entrambi** i rami che tengono viva la
   rotta: quello del CSRF con `X-Requested-With` e quello dell'esenzione da
   token interno (che e' cio' che manda la CLI `claude`, e che vive solo perche'
   l'add-on un token lo genera davvero -- `token_interno.py`).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.api import handlers_mcp
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA
from hiris.app.impostazioni_chat import ImpostazioniChat
from hiris.app.memoria.archivio import MemoryStore
from tests.test_strumenti_conoscenza import _semina_casa

# Il token dell'add-on per questi test: un valore qualunque, purche' quello che
# il client manda e quello che l'app conosce siano lo stesso -- e' esattamente
# la coppia che in produzione `token_interno.prepara_token_interno` allinea fra
# `app["internal_token"]` e `os.environ["INTERNAL_TOKEN"]`.
TOKEN = "token-di-prova-della-rotta-mcp"

# Cio' che manda davvero il sottoprocesso `claude` del ponte: il token interno e
# NIENTE `X-Requested-With`. E' il caso che deve passare.
INTESTAZIONI_CLI = {"X-HIRIS-Internal-Token": TOKEN}


@pytest_asyncio.fixture
async def rotta(aiohttp_client, tmp_path, monkeypatch):
    """L'app vera (`create_app()`), con gli archivi seminati e le due valvole
    della suite rimosse: qui il rifiuto-per-default e il CSRF sono ATTIVI."""
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)

    app = server.create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ImpostazioniChat()
    app["claude_runner"] = None
    app["theme"] = "auto"
    # La sorgente del client di test e' un loopback, che NON e' nella CIDR del
    # Supervisor: nessun bypass ingress, si passa per forza dal token -- e' il
    # caso del sottoprocesso `claude`, che gira dentro il container.
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app["internal_token"] = TOKEN

    casa = _semina_casa(tmp_path)
    memoria_db = str(tmp_path / "memoria.db")
    memoria = MemoryStore(memoria_db)
    app["archivio_casa"] = casa
    app["archivio_memoria"] = memoria
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    try:
        yield client, memoria_db
    finally:
        memoria.close()
        casa.close()


@pytest_asyncio.fixture
async def rotta_senza_archivi(aiohttp_client, monkeypatch):
    """La stessa rotta prima che l'anagrafe sia stata letta: `archivio_casa` e
    `archivio_memoria` semplicemente non ci sono in `app`."""
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    app = server.create_app()
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app["internal_token"] = TOKEN
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


async def _jsonrpc(client, corpo, intestazioni=None):
    return await client.post("/api/mcp", json=corpo,
                             headers=INTESTAZIONI_CLI if intestazioni is None else intestazioni)


# ---------------------------------------------------------------------------
# ① e ② -- il catalogo e' UNO, e viene ri-formato, non ri-dichiarato
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_list_espone_esattamente_il_catalogo_della_costante(rotta):
    """L'insieme dei nomi si deriva dalla costante, non si scrive a mano: un
    elenco scritto qui sarebbe il SECONDO catalogo della stessa cosa -- il
    difetto da cui e' nata l'intera fetta E2 (tre cataloghi divergenti)."""
    client, _ = rotta
    risposta = await _jsonrpc(client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert risposta.status == 200
    corpo = await risposta.json()

    nomi = {voce["name"] for voce in corpo["result"]["tools"]}
    assert nomi == {definizione["name"] for definizione in STRUMENTI_CONOSCENZA}


@pytest.mark.asyncio
async def test_tools_list_rinomina_solo_la_chiave_dello_schema(rotta):
    """La sola differenza ammessa fra la costante e cio' che esce di qui e' la
    grafia della chiave: `input_schema` -> `inputSchema`. Descrizioni e schemi
    restano IDENTICI -- una descrizione riscritta qui sarebbe un catalogo
    proprio travestito da adattatore."""
    client, _ = rotta
    corpo = await (await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})).json()
    per_nome = {voce["name"]: voce for voce in corpo["result"]["tools"]}

    for definizione in STRUMENTI_CONOSCENZA:
        voce = per_nome[definizione["name"]]
        assert "inputSchema" in voce
        assert "input_schema" not in voce
        assert voce["inputSchema"] == definizione["input_schema"]
        assert voce["description"] == definizione["description"]


# ---------------------------------------------------------------------------
# ③ -- initialize
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initialize_rimanda_la_versione_di_protocollo_ricevuta(rotta):
    """E' il client a sapere quale versione sa parlare: si rimanda indietro la
    sua, non una nostra scelta al ribasso."""
    client, _ = rotta
    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    assert risposta.status == 200
    corpo = await risposta.json()

    assert corpo["result"]["protocolVersion"] == "2024-11-05"
    assert corpo["result"]["serverInfo"]["name"] == "hiris"
    assert corpo["result"]["capabilities"]["tools"] == {}


@pytest.mark.asyncio
async def test_initialize_dichiara_la_versione_dell_addon_da_read_version(rotta):
    """`serverInfo.version` viene da `version.read_version()`, gia' l'unica
    fonte della versione del prodotto: nessun numero scritto a mano."""
    from hiris.app.version import read_version
    client, _ = rotta
    corpo = await (await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})).json()
    assert corpo["result"]["serverInfo"]["version"] == read_version()
    # Senza `protocolVersion` nella richiesta si dichiara il predefinito, non
    # `None`: un campo nullo qui sarebbe un modo in piu' di non partire.
    assert corpo["result"]["protocolVersion"] == handlers_mcp.PROTOCOLLO_PREDEFINITO


# ---------------------------------------------------------------------------
# ④ e ⑤ -- tools/call passa dal dispatcher VERO
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_call_ricorda_scrive_davvero_in_memoria_db(rotta):
    """La prova che questa rotta non ha una logica di strumento propria: la
    frase entra da HTTP e si ritrova nel FILE `memoria.db`, letto da una
    connessione a parte. E' anche il guasto storico da cui `ricorda` e' nato --
    «preso nota» senza salvare niente."""
    client, memoria_db = rotta
    frase = "d'inverno il soggiorno ideale e' 19.5"

    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "ricorda", "arguments": {"testo": frase}},
    })
    assert risposta.status == 200
    corpo = await risposta.json()
    assert corpo["id"] == 7
    esito = json.loads(corpo["result"]["content"][0]["text"])
    assert esito["salvato"] is True
    assert "isError" not in corpo["result"]

    conn = sqlite3.connect(memoria_db)
    try:
        righe = conn.execute("SELECT testo FROM ricordi").fetchall()
    finally:
        conn.close()
    assert [r[0] for r in righe] == [frase]


@pytest.mark.asyncio
async def test_tools_call_cerca_risponde_dagli_archivi_dell_app(rotta):
    """`cerca` legge lo stesso `archivio_casa` che alimenta il turno sincrono:
    il dispatcher e' costruito dagli oggetti dell'app, non da archivi propri."""
    client, _ = rotta
    corpo = await (await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "cerca", "arguments": {"testo": "cucina"}},
    })).json()
    esito = json.loads(corpo["result"]["content"][0]["text"])
    assert esito["trovati"]


@pytest.mark.asyncio
async def test_tools_call_di_uno_strumento_inesistente_restituisce_l_errore_del_dispatcher(rotta):
    """Non un 500: il messaggio e' quello del dispatcher (che elenca cio' che
    esiste invece di accusare il modello di essersi inventato un nome), e la
    chiamata e' marcata `isError` -- altrimenti un fallimento arriverebbe
    travestito da successo."""
    client, _ = rotta
    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "accendi", "arguments": {}},
    })
    assert risposta.status == 200
    corpo = await risposta.json()
    assert "error" not in corpo
    assert corpo["result"]["isError"] is True
    esito = json.loads(corpo["result"]["content"][0]["text"])
    assert "accendi" in esito["errore"]
    assert "cerca" in esito["errore"], "il messaggio deve dire cosa esiste"


@pytest.mark.asyncio
async def test_tools_call_senza_archivi_dichiara_cosa_manca(rotta_senza_archivi):
    """Gli archivi possono non esserci ancora (anagrafe mai letta). La rotta non
    esplode e non tace: rimanda l'errore leggibile del dispatcher, marcato."""
    risposta = await _jsonrpc(rotta_senza_archivi, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "cerca", "arguments": {"testo": "cucina"}},
    })
    assert risposta.status == 200
    corpo = await risposta.json()
    assert corpo["result"]["isError"] is True
    esito = json.loads(corpo["result"]["content"][0]["text"])
    assert "non e' disponibile" in esito["errore"]
    assert "casa" in esito["errore"]


@pytest.mark.asyncio
async def test_tools_call_senza_nome_dice_quale_campo_manca(rotta):
    """Un errore generico su una chiamata malformata e' un silenzio travestito:
    il messaggio deve nominare il campo mancante e cio' che era ammesso."""
    client, _ = rotta
    corpo = await (await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"arguments": {}},
    })).json()
    assert corpo["error"]["code"] == -32602
    assert "params.name" in corpo["error"]["message"]
    assert "ricorda" in corpo["error"]["message"]


# ---------------------------------------------------------------------------
# Task 6 -- il tetto ai giri di strumento per turno, l'unico freno che
# l'abbonamento abbia: `claude` non ha un `--max-turns` (verificato su
# `claude --help`), quindi il tetto sta QUI, l'unico punto che vede passare
# OGNI `tools/call`.
# ---------------------------------------------------------------------------

async def _chiama_cerca(client, id_richiesta, intestazioni):
    return await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": id_richiesta, "method": "tools/call",
        "params": {"name": "cerca", "arguments": {"testo": "cucina"}},
    }, intestazioni=intestazioni)


@pytest.mark.asyncio
async def test_tetto_raggiunto_rifiuta_e_il_dispatcher_non_viene_invocato(rotta, caplog):
    """Step 5 ① del brief. Le prime `MAX_GIRI_STRUMENTI` chiamate del turno
    passano regolarmente; la successiva riceve il testo del tetto -- e la
    prova che il dispatcher non e' stato invocato non e' un'asserzione sulla
    forma della risposta, ma sull'EFFETTO: nessuna scrittura in `memoria.db`
    per un `ricorda` tentato oltre il tetto."""
    client, memoria_db = rotta
    intestazioni = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-al-tetto"}

    for i in range(handlers_mcp.MAX_GIRI_STRUMENTI):
        risposta = await _chiama_cerca(client, i, intestazioni)
        corpo = await risposta.json()
        assert "isError" not in corpo["result"], (
            f"la chiamata numero {i + 1} (dentro il tetto di "
            f"{handlers_mcp.MAX_GIRI_STRUMENTI}) e' stata rifiutata")

    with caplog.at_level(logging.WARNING):
        risposta = await _jsonrpc(client, {
            "jsonrpc": "2.0", "id": 999, "method": "tools/call",
            "params": {"name": "ricorda", "arguments": {"testo": "scritto oltre il tetto"}},
        }, intestazioni=intestazioni)

    assert risposta.status == 200
    corpo = await risposta.json()
    assert "error" not in corpo  # risposta JSON-RPC NORMALE, non un errore di protocollo
    assert corpo["result"]["isError"] is True
    esito = json.loads(corpo["result"]["content"][0]["text"])
    # Il testo dichiara COSA e' successo (il tetto, il numero) e COSA fare
    # (rispondere con cio' che gia' si ha): mai un errore generico.
    assert str(handlers_mcp.MAX_GIRI_STRUMENTI) in esito["errore"]
    assert "tetto" in esito["errore"]
    assert "rispond" in esito["errore"]

    conn = sqlite3.connect(memoria_db)
    try:
        righe = conn.execute("SELECT testo FROM ricordi").fetchall()
    finally:
        conn.close()
    assert righe == [], (
        "il dispatcher e' stato invocato oltre il tetto: 'ricorda' ha scritto "
        "in memoria.db un ricordo che il tetto doveva impedire")

    # Un log.warning al primo superamento, che nomina il turno.
    messaggi = [r.getMessage() for r in caplog.records]
    assert any("tetto" in m and "turno-al-tetto" in m for m in messaggi)


@pytest.mark.asyncio
async def test_tetto_raggiunto_non_ripete_il_log_a_ogni_tentativo_successivo(rotta, caplog):
    """Solo il PRIMO superamento logga: i tentativi successivi nello stesso
    turno, gia' oltre il tetto, non devono produrre rumore a ogni chiamata."""
    client, _ = rotta
    intestazioni = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-rumoroso"}
    for i in range(handlers_mcp.MAX_GIRI_STRUMENTI):
        await _chiama_cerca(client, i, intestazioni)

    with caplog.at_level(logging.WARNING):
        for i in range(3):
            risposta = await _chiama_cerca(client, 100 + i, intestazioni)
            corpo = await risposta.json()
            assert corpo["result"]["isError"] is True

    righe_tetto = [r for r in caplog.records if "tetto" in r.getMessage()
                   and "turno-rumoroso" in r.getMessage()]
    assert len(righe_tetto) == 1


@pytest.mark.asyncio
async def test_due_turni_diversi_hanno_contatori_indipendenti(rotta):
    """Step 5 ②. Esaurire (e superare) il tetto del turno A non deve toccare
    il turno B: due identita' diverse sono due contatori diversi."""
    client, _ = rotta
    turno_a = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-A"}
    turno_b = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-B"}

    for i in range(handlers_mcp.MAX_GIRI_STRUMENTI + 1):
        await _chiama_cerca(client, i, turno_a)

    risposta = await _chiama_cerca(client, 1, turno_b)
    corpo = await risposta.json()
    assert "isError" not in corpo["result"], (
        "il turno B e' stato rifiutato per un tetto raggiunto dal turno A: i "
        "due contatori non sono indipendenti")


@pytest.mark.asyncio
async def test_senza_intestazione_di_turno_lo_strumento_si_esegue_e_il_log_lo_dichiara(
    rotta, caplog,
):
    """Step 5 ③ (silenzio dichiarato ⑤ della fetta). Un chiamante che non
    manda `X-HIRIS-Turno` -- oggi, ogni test di questo file che non la
    imposta -- non viene rifiutato: rifiutare romperebbe il prodotto per un
    contatore. Lo strumento si esegue davvero, e il log dichiara che questa
    chiamata resta fuori dal tetto."""
    client, _ = rotta
    with caplog.at_level(logging.WARNING):
        risposta = await _chiama_cerca(client, 1, INTESTAZIONI_CLI)  # niente X-HIRIS-Turno
    corpo = await risposta.json()
    assert "isError" not in corpo["result"]
    esito = json.loads(corpo["result"]["content"][0]["text"])
    assert esito["trovati"]  # lo strumento e' stato ESEGUITO davvero

    messaggi = [r.getMessage() for r in caplog.records]
    assert any("X-HIRIS-Turno" in m and "cerca" in m for m in messaggi)


@pytest.mark.asyncio
async def test_il_dizionario_dei_contatori_non_cresce_oltre_il_limite(rotta):
    """Step 5 ④. Molte identita' di turno diverse, una sola chiamata ciascuna:
    il dizionario tenuto in `app` resta limitato a `_MAX_TURNI_TRACCIATI`, non
    cresce per ogni identita' mai vista."""
    client, _ = rotta
    quante = handlers_mcp._MAX_TURNI_TRACCIATI * 3

    for i in range(quante):
        await _chiama_cerca(
            client, i, {**INTESTAZIONI_CLI, "X-HIRIS-Turno": f"turno-usa-getta-{i}"}
        )

    contatori = client.app["mcp_giri_per_turno"]
    assert len(contatori) <= handlers_mcp._MAX_TURNI_TRACCIATI


@pytest.mark.asyncio
async def test_un_turno_attivo_non_viene_mai_espulso(rotta):
    """Review totale della fetta (M-1): la proprieta' che rende SANO il tetto,
    e che fino a qui non aveva un test.

    Il test qui sopra pinna solo che il dizionario sia LIMITATO -- e resterebbe
    verde anche con un'espulsione FIFO, cioe' con la piu' VECCHIA per data di
    nascita. Con una FIFO un turno lungo verrebbe espulso dopo
    `_MAX_TURNI_TRACCIATI` turni altrui, il suo contatore ripartirebbe da zero
    e **il tetto si aggirerebbe semplicemente durando**: chiamare 10 volte,
    lasciar passare 64 turni, chiamare altre 10.

    Cio' che il codice fa davvero e' LRU (`move_to_end` a ogni giro): il turno
    che continua a chiamare si rimette in coda e non e' mai il candidato
    all'espulsione. Qui lo si prova sull'EFFETTO, non sulla struttura -- un
    turno «caldo» che chiama fino al tetto mentre `_MAX_TURNI_TRACCIATI` turni
    usa-e-getta gli passano accanto, e la sua chiamata successiva che viene
    **rifiutata**: se il contatore fosse ripartito, quella passerebbe."""
    client, _ = rotta
    caldo = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-caldo"}

    # Il turno caldo consuma il suo tetto, ma **intervallato** da altrettanti
    # turni nuovi: alla fine gliene sono passati accanto piu' di
    # `_MAX_TURNI_TRACCIATI`, cioe' abbastanza da espellerlo per intero se
    # l'espulsione guardasse la data di nascita.
    per_giro = (handlers_mcp._MAX_TURNI_TRACCIATI
                // handlers_mcp.MAX_GIRI_STRUMENTI) + 1
    usa_e_getta = 0
    for giro in range(handlers_mcp.MAX_GIRI_STRUMENTI):
        risposta = await _chiama_cerca(client, giro, caldo)
        corpo = await risposta.json()
        assert "isError" not in corpo["result"], (
            f"la chiamata {giro + 1} del turno caldo, DENTRO il tetto di "
            f"{handlers_mcp.MAX_GIRI_STRUMENTI}, e' stata rifiutata")
        for _ in range(per_giro):
            usa_e_getta += 1
            await _chiama_cerca(
                client, 1000 + usa_e_getta,
                {**INTESTAZIONI_CLI, "X-HIRIS-Turno": f"altro-{usa_e_getta}"})

    assert usa_e_getta > handlers_mcp._MAX_TURNI_TRACCIATI, (
        "il test non prova niente se i turni passati accanto sono meno della "
        "capienza del dizionario: alzare `per_giro`")

    risposta = await _chiama_cerca(client, 9999, caldo)
    corpo = await risposta.json()
    assert corpo["result"].get("isError") is True, (
        "il turno caldo e' stato ESPULSO e il suo contatore e' ripartito da "
        "zero: l'espulsione ha guardato la data di nascita (FIFO) invece "
        "dell'ultimo uso (LRU), e il tetto per-turno si aggira semplicemente "
        "durando -- 10 chiamate, 64 turni altrui, altre 10 chiamate")
    testo = json.loads(corpo["result"]["content"][0]["text"])["errore"]
    assert str(handlers_mcp.MAX_GIRI_STRUMENTI) in testo

    # e la controprova che il dizionario e' rimasto limitato lo stesso: la
    # proprieta' nuova non e' stata comprata rinunciando al tetto di memoria.
    assert len(client.app["mcp_giri_per_turno"]) <= handlers_mcp._MAX_TURNI_TRACCIATI


# ---------------------------------------------------------------------------
# ⑥ -- le notifiche, e gli altri errori di protocollo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_una_notifica_senza_id_riceve_202_e_corpo_vuoto(rotta):
    """`notifications/initialized` e compagne: si accettano e basta. Rispondere
    a una notifica sarebbe una violazione del protocollo."""
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert risposta.status == 202
    assert (await risposta.read()) == b""


@pytest.mark.asyncio
async def test_un_id_nullo_esplicito_resta_una_richiesta_e_riceve_risposta(rotta):
    """La notifica e' l'ASSENZA del membro `id`, non un `id` nullo: confonderli
    lascerebbe senza risposta una richiesta legittima."""
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": None, "method": "tools/list"})
    assert risposta.status == 200
    corpo = await risposta.json()
    assert corpo["id"] is None
    assert corpo["result"]["tools"]


@pytest.mark.asyncio
async def test_metodo_sconosciuto_e_32601_e_dice_quali_esistono(rotta):
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 9, "method": "resources/list"})
    assert risposta.status == 200
    corpo = await risposta.json()
    assert corpo["id"] == 9
    assert corpo["error"]["code"] == -32601
    assert "resources/list" in corpo["error"]["message"]
    for metodo in handlers_mcp.METODI:
        assert metodo in corpo["error"]["message"]


@pytest.mark.asyncio
async def test_json_non_valido_e_32700_e_non_un_500(rotta):
    """Mai un 500 nudo, e mai un'eccezione che risalga: e' la stessa proprieta'
    che `DispatcherStrumenti.dispatch` promette per contratto."""
    client, _ = rotta
    risposta = await client.post(
        "/api/mcp", data="{non e' json", headers=INTESTAZIONI_CLI)
    assert risposta.status == 400
    corpo = await risposta.json()
    assert corpo["error"]["code"] == -32700
    assert "JSON" in corpo["error"]["message"]


@pytest.mark.asyncio
async def test_un_batch_json_rpc_viene_rifiutato_dicendolo(rotta):
    """I batch non sono supportati -- e lo si dice, invece di rispondere un
    errore generico che il chiamante non puo' interpretare."""
    client, _ = rotta
    risposta = await _jsonrpc(client, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert risposta.status == 400
    corpo = await risposta.json()
    assert corpo["error"]["code"] == -32600
    assert "batch" in corpo["error"]["message"]


# ---------------------------------------------------------------------------
# ⑦ -- l'autenticazione E il CSRF, con le valvole della suite rimosse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_senza_intestazioni_la_rotta_nega(rotta):
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, intestazioni={})
    assert risposta.status == 401


@pytest.mark.asyncio
async def test_con_un_token_sbagliato_la_rotta_nega(rotta):
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        intestazioni={"X-HIRIS-Internal-Token": TOKEN + "-sbagliato"})
    assert risposta.status == 401


@pytest.mark.asyncio
async def test_il_token_valido_senza_x_requested_with_passa(rotta):
    """**E' esattamente cio' che manda la CLI `claude`**: il token e nessun
    `X-Requested-With`. Passa grazie all'esenzione di `middleware_csrf.py`, che
    a sua volta e' viva solo perche' l'add-on genera un token interno quando
    l'opzione e' vuota (`token_interno.py`). Se un giorno quell'esenzione
    cadesse, questo test diventa rosso: il ramo non muore in silenzio."""
    client, _ = rotta
    risposta = await _jsonrpc(client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert "X-Requested-With" not in INTESTAZIONI_CLI
    assert risposta.status == 200


@pytest.mark.asyncio
async def test_anche_col_x_requested_with_passa(rotta):
    """L'altro ramo del CSRF, pinnato perche' la rotta non dipenda da uno solo:
    il Task 3 puo' mandare `X-Requested-With` insieme al token nella voce
    `--mcp-config`, e la rotta continua a rispondere."""
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        intestazioni={**INTESTAZIONI_CLI, "X-Requested-With": "fetch"})
    assert risposta.status == 200


@pytest.mark.asyncio
async def test_il_solo_x_requested_with_non_basta_a_entrare(rotta):
    """Il CSRF non e' l'autenticazione: superarlo non apre la rotta. Un
    chiamante che sa mandare l'header ma non ha il token resta fuori."""
    client, _ = rotta
    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        intestazioni={"X-Requested-With": "fetch"})
    assert risposta.status == 401


@pytest.mark.asyncio
async def test_la_valvola_di_sviluppo_non_apre_questa_rotta(aiohttp_client, monkeypatch):
    """`HIRIS_ALLOW_NO_TOKEN=1` -- che `conftest.py` accende per TUTTA la suite,
    e che in sviluppo qualcuno potrebbe accendere sul serio -- disattiva
    l'autenticazione su tutta la API. Su questa rotta NO: l'handler accetta la
    sola `auth_via == "token"`, quindi il ramo aperto del middleware non basta.
    E' cio' che impedisce alla rotta di dipendere da un ramo solo."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")
    monkeypatch.setenv("HIRIS_ALLOW_NO_CSRF", "1")
    app = server.create_app()
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app["internal_token"] = ""
    app.on_startup.clear()
    app.on_cleanup.clear()
    client = await aiohttp_client(app)

    risposta = await client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1,
                                                  "method": "tools/list"})
    assert risposta.status == 401
    # Controprova: con la valvola accesa il resto della API risponde davvero --
    # il 401 qui sopra viene dalla rotta, non da un'app che nega tutto.
    assert (await client.get("/api/health")).status == 200


# ---------------------------------------------------------------------------
# La rotta e' registrata, e il dispatcher si costruisce in UN SOLO posto
# ---------------------------------------------------------------------------

def test_la_rotta_e_registrata_in_create_app():
    app = server.create_app()
    percorsi = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/mcp" in percorsi


def test_il_dispatcher_si_costruisce_in_un_solo_punto_del_prodotto():
    """Due costruzioni che possono divergere sono il difetto da cui e' nata la
    fetta E2. `handlers_mcp` non costruisce un `DispatcherStrumenti` proprio:
    chiama la stessa funzione del turno sincrono. Il test guarda il sorgente di
    `hiris/app/` perche' e' l'unico modo di pinnare un'ASSENZA."""
    import pathlib
    radice = pathlib.Path(server.__file__).parent
    costruttori = []
    for percorso in radice.rglob("*.py"):
        for numero, riga in enumerate(percorso.read_text(encoding="utf-8").splitlines(), 1):
            if "DispatcherStrumenti(" in riga and not riga.strip().startswith("#"):
                costruttori.append(f"{percorso.relative_to(radice)}:{numero}")
    assert len(costruttori) == 1, (
        "il dispatcher va costruito in UN SOLO punto "
        f"(costruisci_dispatcher_strumenti); trovati invece: {costruttori}"
    )
    assert costruttori[0].replace("\\", "/").startswith("api/handlers_chat.py:"), costruttori


@pytest.mark.asyncio
async def test_la_rotta_usa_la_stessa_costruzione_del_turno_sincrono(rotta, monkeypatch):
    """La controprova dinamica del test qui sopra: se `handle_mcp` smettesse di
    passare da `costruisci_dispatcher_strumenti`, questo test cadrebbe.

    fetta «costruire», review indipendente (I3): il cablaggio della guardia
    non era pinnato da nessun test -- cancellare `turno=id_turno` dalla
    chiamata in `handlers_mcp.py` avrebbe reso ogni proposta nata dal ponte
    inconfermabile, e nessun test se ne sarebbe accorto. Qui si verifica che
    il `turno` ricevuto dal costruttore sia DAVVERO il valore
    dell'intestazione `X-HIRIS-Turno`, non un `None` o un valore inventato."""
    chiamate = []
    vero = handlers_mcp.costruisci_dispatcher_strumenti

    def _spia(app, turno=None):
        chiamate.append((app, turno))
        return vero(app, turno=turno)

    monkeypatch.setattr(handlers_mcp, "costruisci_dispatcher_strumenti", _spia)
    client, _ = rotta
    intestazioni = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-guardia-mcp"}
    await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "cerca", "arguments": {"testo": "cucina"}},
    }, intestazioni=intestazioni)
    assert len(chiamate) == 1
    _app_vista, turno_visto = chiamate[0]
    assert turno_visto == "turno-guardia-mcp", (
        "il turno che arriva al dispatcher non e' quello dell'intestazione "
        "X-HIRIS-Turno: la guardia dell'officina riceverebbe un'identita' "
        "sbagliata (o nessuna) e non potrebbe piu' distinguere il turno "
        "della proposta da quello della conferma")
