"""Un solo invio (A-28) e il costo dichiarato (R16).

**Cosa difende.** Ogni domanda di HIRIS a Home Assistant passa da DUE porte
sole del client: `_ws_send` (N comandi WebSocket su UNA connessione) e
`_rest_get` (una lettura REST). Prima le vie d'invio WebSocket erano tre
(`_ws_batch`, `_ws_request`, `_ws_command`) piu' quattro `_ws_batch(...)[0]`
riscritti a mano: tre contratti diversi per la stessa cosa, e nessun posto
solo da cui contare quante connessioni costa una domanda.

**Il costo si DICHIARA** (R16): ogni metodo pubblico che parla con Home
Assistant porta `@cost(ws=..., rest=...)`, le connessioni che apre, e la
dichiarazione si chiede al metodo (`HAClient.get_states.cost`). Qui la si
confronta con cio' che il metodo apre davvero, su un trasporto finto che conta.

**L'elenco dei metodi si CHIEDE, non si ricopia** (CLAUDE.md, «Un cancello
CHIEDE il suo elenco»): le letture sono quelle che `tests/test_fonte_unica.py`
gia' deriva da `HAClient` (`_client_reads`: i metodi pubblici meno le
scritture, per verbo, e meno il ciclo di vita). Le scritture dichiarano il loro
costo anche loro, ma qui si misura solo la presenza della dichiarazione: per
chiamarle fino in fondo servirebbero argomenti diversi per lo stesso nome di
parametro (`domain` e' un helper per `create_helper`, un dominio configurabile
per `save_configuration`), e le scritture sono le porte della Tappa 7.
"""
import ast
import inspect
import logging
import pathlib
from unittest.mock import patch

import pytest

from hiris.app.proxy.ha_client import HAClient
from tests.test_fonte_unica import LIFECYCLE, _client_reads

_CLIENT = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app" / "proxy" / "ha_client.py"

#: Gli argomenti con cui si chiama una lettura, per NOME di parametro: valori
#: che fanno percorrere al metodo la strada PIU' LUNGA (un entity_id valido,
#: un dominio che ha una configurazione, un tipo che `search/related` accetta),
#: perche' il costo dichiarato e' quello della strada intera. Un parametro
#: obbligatorio che non e' qui fa fallire la prova nominandosi: una lettura
#: nuova con un parametro nuovo chiede una decisione, non passa a vuoto.
ARGUMENTS = {
    "entity_ids": ["automation.a"],
    "entities": ["automation.a"],
    "entity_id": "automation.a",
    "from_iso": "2026-10-03T00:00:00+00:00",
    "to_iso": "2026-10-03T01:00:00+00:00",
    "start": "2026-10-03T00:00:00+00:00",
    "end": "2026-10-03T01:00:00+00:00",
    "windows": [(0.0, 1.0)],
    "domain": "automation",
    "key": "1",
    "item_id": "1",
    "run_id": "r",
    "automation_id": "1",
    "item_type": HAClient.RELATED_ITEM_TYPES[0],
    "identifier": "x",
    "identifiers": ["sensor.a"],
    "keys": [("automation", "1")],
    "target": {"entity_id": ["automation.a"]},
    "language": "it",
    "triggers": [],
    "conditions": [],
    "actions": [],
}

#: Le sole risposte che servono a non fermare un metodo a meta' strada: con il
#: registro delle entita' vuoto `read_registries` non chiederebbe gli alias.
#: Ogni altro comando risponde con successo e `result: None`.
ANSWERS = {"config/entity_registry/list": [{"entity_id": "automation.a"}]}


class _Response:
    status = 200

    def raise_for_status(self):
        return None

    async def json(self):
        return []

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _CountingSession:
    """La sessione HTTP del client: ogni richiesta e' una connessione REST."""

    def __init__(self, opened):
        self._opened = opened

    def _request(self, *args, **kwargs):
        self._opened["rest"] += 1
        return _Response()

    get = post = delete = _request


def _mount(client, opened):
    """Sostituisce il solo trasporto: `_ws_send` e la sessione HTTP."""
    async def ws_send(commands, timeout=10.0):
        # Come il vero: nessun comando, nessuna connessione.
        if commands:
            opened["ws"] += 1
        return [{"id": i, "type": "result", "success": True,
                 "result": ANSWERS.get(command)}
                for i, (command, _extra) in enumerate(commands, start=1)]

    client._ws_send = ws_send
    client._session = _CountingSession(opened)


def _arguments(method) -> dict:
    found = {}
    for name, parameter in list(inspect.signature(method).parameters.items())[1:]:
        if name in ARGUMENTS:
            found[name] = ARGUMENTS[name]
        elif parameter.default is inspect.Parameter.empty:
            raise AssertionError(
                f"`{method.__name__}` vuole `{name}`, e la prova non sa con cosa "
                "chiamarlo: aggiungilo ad ARGUMENTS con un valore che percorra "
                "la strada intera")
    return found


def _ports() -> list[str]:
    """Ogni metodo pubblico di `HAClient` che e' una coroutine, meno il ciclo
    di vita: chiesto alla classe, non scritto qui."""
    return sorted(name for name, member in inspect.getmembers(HAClient)
                  if not name.startswith("_") and inspect.iscoroutinefunction(member)
                  and name not in LIFECYCLE)


# --- la derivazione non si e' svuotata ---------------------------------------

def test_la_derivazione_contiene_le_letture_di_oggi():
    """Un insieme improvvisamente piccolo e' un cancello che sembra vivo e non
    guarda piu' niente. Le letture qui sotto sono un'ancora, non l'elenco:
    l'elenco viene da `_client_reads`."""
    reads = _client_reads()
    assert len(reads) > 20, sorted(reads)
    for name in ("get_states", "get_services", "history", "read_dashboards",
                 "read_registries", "problems", "get_config", "statistic_ids",
                 "get_translations", "calendars"):
        assert name in reads, f"`{name}` e' uscita dalle letture derivate"
    assert set(reads) <= set(_ports())


# --- il costo dichiarato -----------------------------------------------------

@pytest.mark.parametrize("name", _ports())
def test_ogni_porta_dichiara_il_suo_costo(name):
    declared = getattr(getattr(HAClient, name), "cost", None)
    assert isinstance(declared, dict) and set(declared) == {"ws", "rest"}, (
        f"`HAClient.{name}` non dichiara il suo costo: va decorata con "
        "`@cost(ws=..., rest=...)`, le connessioni che apre (R16)")


@pytest.mark.parametrize("name", sorted(_client_reads()))
@pytest.mark.asyncio
async def test_ogni_lettura_apre_le_connessioni_che_dichiara(name):
    method = getattr(HAClient, name)
    declared = getattr(method, "cost", None)
    assert declared is not None, f"`HAClient.{name}` non dichiara il suo costo"
    client = HAClient(base_url="http://ha.test", token="t")
    opened = {"ws": 0, "rest": 0}
    _mount(client, opened)

    await getattr(client, name)(**_arguments(method))

    assert opened == declared, (
        f"`HAClient.{name}` dichiara {declared}, apre {opened}")


# --- un solo punto apre le connessioni ---------------------------------------

#: Dove il client puo' APRIRE una connessione verso Home Assistant. Lista di
#: AMMISSIONE, con la ragione: una funzione nuova che apre una connessione per
#: conto suo esce dal conto del costo, e qualcuno deve deciderlo per iscritto.
OPENERS = {
    "ws_connect": {
        "_ws_send": "l'invio: N comandi su una connessione",
        "_ws_loop": "il WebSocket di lunga vita, quello degli eventi",
    },
    "ClientSession": {
        "start": "la sessione HTTP del client, una per la vita dell'add-on",
        "_ws_send": "la connessione dell'invio vive e muore con la sua sessione",
    },
    "get": {
        "_rest_get": "la lettura REST",
        "read_configuration": "il canale della configurazione (Tappa 7)",
    },
}


def _opening_sites() -> dict[str, set[str]]:
    """`{chiamata: {funzioni che la fanno}}`, dal sorgente del client.

    `get` conta solo `self._session.get`: `dict.get` non apre niente."""
    sites: dict[str, set[str]] = {name: set() for name in OPENERS}
    tree = ast.parse(_CLIENT.read_text(encoding="utf-8"))
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Attribute) and called.attr == "ws_connect":
                sites["ws_connect"].add(function.name)
            if ((isinstance(called, ast.Attribute) and called.attr == "ClientSession")
                    or (isinstance(called, ast.Name) and called.id == "ClientSession")):
                sites["ClientSession"].add(function.name)
            if (isinstance(called, ast.Attribute) and called.attr == "get"
                    and isinstance(called.value, ast.Attribute)
                    and called.value.attr == "_session"):
                sites["get"].add(function.name)
    return sites


def test_le_connessioni_si_aprono_solo_dove_e_ammesso():
    sites = _opening_sites()
    assert sites["ws_connect"], "la scansione non trova nemmeno `_ws_loop`: si e' rotta"
    for call, admitted in OPENERS.items():
        assert sites[call] == set(admitted), (
            f"`{call}` si chiama in {sorted(sites[call])}, ammesse "
            f"{sorted(admitted)}: un invio fuori da `_ws_send`/`_rest_get` non "
            "e' contato nel costo dichiarato")


# --- `_ws_send`, il trasporto vero (da `tests/test_ws_batch.py`) -------------

class _FakeWS:
    def __init__(self, log):
        self._log = log
        self._pending = [{"type": "auth_required"}]

    async def receive_json(self):
        if self._pending:
            return self._pending.pop(0)
        raise AssertionError("nessun messaggio da consegnare")

    async def send_json(self, payload):
        if payload.get("type") == "auth":
            self._pending.append({"type": "auth_ok"})
            return
        self._log["commands"].append(payload)
        self._pending.append({
            "id": payload["id"], "type": "result", "success": True,
            "result": [{"echo": payload["type"]}],
        })

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, log):
        self._log = log

    def ws_connect(self, url):
        self._log["connections"] += 1
        return _FakeWS(self._log)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture
def log():
    return {"connections": 0, "commands": []}


def _client():
    return HAClient(base_url="http://ha.test", token="t")


@pytest.mark.asyncio
async def test_sei_comandi_una_connessione_sola(log):
    commands = [(f"comando/{i}", None) for i in range(6)]
    with patch("aiohttp.ClientSession", lambda *a, **k: _FakeSession(log)):
        replies = await _client()._ws_send(commands)
    assert log["connections"] == 1
    assert len(replies) == 6
    assert [r["result"][0]["echo"] for r in replies] == [f"comando/{i}" for i in range(6)]


@pytest.mark.asyncio
async def test_le_risposte_seguono_l_ordine_dei_comandi(log):
    with patch("aiohttp.ClientSession", lambda *a, **k: _FakeSession(log)):
        replies = await _client()._ws_send([("primo", None), ("secondo", {"x": 1})])
    assert replies[0]["result"][0]["echo"] == "primo"
    assert replies[1]["result"][0]["echo"] == "secondo"
    assert log["commands"][1]["x"] == 1


@pytest.mark.asyncio
async def test_nessun_comando_nessuna_connessione(log):
    with patch("aiohttp.ClientSession", lambda *a, **k: _FakeSession(log)):
        assert await _client()._ws_send([]) == []
    assert log["connections"] == 0


@pytest.mark.asyncio
async def test_una_connessione_fallita_non_solleva(log):
    def explode(*a, **k):
        raise OSError("rete assente")
    with patch("aiohttp.ClientSession", explode):
        assert await _client()._ws_send([("a", None), ("b", None)]) == [None, None]


@pytest.mark.asyncio
async def test_ogni_connessione_lascia_una_riga_di_debug(log, caplog):
    """La riga da cui si contano le connessioni dal vivo (Task 13 del piano):
    una per connessione, non una per comando."""
    with (caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"),
          patch("aiohttp.ClientSession", lambda *a, **k: _FakeSession(log))):
        await _client()._ws_send([("a", None), ("b", None)])
        await _client()._ws_send([("c", None)])
    lines = [r for r in caplog.records if r.getMessage().startswith("_ws_send:")]
    assert len(lines) == log["connections"] == 2
