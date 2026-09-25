"""Il ponte porta chi parla fino agli strumenti (le chat divise, Task 4).

**Il buco che queste prove chiudono.** Un turno di chat servito dal ponte
chiamava gli strumenti su `/api/mcp` SENZA soffitto e SENZA soggetto: una
persona non amministratrice, passando dal piano Claude Max, poteva far
scrivere un'automazione in casa -- cosa che il ramo sincrono le nega, e che
Home Assistant le negherebbe. E la cronaca degli atti non sapeva chi aveva
chiesto.

**La forma, uguale a `X-HIRIS-Promessa`.** Il runner manda `X-HIRIS-Chat:
<job_id>`; non e' un'autenticazione (quella resta la credenziale di turno), e
per questo la rotta la VERIFICA: vale solo per un job `kind="chat"` in stato
`claimed`. Un id inventato, o di un job ancora `pending`, non concede niente in
piu' di oggi.

**Perche' la prova e' su `confirm` e non su `propose`.** Il soffitto del
dispatcher (`home_space/tools.py::_confirm`) custodisce la porta che SCRIVE in
Home Assistant, cioe' `confirm`; `propose` compone una bozza nel nostro
archivio e non scrive niente, e il ramo sincrono non la rifiuta a nessuno. Il
fatto di sicurezza si asserisce dove sta: la scrittura non avviene.
"""
from __future__ import annotations

import json
import logging
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.journal import Journal
from hiris.app.agent import runner as ponte
from hiris.app.api import handlers_mcp
from hiris.app.api.soffitto import _SOLO_AMMINISTRATORI
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_thread import thread_for
from hiris.app.reasoning.queue import ReasoningQueue
from tests.test_construction_workshop import FintoHA, _intento

TOKEN = "token-di-prova-del-turno-di-chat"
INTESTAZIONI_CLI = {"X-HIRIS-Internal-Token": TOKEN}

MARTA = {"specie": "persona", "id": "marta", "nome": "Marta",
         "utente": "marta"}
PAOLO = {"specie": "persona", "id": "paolo", "nome": "Paolo",
         "utente": "paolo"}


@pytest_asyncio.fixture
async def rotta(aiohttp_client, tmp_path, monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)

    app = server.create_app()
    mock_ha = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    # Chi e' amministratore lo dice Home Assistant: Paolo si', Marta no.
    mock_ha.users = AsyncMock(return_value={"utenti": [
        {"id": "paolo", "amministratore": True, "proprietario": True},
        {"id": "marta", "amministratore": False, "proprietario": False},
    ]})
    app["ha_client"] = mock_ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    from conftest import credenziale_ponte
    credenziale_ponte(app, TOKEN)

    casa_ha = FintoHA()
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    coda = ReasoningQueue(os.path.join(str(tmp_path), "reasoning.db"))
    app["workshop"] = Workshop(casa_ha, archivio, cronaca)
    app["journal"] = cronaca
    app["reasoning_queue"] = coda
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    try:
        yield client, coda, archivio, casa_ha
    finally:
        archivio.close()
        cronaca.close()


def _accoda_chat(coda, soggetto, *, prendi=True) -> str:
    adesso = time.time()
    job_id = coda.enqueue(
        "chat", {},
        {"history": [{"role": "user", "content": "sì, procedi"}],
         "system_prompt": "Sei HIRIS.", "soggetto": soggetto},
        adesso + 300, now=adesso, thread=thread_for(soggetto, "ingress"))
    if prendi:
        preso = coda.claim(adesso + 1)
        assert preso is not None and preso["job_id"] == job_id
    return job_id


async def _proposta(client) -> str:
    officina = client.app["workshop"]
    esito = await officina.propose(_intento(), actor="chat",
                                   exchange="turno-1", now=time.time())
    assert "errore" not in esito, esito
    return esito["proposta_id"]


async def _confirm(client, proposta_id, *, chat=None):
    intestazioni = dict(INTESTAZIONI_CLI)
    intestazioni["X-HIRIS-Turno"] = "turno-2"
    if chat is not None:
        intestazioni["X-HIRIS-Chat"] = chat
    risposta = await client.post("/api/mcp", headers=intestazioni, json={
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "confirm", "arguments": {"proposta_id": proposta_id}}})
    corpo = await risposta.json()
    return json.loads(corpo["result"]["content"][0]["text"])


@pytest.fixture
def dispatcher_visti(monkeypatch):
    """Cosa la rotta ha passato al dispatcher -- il costruttore VERO gira."""
    visti: list[dict] = []
    vero = handlers_mcp.create_tool_dispatcher

    def _spia(app, **kw):
        visti.append(kw)
        return vero(app, **kw)

    monkeypatch.setattr(handlers_mcp, "create_tool_dispatcher", _spia)
    return visti


# 1. Il buco: una persona NON amministratrice non costruisce dal ponte.
@pytest.mark.asyncio
async def test_il_ponte_di_una_persona_non_amministratrice_non_scrive_in_casa(rotta):
    client, coda, archivio, casa_ha = rotta
    proposta = await _proposta(client)
    job_id = _accoda_chat(coda, MARTA)

    esito = await _confirm(client, proposta, chat=job_id)

    assert _SOLO_AMMINISTRATORI in (esito.get("errore") or ""), esito
    assert casa_ha.salvate == [], "Home Assistant ha ricevuto una scrittura"
    assert archivio.read(proposta)["stato"] == "in_attesa"


# 2. Lo stesso job, ma di un amministratore: il soffitto lo lascia passare.
@pytest.mark.asyncio
async def test_il_ponte_di_un_amministratore_attraversa_il_soffitto(
        rotta, dispatcher_visti):
    client, coda, _archivio, casa_ha = rotta
    proposta = await _proposta(client)
    job_id = _accoda_chat(coda, PAOLO)

    esito = await _confirm(client, proposta, chat=job_id)

    assert esito.get("applicata"), esito
    assert casa_ha.salvate, "la conferma dell'amministratore non ha scritto"
    visto = dispatcher_visti[-1]
    assert visto["soffitto"]["costruire"] is True
    assert visto["soggetto"] == PAOLO
    assert visto["frase"] == "sì, procedi"


# 3. Un'intestazione presente che non vale: si chiude, non si ripiega.
#
# Fix round 1 (review del Task 4): prima un id che non valeva ricadeva sul
# dispatcher SENZA soffitto -- cioe' un job scaduto, ripiegato o gia'
# consegnato mentre la CLI girava ancora riapriva la porta della scrittura.
# Il runner manda l'intestazione solo per i job di chat: se c'e' e non vale,
# nessuno strumento gira.
@pytest.mark.asyncio
@pytest.mark.parametrize("quale", ["inventato", "pending", "ripiego", "promessa"])
async def test_un_X_HIRIS_Chat_non_valido_non_fa_girare_nessuno_strumento(
        rotta, dispatcher_visti, caplog, quale):
    client, coda, archivio, casa_ha = rotta
    proposta = await _proposta(client)
    if quale == "inventato":
        ident = "non-esiste"
    elif quale == "pending":
        ident = _accoda_chat(coda, MARTA, prendi=False)
    elif quale == "ripiego":
        ident = _accoda_chat(coda, MARTA)
        assert coda.reclaim_expired(ident, time.time() + 400) is not None
    else:
        adesso = time.time()
        ident = coda.enqueue("promessa", {}, {"soggetto": MARTA},
                             adesso + 300, now=adesso)
        coda.claim(adesso + 1)

    with caplog.at_level(logging.WARNING, logger=handlers_mcp.__name__):
        esito = await _confirm(client, proposta, chat=ident)

    assert "non è più valido" in (esito.get("errore") or ""), esito
    assert casa_ha.salvate == [], "Home Assistant ha ricevuto una scrittura"
    assert archivio.read(proposta)["stato"] == "in_attesa"
    assert dispatcher_visti == [], "il dispatcher non doveva nemmeno nascere"
    assert "X-HIRIS-Chat" in caplog.text


@pytest.mark.asyncio
async def test_senza_intestazione_resta_il_comportamento_di_prima(
        rotta, dispatcher_visti, caplog):
    """Promesse e osservatore non la portano: non e' un'anomalia, e il turno
    va com'e' sempre andato -- nessun soffitto, nessun soggetto."""
    client, _coda, _archivio, casa_ha = rotta
    proposta = await _proposta(client)
    with caplog.at_level(logging.WARNING, logger=handlers_mcp.__name__):
        esito = await _confirm(client, proposta)
    assert esito.get("applicata"), esito
    assert casa_ha.salvate
    assert dispatcher_visti[-1].get("soffitto") is None
    assert dispatcher_visti[-1].get("soggetto") is None
    assert "X-HIRIS-Chat" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("storia", [["sì"], [None], [{"role": "user"}], "sì"])
async def test_una_cronologia_malformata_non_fa_cadere_la_rotta(
        rotta, dispatcher_visti, storia):
    """Un contesto storto da' una frase assente, non un 500."""
    client, coda, _archivio, _casa = rotta
    proposta = await _proposta(client)
    adesso = time.time()
    ident = coda.enqueue("chat", {}, {"history": storia, "soggetto": PAOLO},
                         adesso + 300, now=adesso,
                         thread=thread_for(PAOLO, "ingress"))
    coda.claim(adesso + 1)

    esito = await _confirm(client, proposta, chat=ident)

    assert esito.get("applicata"), esito
    assert dispatcher_visti[-1]["frase"] is None


# 4. config_mcp porta l'intestazione solo quando c'e' un job di chat.
def _intestazioni(conf: str) -> dict:
    return json.loads(conf)["mcpServers"]["hiris"]["headers"]


def test_config_mcp_porta_X_HIRIS_Chat_solo_per_un_job_di_chat():
    con = ponte.config_mcp("http://127.0.0.1:8099", "tok", "t", chat_job_id="J")
    assert _intestazioni(con)["X-HIRIS-Chat"] == "J"
    senza = ponte.config_mcp("http://127.0.0.1:8099", "tok", "t")
    assert "X-HIRIS-Chat" not in _intestazioni(senza)


# 5. Il runner: l'intestazione nell'argv vero, e il soggetto nel registro.
class _Risposta:
    status_code = 200

    def json(self):
        return {"jsonrpc": "2.0", "id": 1, "result": {"tools": [
            {"name": n.split("__")[-1]}
            for n in {*ponte.mcp_names(), *ponte.mcp_names(by_promise=True)}]}}


class _ClientFinto:
    def post(self, *_a, **_k):
        return _Risposta()


class _ProcessoFinto:
    returncode = 1
    stdout = ""
    stderr = "la CLI non e' stata lanciata: e' una prova"


@pytest.mark.parametrize("kind", ["chat", "promessa"])
def test_il_runner_manda_X_HIRIS_Chat_e_il_soggetto_solo_per_la_chat(
        monkeypatch, kind):
    argv_visti: list = []

    def _cli(argv, *_a, **_k):
        argv_visti.append(argv)
        return _ProcessoFinto()

    monkeypatch.setattr(ponte.subprocess, "run", _cli)
    righe: list[dict] = []
    ponte.set_turn_logger(righe.append)
    contesto = {"history": [{"role": "user", "content": "ciao"}],
                "system_prompt": "Sei HIRIS.", "contesto": "", "soggetto": MARTA}
    if kind == "promessa":
        contesto["promessa_id"] = "p1"
    try:
        ponte._reason_chat({"job_id": "J1", "kind": kind, "context": contesto},
                           "live", client=_ClientFinto(),
                           base_url="http://127.0.0.1:8099",
                           headers={"X-HIRIS-Internal-Token": "tok"})
    finally:
        ponte.set_turn_logger(None)

    argv = argv_visti[0]
    conf = _intestazioni(argv[argv.index("--mcp-config") + 1])
    if kind == "chat":
        assert conf["X-HIRIS-Chat"] == "J1"
        assert righe[-1]["subject"] == MARTA
    else:
        assert "X-HIRIS-Chat" not in conf
        assert righe[-1].get("subject") is None


def test_il_registro_dei_turni_scrive_il_soggetto_del_ponte(tmp_path):
    from hiris.app.usage.store import UsageStore

    archivio = UsageStore(str(tmp_path / "usage.db"))
    registra = server._registra_turno_ponte(archivio)
    registra({"species": "chat", "channel": "ponte", "provider": "subscription",
              "model": "m", "duration_ms": 1, "iterations": 1, "tools": [],
              "outcome": "riuscito", "subject": MARTA})
    assert archivio.turns()[0]["subject"] == MARTA
