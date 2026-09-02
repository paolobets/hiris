"""Il ponte che mantiene una promessa vede il catalogo della promessa.

`SOLA_LETTURA` e' un elenco di **ammissione**, non di esclusione, e deve
valere su ENTRAMBE le strade. Se valesse solo sul ramo sincrono, uno strumento
nuovo che scrive entrerebbe da solo nel turno del ponte il giorno in cui
qualcuno lo aggiunge alla chat -- e nessuno se ne accorgerebbe: e' esattamente
il verso sbagliato di derivazione che `keeper/exchange.py` esiste per
evitare.

L'intestazione `X-HIRIS-Promessa` dice QUALE turno sta parlando. Non e'
un'autenticazione -- quella resta il token interno -- e per questo va
VERIFICATA: un id che non corrisponde a una promessa `in_corso` non vale
niente, altrimenti sarebbe un modo per farsi servire un catalogo diverso
mostrando un identificatore qualunque.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.action.actuator import ActionActuator
from hiris.app.chat_settings import ChatSettings
from hiris.app.keeper.store import AgendaStore
from hiris.app.keeper.sweeper import Sweeper
from hiris.app.memory.store import MemoryStore
from tests._contracts import assert_stessa_firma
from tests.test_knowledge_tools import _semina_casa

TOKEN = "token-di-prova-del-turno-di-promessa"
INTESTAZIONI_CLI = {"X-HIRIS-Internal-Token": TOKEN}
ADESSO = 1787324400.0


class PortaFinta:
    """SA eseguire davvero: se il guardiano lasciasse passare un `execute`, la
    casa verrebbe toccata e questo doppio lo registrerebbe. Una finta che non
    sa produrre il difetto non lo puo' provare."""

    def __init__(self) -> None:
        self.chiamate = []

    async def execute(self, call: dict, *, actor: str):
        self.chiamate.append((call, actor))
        return {"eseguito": True, "esecuzione_id": "e1"}


def test_la_finta_porta_combacia_con_la_firma_vera():
    """Guardia (review Task 7, round 3): questa finta era cablata come
    `Sweeper(..., execute=porta.execute, ...)`, lo stesso cablaggio di
    `server.py`, e divergeva gia' (`chiamata, actor="chat"` contro
    `call, *, actor` del vero) senza che niente diventasse rosso."""
    assert_stessa_firma(ActionActuator.execute, PortaFinta.execute, nome="execute")


@pytest_asyncio.fixture
async def rotta(aiohttp_client, tmp_path, monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)

    app = server.create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    app["ha_client"] = mock_ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app["internal_token"] = TOKEN

    casa = _semina_casa(tmp_path)
    memoria = MemoryStore(str(tmp_path / "memoria.db"))
    promesse = AgendaStore(str(tmp_path / "promesse.db"))
    porta = PortaFinta()
    app["home_space_store"] = casa
    app["memory_store"] = memoria
    app["agenda"] = promesse
    app["action_actuator"] = porta
    # L'orologio vero: e' lui che conclude una promessa e fa partire la
    # notifica dalla porta. `interpreta` non viene mai chiamato in questi test
    # -- qui il turno gira sul ponte, non sulla catena.
    async def _mai(_promessa):
        raise AssertionError("il turno non doveva passare dalla catena")

    app["sweeper"] = Sweeper(promesse, execute=porta.execute, interpreta=_mai)
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    try:
        yield client, promesse, porta
    finally:
        promesse.close()
        memoria.close()
        casa.close()


def _crea_in_corso(promesse, *, recapito=None) -> str:
    ident = promesse.create({
        "specie": "chiedi", "frase": "fra un'ora verifica la temperatura",
        "quando_ts": ADESSO + 10, "domanda": "e' aumentata?",
        "recapito": recapito,
    }, now=ADESSO)["promessa"]["id"]
    assert promesse.prendi(ident, now=ADESSO + 11) is True
    return ident


async def _jsonrpc(client, corpo, *, promessa=None):
    intestazioni = dict(INTESTAZIONI_CLI)
    if promessa is not None:
        intestazioni["X-HIRIS-Promessa"] = promessa
    return await client.post("/api/mcp", json=corpo, headers=intestazioni)


def _nomi(corpo) -> set:
    return {voce["name"] for voce in corpo["result"]["tools"]}


@pytest.mark.asyncio
async def test_col_turno_di_promessa_il_catalogo_e_quello_della_promessa(rotta):
    client, promesse, _ = rotta
    ident = _crea_in_corso(promesse)

    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, promessa=ident)

    nomi = _nomi(await risposta.json())
    assert "conclude" in nomi, "senza «conclude» il turno non ha modo di finire"
    for scrive in ("execute", "remember", "promise", "cancel"):
        assert scrive not in nomi, (
            f"«{scrive}» scrive: un turno che gira senza nessuno davanti non "
            "deve nemmeno vederlo")


@pytest.mark.asyncio
async def test_senza_l_intestazione_il_catalogo_resta_quello_della_chat(rotta):
    client, promesse, _ = rotta
    _crea_in_corso(promesse)

    risposta = await _jsonrpc(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    nomi = _nomi(await risposta.json())
    assert "conclude" not in nomi
    assert "execute" in nomi


@pytest.mark.asyncio
async def test_un_id_di_promessa_NON_in_corso_non_vale(rotta):
    """L'intestazione dice quale turno parla; non e' un'autenticazione, e non
    deve diventare un modo per farsi dare un catalogo diverso mostrando un id
    qualunque."""
    client, _promesse, _ = rotta
    inventato = "questo-id-non-esiste"

    risposta = await _jsonrpc(
        client, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, promessa=inventato)

    assert "conclude" not in _nomi(await risposta.json())


@pytest.mark.asyncio
async def test_col_turno_di_promessa_esegui_viene_RIFIUTATO_e_la_casa_non_si_tocca(rotta):
    client, promesse, porta = rotta
    ident = _crea_in_corso(promesse)

    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "execute",
                   "arguments": {"servizio": "light.turn_on",
                                 "bersaglio": {"entity_id": "light.cucina_1"}}},
    }, promessa=ident)

    corpo = await risposta.json()
    testo = corpo["result"]["content"][0]["text"]
    assert "non e' disponibile mentre mantengo una promessa" in testo
    assert porta.chiamate == [], (
        "la porta ha eseguito davvero: il guardiano non sta davanti al "
        "dispatcher sul percorso del ponte")


@pytest.mark.asyncio
async def test_col_turno_di_promessa_guarda_funziona_ancora(rotta):
    """L'elenco AMMETTE i sei lettori: chiuderli tutti renderebbe il turno
    cieco invece che prudente."""
    client, promesse, _ = rotta
    ident = _crea_in_corso(promesse)

    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "view",
                   "arguments": {"tipo": "entita", "riferimento": "light.cucina_1"}},
    }, promessa=ident)

    corpo = await risposta.json()
    assert corpo["result"].get("isError") is not True
    assert json.loads(corpo["result"]["content"][0]["text"])["esiste"] is True


@pytest.mark.asyncio
async def test_concludi_dal_ponte_chiude_la_promessa_e_fa_partire_la_notifica(rotta):
    """Il secondo tempo di `mantieni`, raggiunto dall'altra strada.

    Sul ramo sincrono la conclusione torna a `interpreta_promise` e
    l'orologio chiude. Sul ponte non torna niente a nessuno: `conclude` e'
    una `tools/call` come le altre, e se questa rotta si limitasse a
    registrarla nel dispatcher la promessa resterebbe `in_corso` per
    sempre -- che e' peggio di una fallita, perche' non si vede."""
    client, promesse, porta = rotta
    ident = _crea_in_corso(promesse, recapito="notify.mobile_app_x")

    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "conclude",
                   "arguments": {"avvisare": True,
                                 "testo": "in bagno +0,4 gradi"}},
    }, promessa=ident)

    corpo = await risposta.json()
    assert corpo["result"].get("isError") is not True

    p = promesse.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["testo"] == "in bagno +0,4 gradi"
    assert p["avvisare"] is True
    assert porta.chiamate, "la notifica non e' partita dalla porta"
    assert porta.chiamate[0][0]["servizio"] == "notify.mobile_app_x"
    assert porta.chiamate[0][1] == "schedulatore"


@pytest.mark.asyncio
async def test_concludere_senza_avvisare_chiude_lo_stesso_e_non_notifica(rotta):
    """«La condizione non si e' verificata» e' un esito RIUSCITO, e resta
    scritto: e' cio' che rende il silenzio un fatto dichiarato."""
    client, promesse, porta = rotta
    ident = _crea_in_corso(promesse, recapito="notify.mobile_app_x")

    await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "conclude",
                   "arguments": {"avvisare": False, "testo": "tutto fermo"}},
    }, promessa=ident)

    p = promesse.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["testo"] == "tutto fermo"
    assert porta.chiamate == [], "non c'era niente per cui disturbarlo"


@pytest.mark.asyncio
async def test_concludi_con_argomenti_sbagliati_non_chiude_niente(rotta):
    """Il guardiano rifiuta e la promessa resta in corso: chiudere su un
    `conclude` malformato scriverebbe in pagina un testo che il modello non
    ha mai composto."""
    client, promesse, _porta = rotta
    ident = _crea_in_corso(promesse)

    risposta = await _jsonrpc(client, {
        "jsonrpc": "2.0", "id": 8, "method": "tools/call",
        "params": {"name": "conclude", "arguments": {"avvisare": "forse"}},
    }, promessa=ident)

    assert (await risposta.json())["result"]["isError"] is True
    assert promesse.read(ident)["stato"] == "in_corso"
