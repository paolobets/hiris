"""Una busta per «e' andata?» (A-29, A-30) -- decisione D3 del 03/10/2026.

**Cosa difende.** Fino alla Tappa 2 `HAClient` diceva «Home Assistant non ha
risposto» in nove modi e otto forme: `get_states` e `get_services`
sollevavano, `get_config` rendeva `{}` e `statistic_ids` `None` (due silenzi
che si leggevano come «la casa non ha niente»), e `related`, `problems`,
`system_log` chiamavano «risposta in forma inattesa» una connessione caduta.

Adesso ogni guasto di una lettura e' la STESSA busta, costruita in un posto
solo (`proxy/ha_client.py::_failure`)::

    {"errore": testo, "causa": "silenzio" | "rifiuto" | "forma" | "richiesta",
     "codice": il codice di Home Assistant, o lo stato HTTP, o None}

Il successo tiene la sua forma di oggi.

**L'elenco delle letture si CHIEDE** (`_client_reads`, come per il costo):
una lettura nuova entra qui il giorno in cui nasce. Le sole voci scritte a
mano sono liste di AMMISSIONE, ognuna con la sua ragione.
"""
import aiohttp
import pytest

from hiris.app.proxy.ha_client import HAClient
from tests.test_fonte_unica import _client_reads
from tests.test_ha_client_invio import _arguments

#: Le letture che NON rispondono con la busta, e perche'. Chiude per difetto:
#: una lettura nuova senza busta e' rossa finche' qualcuno non la scrive qui.
NOT_ENVELOPED = {
    "read_configuration": "canale della configurazione: con le scritture, Tappa 7",
    "read_registries": "(registri, non_disponibili): la lettura dell'anagrafe, "
                       "dove ogni registro caduto si nomina da se'; il registro "
                       "solo, con la busta, e' `read_registry`",
    "read_dashboards": "(plance, non_disponibili): la plancia che manca si "
                       "nomina da se', e una casa con l'elenco caduto resta "
                       "quella di prima (`behavior.reread_dashboards`)",
}

#: Le raffiche di voci INDIPENDENTI: la busta e' per la raffica che non parte
#: (tutte le risposte mancano); un rifiuto o una forma sbagliata restano della
#: loro voce (`non_letti`, o `None` per una finestra della sonda), e non
#: spengono le altre.
PER_ITEM = {
    "traces": "una chiave rifiutata finisce in `non_letti`",
    "behavior_configs": "un corpo rifiutato finisce in `non_letti`",
    "recorded_changes": "una finestra senza risposta e' `None`",
}

#: I risultati con cui Home Assistant risponde a ogni comando che le letture
#: mandano, nella forma vera minima. Un comando che non e' qui SOLLEVA
#: nominandosi: una lettura nuova non passa mai a vuoto.
SUCCESS = {
    "validate_config": {},
    "config/label_registry/list": [],
    "config/category_registry/list": [],
    "config/auth/list": [],
    "get_panels": {},
    "extract_from_target": {},
    "history/history_during_period": {},
    "recorder/list_statistic_ids": [],
    "recorder/statistics_during_period": {},
    "automation/config": {"config": {}},
    "search/related": {},
    "repairs/list_issues": {"issues": []},
    "system_log/list": [],
    "trace/list": [],
    "trace/get": {},
    "frontend/get_translations": {"resources": {}},
    "get_config": {},
}

HA_ERROR = {"code": "unknown_error", "message": "rifiutato per prova"}


class _Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def json(self):
        return self._body

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, state):
        self._state = state

    def get(self, url):
        if self._state == "silenzio":
            raise aiohttp.ClientConnectionError("rete assente")
        if self._state == "rifiuto":
            return _Response(500, None)
        if self._state == "forma":
            return _Response(200, "non una forma")
        return _Response(200, [])


def _client(state: str) -> HAClient:
    """Un `HAClient` vero con il solo trasporto finto, in uno dei quattro
    stati: `successo`, `rifiuto`, `silenzio`, `forma`."""
    client = HAClient(base_url="http://ha.test", token="t")

    async def ws_send(commands, timeout=10.0):
        replies = []
        for index, (command, _extra) in enumerate(commands, start=1):
            if state == "silenzio":
                replies.append(None)
            elif state == "rifiuto":
                replies.append({"id": index, "type": "result", "success": False,
                                "error": dict(HA_ERROR)})
            elif state == "forma":
                replies.append({"id": index, "type": "result", "success": True,
                                "result": "non una forma"})
            else:
                assert command in SUCCESS, (
                    f"la finta non sa come risponde Home Assistant a `{command}`")
                replies.append({"id": index, "type": "result", "success": True,
                                "result": SUCCESS[command]})
        return replies

    client._ws_send = ws_send
    client._session = _Session(state)
    return client


async def _ask(name: str, state: str):
    return await getattr(_client(state), name)(**_arguments(getattr(HAClient, name)))


def _is_envelope(answer, cause: str) -> bool:
    return (isinstance(answer, dict) and isinstance(answer.get("errore"), str)
            and answer["errore"] and answer.get("causa") == cause
            and "codice" in answer)


READS = sorted(set(_client_reads()) - set(NOT_ENVELOPED))


def test_la_derivazione_contiene_le_letture_di_oggi():
    assert len(READS) > 15, READS
    for name in ("get_states", "get_services", "get_config", "statistic_ids",
                 "related", "problems", "system_log", "history"):
        assert name in READS
    assert set(NOT_ENVELOPED) <= set(_client_reads()), (
        "un'ammissione nomina una lettura che non c'e' piu': si toglie")


@pytest.mark.parametrize("name", READS)
@pytest.mark.asyncio
async def test_il_successo_non_e_una_busta(name):
    answer = await _ask(name, "successo")
    assert not (isinstance(answer, dict) and "errore" in answer), (name, answer)


@pytest.mark.parametrize("name", READS)
@pytest.mark.asyncio
async def test_la_connessione_caduta_e_un_silenzio(name):
    answer = await _ask(name, "silenzio")
    assert _is_envelope(answer, "silenzio"), (
        f"`{name}` a connessione caduta risponde {answer!r}: serve la busta "
        "con `causa: silenzio`")


@pytest.mark.parametrize("name", READS)
@pytest.mark.asyncio
async def test_un_rifiuto_di_home_assistant_e_un_rifiuto(name):
    answer = await _ask(name, "rifiuto")
    if name in PER_ITEM:
        assert not (isinstance(answer, dict) and "errore" in answer), (name, answer)
        return
    assert _is_envelope(answer, "rifiuto"), (
        f"`{name}` a un rifiuto risponde {answer!r}: serve la busta con "
        "`causa: rifiuto`")


@pytest.mark.parametrize("name", READS)
@pytest.mark.asyncio
async def test_una_forma_inattesa_e_una_forma(name):
    answer = await _ask(name, "forma")
    if name in PER_ITEM:
        assert not (isinstance(answer, dict) and "errore" in answer), (name, answer)
        return
    assert _is_envelope(answer, "forma"), (
        f"`{name}` a una risposta in forma inattesa risponde {answer!r}: serve "
        "la busta con `causa: forma`")


@pytest.mark.asyncio
async def test_il_rifiuto_conserva_il_motivo_e_il_codice_di_home_assistant():
    answer = await _ask("problems", "rifiuto")
    assert answer == {"errore": "rifiutato per prova", "causa": "rifiuto",
                      "codice": "unknown_error"}


@pytest.mark.asyncio
async def test_il_rifiuto_REST_porta_lo_stato_http():
    answer = await _ask("get_states", "rifiuto")
    assert answer["codice"] == 500


@pytest.mark.asyncio
async def test_le_voci_rifiutate_di_una_raffica_portano_il_motivo():
    traces = await _ask("traces", "rifiuto")
    configs = await _ask("behavior_configs", "rifiuto")
    assert traces["non_letti"] == {"automation.1": "rifiutato per prova"}
    assert configs["non_letti"] == {"automation.a": "rifiutato per prova"}


@pytest.mark.asyncio
async def test_una_domanda_malformata_non_parte():
    """Un identificatore che non ha la forma di un entity_id si ferma prima
    della rete, con la stessa busta e la causa `richiesta`: non e' Home
    Assistant ad aver detto di no."""
    client = _client("silenzio")
    answer = await client.history(["non valido"], "a", "b")
    assert _is_envelope(answer, "richiesta")


@pytest.mark.asyncio
async def test_get_states_filtra_ancora():
    client = _client("successo")

    class _Full(_Session):
        def get(self, url):
            return _Response(200, [{"entity_id": "light.a"}, {"entity_id": "light.b"}])

    client._session = _Full("successo")
    assert await client.get_states(["light.b"]) == [{"entity_id": "light.b"}]
