"""Il ponte serve il catalogo del MESTIERE, non «chat o promessa» (attori,
Task 3.6, 06/10/2026).

**Il buco.** Fino a qui il ponte conosceva due cataloghi: `mcp_names`,
`verify_init` e la sonda sceglievano fra chat e promessa con un booleano, e
`/api/mcp` serviva il catalogo della promessa solo con `X-HIRIS-Promessa` --
in ogni altro caso quello della chat, `execute` compreso, col dispatcher
della chat. Un terzo mestiere con strumenti (l'analista, D5) avrebbe ricevuto
sul ponte i nomi e la porta della chat.

**La cura.** Il catalogo lo dice la dichiarazione del mestiere
(`steering.Species.catalog`), da tutte e due le parti: il runner ci compone
`--allowedTools`, la sonda e `verify_init`; la rotta lo serve al turno che si
fa riconoscere con `X-HIRIS-Lavoro`, verificato contro un job preso in carico,
e dispaccia col guardiano del mestiere (`Species.guard`). Un'intestazione che
non vale chiude.

Qui il mestiere e' un analista FINTO, dichiarato con un catalogo e un
guardiano di prova: la prova guarda il ponte, non l'analista.
"""
from __future__ import annotations

import json
import time

import pytest

from hiris.app import steering
from hiris.app.agent import runner as ponte
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
from hiris.app.reasoning.queue import PRIORITY_BACKGROUND
from tests.test_mcp_chat_thread import TOKEN, rotta  # noqa: F401

_CERCA = next(d for d in KNOWLEDGE_TOOLS if d["name"] == "search")
_CONTA = {"name": "conta", "description": "uno strumento che solo questo "
          "mestiere ha", "input_schema": {"type": "object", "properties": {}}}
_INTESTAZIONI = {"X-HIRIS-Internal-Token": TOKEN}


class _Guardiano:
    """Il dispatcher di prova: dice chi ha risposto."""

    def __init__(self, visti: list):
        self._visti = visti

    async def dispatch(self, name, arguments):
        self._visti.append(name)
        return {"dal": "guardiano", "strumento": name}


@pytest.fixture
def mestiere(monkeypatch):
    """L'analista dichiarato con strumenti e guardiano, per la durata della
    prova. `SPECIES` e' un dizionario condiviso: runner e rotta lo leggono."""
    visti: list = []

    async def _guard(app, exchange):
        return _Guardiano(visti)

    monkeypatch.setitem(steering.SPECIES, steering.ANALYST_SPECIES, steering.Species(
        steering.ANALYST_SPECIES, "analisi", lambda: [_CERCA, _CONTA],
        PRIORITY_BACKGROUND, guard=_guard,
        gestures=steering.SPECIES[steering.ANALYST_SPECIES].gestures))
    # La vista dei mestieri autosufficienti si deriva all'import: qui la si
    # rideriva dalla dichiarazione di prova.
    monkeypatch.setattr(ponte, "_SELF_CONTAINED_KINDS", tuple(
        kind for kind, name in steering.JOB_SPECIES.items()
        if steering.SPECIES[name].self_contained))
    return visti


def _accoda_analisi(coda, *, prendi=True) -> str:
    adesso = time.time()
    job_id = coda.enqueue("analisi", {}, {"history": []}, adesso + 300, now=adesso)
    if prendi:
        preso = coda.claim(adesso + 1)
        assert preso is not None and preso["job_id"] == job_id
    return job_id


async def _rpc(client, metodo, intestazioni, params=None):
    corpo = {"jsonrpc": "2.0", "id": 1, "method": metodo}
    if params is not None:
        corpo["params"] = params
    risposta = await client.post("/api/mcp", json=corpo, headers=intestazioni)
    return (await risposta.json())["result"]


# ── il runner ────────────────────────────────────────────────────────────

def test_i_nomi_del_ponte_vengono_dalla_dichiarazione_del_mestiere(mestiere):
    """Mutazione ESEGUITA (06/10/2026): `mcp_names` che torna al catalogo
    della chat -- rossa (`execute` fra i nomi dell'analista)."""
    nomi = ponte.mcp_names(steering.ANALYST_SPECIES)
    assert nomi == (ponte.mcp_name("search"), ponte.mcp_name("conta"))
    argv = ponte._chat_claude_args("sistema.txt", "sonnet", active_tools=True,
                                   mcp_config="{}", species=steering.ANALYST_SPECIES)
    assert argv[argv.index("--allowedTools") + 1] == ",".join(nomi)


class _Risposta:
    """La risposta di `tools/list`, ESATTA per il turno: la sonda rifiuta
    anche un catalogo piu' largo del suo (G23-1)."""
    status_code = 200

    def __init__(self, specie):
        self._specie = specie

    def json(self):
        return {"jsonrpc": "2.0", "id": 1, "result": {"tools": [
            {"name": n} for n in steering.SPECIES[self._specie].tools_for_turn()]}}


class _ClientFinto:
    def __init__(self):
        self.intestazioni: list[dict] = []

    def post(self, *_a, headers=None, **_k):
        self.intestazioni.append(dict(headers or {}))
        lavoro = "X-HIRIS-Lavoro" in (headers or {})
        return _Risposta(steering.ANALYST_SPECIES if lavoro else "chat")


class _ProcessoFinto:
    returncode = 1
    stdout = ""
    stderr = "la CLI non e' stata lanciata: e' una prova"


def test_il_runner_si_fa_riconoscere_col_lavoro_fuori_da_chat_e_promessa(
        monkeypatch, mestiere):
    """Il turno dell'analista porta `X-HIRIS-Lavoro` nella sonda e nella
    mcp-config; quello della chat no (lo riconosce `X-HIRIS-Chat`)."""
    argv_visti: list = []
    monkeypatch.setattr(ponte.subprocess, "run",
                        lambda argv, *_a, **_k: argv_visti.append(argv) or _ProcessoFinto())
    for kind in ("analisi", "chat"):
        primo = len(argv_visti)
        client = _ClientFinto()
        ponte._reason_chat({"deadline_ts": time.time() + 300, "job_id": "J1",
                            "kind": kind, "context": {
                                "model": "sonnet", "system_prompt": "Sei HIRIS.",
                                "history": [{"role": "user", "content": "ciao"}],
                                "contesto": ""}},
                           "live", client=client, base_url="http://127.0.0.1:8099",
                           headers=_INTESTAZIONI)
        # La prima invocazione: senza `init` la seconda riparte senza strumenti.
        argv = argv_visti[primo]
        conf = json.loads(argv[argv.index("--mcp-config") + 1])
        intestazioni = conf["mcpServers"]["hiris"]["headers"]
        if kind == "analisi":
            assert intestazioni["X-HIRIS-Lavoro"] == "J1"
            assert client.intestazioni[0]["X-HIRIS-Lavoro"] == "J1"
            assert argv[argv.index("--allowedTools") + 1] == ",".join(
                ponte.mcp_names(steering.ANALYST_SPECIES))
        else:
            assert "X-HIRIS-Lavoro" not in intestazioni


# ── la rotta ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_la_rotta_serve_al_lavoro_il_catalogo_del_suo_mestiere(rotta, mestiere):
    """Mutazione ESEGUITA (06/10/2026): `tools/list` che ignora
    `X-HIRIS-Lavoro` -- rossa (arriva il catalogo della chat)."""
    client, coda, *_ = rotta
    job_id = _accoda_analisi(coda)
    catalogo = await _rpc(client, "tools/list",
                          {**_INTESTAZIONI, "X-HIRIS-Lavoro": job_id})
    assert [t["name"] for t in catalogo["tools"]] == ["search", "conta"]


@pytest.mark.asyncio
async def test_la_rotta_dispaccia_col_guardiano_del_mestiere(rotta, mestiere):
    """Mutazione ESEGUITA (06/10/2026): `_call_tool` che non chiede il
    guardiano -- rossa (risponde il dispatcher della chat)."""
    client, coda, *_ = rotta
    job_id = _accoda_analisi(coda)
    esito = await _rpc(client, "tools/call",
                       {**_INTESTAZIONI, "X-HIRIS-Lavoro": job_id,
                        "X-HIRIS-Turno": "turno-analista"},
                       {"name": "execute", "arguments": {}})
    assert json.loads(esito["content"][0]["text"]) == {
        "dal": "guardiano", "strumento": "execute"}
    assert mestiere == ["execute"]


@pytest.mark.asyncio
async def test_un_lavoro_che_non_vale_CHIUDE(rotta, mestiere):
    """Un job non preso in carico (scaduto, consegnato, mai esistito) non
    presta il catalogo del suo mestiere, e non ricade su quello della chat.

    Mutazione ESEGUITA (06/10/2026): `_exchange_species` che non guarda lo
    stato del job -- rossa (il catalogo arriva)."""
    client, coda, *_ = rotta
    in_coda = _accoda_analisi(coda, prendi=False)
    for ident in (in_coda, "mai-esistito"):
        intestazioni = {**_INTESTAZIONI, "X-HIRIS-Lavoro": ident}
        assert (await _rpc(client, "tools/list", intestazioni))["tools"] == []
        esito = await _rpc(client, "tools/call", intestazioni,
                           {"name": "search", "arguments": {"nome": "cucina"}})
        assert esito["isError"] is True
    assert mestiere == []


@pytest.mark.asyncio
async def test_un_lavoro_di_un_mestiere_SENZA_guardiano_chiude(rotta, mestiere):
    """`X-HIRIS-Lavoro` vale solo per un mestiere con guardiano: un job di
    chat che la porta non riceve per quella strada niente.

    Mutazione ESEGUITA (06/10/2026): il rifiuto col vecchio testo, «scaduto
    o gia' stato consegnato» -- rossa."""
    client, coda, *_ = rotta
    adesso = time.time()
    job_id = coda.enqueue("chat", {}, {"history": []}, adesso + 300, now=adesso)
    coda.claim(adesso + 1)
    intestazioni = {**_INTESTAZIONI, "X-HIRIS-Lavoro": job_id}
    catalogo = await _rpc(client, "tools/list", intestazioni)
    assert catalogo["tools"] == []
    # Il rifiuto dice anche questa ragione, non solo «scaduto o consegnato»:
    # il job e' vivo, e' il suo mestiere a non avere strumenti (giro 23).
    esito = await _rpc(client, "tools/call", intestazioni,
                       {"name": "search", "arguments": {"nome": "cucina"}})
    assert "il suo mestiere non ne ha" in esito["content"][0]["text"]


# ── G23-1 (giro 23 della revisione, 06/10/2026): la porta non resta aperta ──

def test_la_sonda_rifiuta_un_catalogo_PIU_LARGO_del_mestiere(monkeypatch):
    """Una sonda che guardava solo cosa manca passava il catalogo della
    chat a un turno dell'analista: c'era tutto, e in piu' `execute`.

    Mutazione ESEGUITA (06/10/2026): togliere il controllo su cio' che c'e'
    in piu' -- rossa (la sonda passa)."""
    class _Chat:
        def post(self, *_a, **_k):
            return _Risposta("chat")

    monkeypatch.setitem(steering.SPECIES, steering.ANALYST_SPECIES, steering.Species(
        steering.ANALYST_SPECIES, "analisi", lambda: [_CERCA], PRIORITY_BACKGROUND))
    ok, motivo = ponte.probe_tools(_Chat(), "http://127.0.0.1:8099", {},
                                   species=steering.ANALYST_SPECIES)
    assert ok is False and "execute" in motivo, motivo


def test_verify_init_rifiuta_gli_strumenti_del_server_che_il_turno_non_ha(mestiere):
    """Mutazione ESEGUITA (06/10/2026): togliere `extra` da `verify_init` --
    rossa."""
    esito = ponte.StreamOccurrence()
    esito.init = {
        "mcp_servers": [{"name": "hiris", "status": "connected"}],
        # Gli strumenti propri della CLI non portano il prefisso: non contano.
        "tools": [*ponte.mcp_names(steering.ANALYST_SPECIES), "ToolSearch"],
    }
    ok, motivo = ponte.verify_init(esito, species=steering.ANALYST_SPECIES)
    assert ok is True, motivo

    esito.init["tools"].append(ponte.mcp_name("execute"))
    ok, motivo = ponte.verify_init(esito, species=steering.ANALYST_SPECIES)
    assert ok is False and "execute" in motivo, motivo


@pytest.mark.asyncio
async def test_un_mestiere_con_catalogo_e_SENZA_guardiano_non_riceve_la_chat(
        rotta, monkeypatch):
    """Il caso del giro 23, eseguito: l'analista dichiarato con un catalogo e
    senza guardiano. Il runner manda `X-HIRIS-Lavoro` lo stesso, e la rotta
    chiude: niente catalogo della chat, niente `execute`.

    Mutazione ESEGUITA (06/10/2026): il runner che manda l'intestazione solo
    dove c'e' un guardiano -- rossa (nessuna intestazione)."""
    monkeypatch.setitem(steering.SPECIES, steering.ANALYST_SPECIES, steering.Species(
        steering.ANALYST_SPECIES, "analisi", lambda: [_CERCA], PRIORITY_BACKGROUND))
    monkeypatch.setattr(ponte, "_SELF_CONTAINED_KINDS", tuple(
        kind for kind, name in steering.JOB_SPECIES.items()
        if steering.SPECIES[name].self_contained))
    argv_visti: list = []
    monkeypatch.setattr(ponte.subprocess, "run",
                        lambda argv, *_a, **_k: argv_visti.append(argv) or _ProcessoFinto())

    class _Esatto:
        def post(self, *_a, **_k):
            return _Risposta(steering.ANALYST_SPECIES)

    ponte._reason_chat({"deadline_ts": time.time() + 300, "job_id": "J9",
                        "kind": "analisi", "context": {
                            "model": "sonnet", "system_prompt": "Sei HIRIS.",
                            "history": [{"role": "user", "content": "ciao"}],
                            "contesto": ""}},
                       "live", client=_Esatto(), base_url="http://127.0.0.1:8099",
                       headers=_INTESTAZIONI)
    argv = argv_visti[0]
    conf = json.loads(argv[argv.index("--mcp-config") + 1])
    assert conf["mcpServers"]["hiris"]["headers"]["X-HIRIS-Lavoro"] == "J9"

    client, coda, *_ = rotta
    job_id = _accoda_analisi(coda)
    intestazioni = {**_INTESTAZIONI, "X-HIRIS-Lavoro": job_id}
    catalogo = await _rpc(client, "tools/list", intestazioni)
    assert catalogo["tools"] == []
    # Il rifiuto dice anche questa ragione, non solo «scaduto o consegnato»:
    # il job e' vivo, e' il suo mestiere a non avere strumenti (giro 23).
    esito = await _rpc(client, "tools/call", intestazioni,
                       {"name": "search", "arguments": {"nome": "cucina"}})
    assert "il suo mestiere non ne ha" in esito["content"][0]["text"]
