"""Denylist di lettura del gateway MCP.

Due lati, e il secondo e' quello che conta: filtrare gli argomenti in ingresso
non basta, perche' molte letture non prendono affatto un'entita'
(get_home_status restituisce tutta la casa, get_logbook senza entity_id elenca
tutti gli eventi). Se il perimetro valesse solo sugli argomenti, basterebbe
OMETTERE il parametro per aggirarlo: il test dell'omissione qui sotto e' il
motivo per cui esiste la potatura in uscita.
"""
from pathlib import Path

import pytest
import yaml
from aiohttp import web

from hiris.app.api.handlers_execute import handle_execute
from hiris.app.api.read_denylist import (
    DEFAULT_READ_DENYLIST,
    LOCAL_CHAT_HEADER,
    denied_entities_in_inputs,
    is_denied,
    parse_read_denylist,
    prune_read_result,
)

_DENY = ["lock.*", "camera.ingresso"]


# ---------------------------------------------------------------------------
# Configurazione: parsing e valore predefinito
# ---------------------------------------------------------------------------

def test_parse_none_gives_protective_default():
    # Anello mancante nella catena di configurazione (variabile d'ambiente non
    # esportata): vale il default protettivo, non "nessuna denylist".
    assert parse_read_denylist(None) == list(DEFAULT_READ_DENYLIST)


def test_parse_empty_string_empties_the_denylist():
    # L'elenco deve restare svuotabile per tornare al comportamento precedente.
    assert parse_read_denylist("") == []
    assert parse_read_denylist("   ") == []


def test_parse_csv_trims():
    assert parse_read_denylist("lock.*, camera.ingresso ,person.*") == [
        "lock.*", "camera.ingresso", "person.*"]


def test_default_covers_reading_sensitive_domains():
    d = list(DEFAULT_READ_DENYLIST)
    for pat in ("lock.*", "alarm_control_panel.*", "camera.*",
                "person.*", "device_tracker.*"):
        assert pat in d


def test_default_is_not_the_action_dangerous_domains():
    # I domini pericolosi del semaforo riguardano l'AZIONE: una tapparella e'
    # pericolosa da muovere ma innocua da leggere, una telecamera e' l'opposto.
    # Due nozioni diverse che devono restare separate.
    from hiris.app.security.semaphore import DANGEROUS_DOMAINS
    domini = {p.split(".", 1)[0] for p in DEFAULT_READ_DENYLIST}
    assert "cover" not in domini            # pericolosa in azione, innocua in lettura
    assert "camera" in domini               # innocua in azione, sensibile in lettura
    assert domini != set(DANGEROUS_DOMAINS)


# ---------------------------------------------------------------------------
# Glob: dominio intero e singola entita'
# ---------------------------------------------------------------------------

def test_glob_matches_whole_domain():
    assert is_denied("lock.porta_ingresso", _DENY)
    assert is_denied("lock.garage", _DENY)


def test_glob_matches_single_entity_only():
    assert is_denied("camera.ingresso", _DENY)
    assert not is_denied("camera.giardino", _DENY)


def test_empty_denylist_denies_nothing():
    assert not is_denied("lock.porta", [])


# ---------------------------------------------------------------------------
# Lato ingresso: una richiesta che nomina un'entita' coperta viene rifiutata
# ---------------------------------------------------------------------------

def test_denied_in_inputs_finds_list_and_scalar():
    assert denied_entities_in_inputs({"entity_ids": ["light.salotto", "lock.porta"]},
                                     _DENY) == ["lock.porta"]
    assert denied_entities_in_inputs({"entity_id": "lock.porta"}, _DENY) == ["lock.porta"]
    assert denied_entities_in_inputs({"ids": ["camera.ingresso"]}, _DENY) == ["camera.ingresso"]


def test_denied_in_inputs_normalizes_automation_id():
    assert denied_entities_in_inputs({"automation_id": "apri_porta"},
                                     ["automation.*"]) == ["automation.apri_porta"]


def test_denied_in_inputs_clean_request():
    assert denied_entities_in_inputs({"entity_ids": ["light.salotto"]}, _DENY) == []


# ---------------------------------------------------------------------------
# Lato uscita: potatura per forma di risposta
# ---------------------------------------------------------------------------

def test_prune_home_status_drops_denied_entities():
    risposta = [{"id": "light.salotto", "state": "on"},
                {"id": "lock.porta", "state": "locked"}]
    out = prune_read_result("get_home_status", risposta, _DENY)
    assert out["entities"] == [{"id": "light.salotto", "state": "on"}]
    assert out["filtered"] == {"shown": 1, "total": 2}


def test_prune_home_status_untouched_when_nothing_denied():
    risposta = [{"id": "light.salotto", "state": "on"}]
    assert prune_read_result("get_home_status", risposta, _DENY) == risposta


def test_prune_entity_states():
    risposta = [{"id": "lock.porta", "state": "locked"}]
    out = prune_read_result("get_entity_states", risposta, _DENY)
    assert out["entities"] == []
    assert out["filtered"] == {"shown": 0, "total": 1}


def test_prune_history_series():
    risposta = [{"id": "sensor.temp", "buckets": []}, {"id": "lock.porta", "buckets": []}]
    out = prune_read_result("get_history", risposta, _DENY)
    assert [s["id"] for s in out["series"]] == ["sensor.temp"]
    assert out["filtered"] == {"shown": 1, "total": 2}


def test_prune_area_entities_drops_ids_and_empty_areas():
    risposta = {"Ingresso": ["lock.porta", "light.ingresso"], "Garage": ["lock.garage"]}
    out = prune_read_result("get_area_entities", risposta, _DENY)
    assert out["areas"] == {"Ingresso": ["light.ingresso"]}
    assert out["filtered"] == {"shown": 1, "total": 3}


def test_prune_logbook_without_entity_id():
    # Il caso centrale: get_logbook invocato SENZA entity_id elenca tutta la
    # casa. Il filtro sugli argomenti non lo tocca; la potatura si'.
    risposta = {
        "entries": [
            {"when": "1", "name": "Porta", "message": "sbloccata", "entity_id": "lock.porta"},
            {"when": "2", "name": "Salotto", "message": "acceso", "entity_id": "light.salotto"},
        ],
        "count": 2, "hours": 24, "entity_id": None,
    }
    out = prune_read_result("get_logbook", risposta, _DENY)
    assert [v["entity_id"] for v in out["entries"]] == ["light.salotto"]
    assert out["count"] == 1
    assert out["filtered"] == {"shown": 1, "total": 2}


def test_prune_logbook_keeps_system_entries():
    # Una voce senza entity_id (avvio di HA, script) non e' attribuibile a
    # un'entita' vietata: una denylist toglie cio' che nomina, non tutto il resto.
    risposta = {"entries": [{"when": "1", "name": "Home Assistant", "message": "avviato"}],
                "count": 1, "hours": 24, "entity_id": None}
    assert prune_read_result("get_logbook", risposta, _DENY) == risposta


def test_prune_advisories_drops_entry_and_evidence_ids():
    risposta = {
        "advisories": [
            {"severity": "high", "title": "Batteria scarica",
             "evidence": {"entity_id": "lock.porta", "pct": 5}},
            {"severity": "info", "title": "Entita' senza area",
             "evidence": {"entities": ["light.salotto", "lock.garage"], "count": 2}},
        ],
        "count": 2,
    }
    out = prune_read_result("get_advisories", risposta, _DENY)
    assert len(out["advisories"]) == 1
    assert out["advisories"][0]["evidence"]["entities"] == ["light.salotto"]
    # Taglio dentro una voce che resta: dichiarato sulla voce, non confuso col
    # taglio sul numero di voci.
    assert out["advisories"][0]["evidence_filtered"] == {"shown": 1, "total": 2}
    assert out["count"] == 1
    assert out["filtered"] == {"shown": 1, "total": 2}


def test_prune_advisories_keeps_system_entries_without_entity_id():
    # Segnalazione di sistema (spazio disco, add-on fermo): non riguarda
    # un'entita', quindi la denylist non ha nulla da dire e resta visibile.
    risposta = {"advisories": [{"severity": "warn", "title": "Disco quasi pieno",
                                "evidence": {"free_gb": 2}}], "count": 1}
    assert prune_read_result("get_advisories", risposta, _DENY) == risposta


def test_prune_automation_config_blocked_when_it_names_a_denied_entity():
    # Una config di automazione non e' un elenco potabile: o e' pulita o si
    # blocca. Potarne i campi la renderebbe una config diversa da quella vera.
    risposta = {"alias": "Apri di sera",
                "action": [{"service": "switch.turn_on",
                            "target": {"entity_id": "lock.porta"}}]}
    out = prune_read_result("get_automation_config", risposta, _DENY)
    assert set(out) == {"error"}
    assert "denylist" in out["error"]


def test_prune_automation_config_passes_when_clean():
    risposta = {"alias": "Luci sera",
                "action": [{"service": "light.turn_on",
                            "target": {"entity_id": "light.salotto"}}]}
    assert prune_read_result("get_automation_config", risposta, _DENY) == risposta


def test_prune_recall_knowledge_passes_through():
    # Limite dichiarato nel design: la memoria e' testo libero, nessuna
    # denylist per entita' puo' intercettare un appunto scritto a mano.
    risposta = {"results": [{"id": 1, "kind": "note", "content": "la porta e' rotta"}]}
    assert prune_read_result("recall_knowledge", risposta, _DENY) == risposta


def test_prune_error_dict_passes_through():
    risposta = {"error": "Home Assistant non raggiungibile"}
    assert prune_read_result("get_home_status", risposta, _DENY) == risposta


# ---------------------------------------------------------------------------
# Fail-closed sulle forme non riconosciute
# ---------------------------------------------------------------------------

def test_prune_unknown_tool_is_blocked():
    out = prune_read_result("un_tool_mai_visto", [{"id": "light.salotto"}], _DENY)
    assert set(out) == {"error"}


def test_prune_unknown_shape_is_blocked():
    # get_home_status che torna un dict invece di un elenco: forma che la
    # potatura non sa trattare -> si blocca, non si lascia passare.
    out = prune_read_result("get_home_status", {"entita": ["lock.porta"]}, _DENY)
    assert set(out) == {"error"}


def test_prune_list_item_without_id_is_blocked():
    out = prune_read_result("get_home_status", [{"stato": "on"}], _DENY)
    assert set(out) == {"error"}


def test_prune_empty_denylist_is_identity():
    risposta = [{"id": "lock.porta", "state": "locked"}]
    assert prune_read_result("get_home_status", risposta, []) == risposta
    # Anche una forma sconosciuta passa: senza denylist non c'e' nulla da potare.
    assert prune_read_result("un_tool_mai_visto", risposta, []) == risposta


# ---------------------------------------------------------------------------
# Integrazione: POST /api/execute
# ---------------------------------------------------------------------------

class _FakeDispatcher:
    def __init__(self, result=None):
        self.calls = []
        self._result = result if result is not None else []

    async def dispatch(self, name, inputs, allowed_entities=None,
                       allowed_services=None, chatbot_id=None, cloud=True, **kw):
        self.calls.append((name, inputs))
        return self._result


def _make_app(tmp_path, *, denylist, result=None, local_token="LOCALE"):
    app = web.Application()
    app["internal_token"] = "secret"
    app["data_dir"] = str(tmp_path)
    # get_logbook non e' (ancora) fra i READ_TOOLS esposti al gateway: la sua
    # potatura si verifica sulla funzione, non sull'endpoint.
    app["execute_policy"] = {"tools": ["get_home_status", "get_history"],
                             "allowed_entities": None, "allowed_services": None}
    app["read_denylist"] = denylist
    app["local_execute_token"] = local_token
    app["tool_dispatcher"] = _FakeDispatcher(result)
    app.router.add_post("/api/execute", handle_execute)
    return app


async def _post(client, body, headers=None):
    h = {"X-HIRIS-Internal-Token": "secret"}
    h.update(headers or {})
    return await client.post("/api/execute", json=body, headers=h)


@pytest.mark.asyncio
async def test_execute_rejects_request_naming_a_denied_entity(aiohttp_client, tmp_path):
    app = _make_app(tmp_path, denylist=_DENY)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_history",
                                "input": {"entity_ids": ["lock.porta"], "days": 1}})
    assert resp.status == 403
    body = await resp.json()
    assert "lock.porta" in body["error"]
    # Rifiutata PRIMA di raggiungere Home Assistant.
    assert app["tool_dispatcher"].calls == []


@pytest.mark.asyncio
async def test_execute_prunes_response_when_parameter_is_omitted(aiohttp_client, tmp_path):
    # Il modo con cui il perimetro verrebbe aggirato: nessun argomento da
    # filtrare, quindi il rifiuto in ingresso non scatta e resta solo la potatura.
    app = _make_app(tmp_path, denylist=_DENY, result=[
        {"id": "light.salotto", "state": "on"}, {"id": "lock.porta", "state": "locked"}])
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}})
    assert resp.status == 200
    result = (await resp.json())["result"]
    assert result["entities"] == [{"id": "light.salotto", "state": "on"}]
    assert result["filtered"] == {"shown": 1, "total": 2}


@pytest.mark.asyncio
async def test_execute_blocks_unprunable_shape(aiohttp_client, tmp_path):
    app = _make_app(tmp_path, denylist=_DENY, result={"inatteso": True})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}})
    result = (await resp.json())["result"]
    assert set(result) == {"error"}


@pytest.mark.asyncio
async def test_execute_empty_denylist_restores_previous_behaviour(aiohttp_client, tmp_path):
    risposta = [{"id": "lock.porta", "state": "locked"}]
    app = _make_app(tmp_path, denylist=[], result=risposta)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}})
    assert (await resp.json())["result"] == risposta
    resp = await _post(client, {"tool": "get_history",
                                "input": {"entity_ids": ["lock.porta"]}})
    assert resp.status == 200


@pytest.mark.asyncio
async def test_execute_missing_denylist_key_falls_back_to_default(aiohttp_client, tmp_path):
    # Anello mancante nel cablaggio: la denylist non e' inerte, vale il default.
    app = _make_app(tmp_path, denylist=None, result=[{"id": "lock.porta", "state": "locked"}])
    del app["read_denylist"]
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_history", "input": {"entity_ids": ["lock.porta"]}})
    assert resp.status == 403


@pytest.mark.asyncio
async def test_execute_local_chat_is_exempt(aiohttp_client, tmp_path):
    # La chat in-addon passa dalla stessa API via LocalExecuteClient: li' vale
    # il perimetro del Chatbot, non questa denylist. Il marcatore e' un segreto
    # di processo che un chiamante remoto non puo' indovinare.
    risposta = [{"id": "lock.porta", "state": "locked"}]
    app = _make_app(tmp_path, denylist=_DENY, result=risposta)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}},
                       headers={LOCAL_CHAT_HEADER: "LOCALE"})
    assert (await resp.json())["result"] == risposta
    resp = await _post(client, {"tool": "get_history", "input": {"entity_ids": ["lock.porta"]}},
                       headers={LOCAL_CHAT_HEADER: "LOCALE"})
    assert resp.status == 200


@pytest.mark.asyncio
async def test_execute_forged_local_marker_does_not_exempt(aiohttp_client, tmp_path):
    app = _make_app(tmp_path, denylist=_DENY, result=[{"id": "lock.porta", "state": "locked"}])
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_history", "input": {"entity_ids": ["lock.porta"]}},
                       headers={LOCAL_CHAT_HEADER: "indovinato"})
    assert resp.status == 403


# ---------------------------------------------------------------------------
# Catena di configurazione: se salta un anello l'opzione resta inerte
# ---------------------------------------------------------------------------

_BASE = Path(__file__).resolve().parents[1] / "hiris"


def test_option_is_in_config_yaml_options_and_schema():
    cfg = yaml.safe_load((_BASE / "config.yaml").read_text(encoding="utf-8"))
    assert "execute_api_read_denylist" in cfg["options"]
    assert "execute_api_read_denylist" in cfg["schema"]


def test_config_yaml_default_matches_the_code_default():
    # Due elenchi che dicono la stessa cosa divergono al primo cambio: qui si
    # verifica che il default mostrato all'utente sia quello che il codice applica.
    cfg = yaml.safe_load((_BASE / "config.yaml").read_text(encoding="utf-8"))
    assert parse_read_denylist(cfg["options"]["execute_api_read_denylist"]) == \
        list(DEFAULT_READ_DENYLIST)


def test_run_sh_exports_env():
    sh = (_BASE / "run.sh").read_text(encoding="utf-8")
    assert "EXECUTE_API_READ_DENYLIST" in sh
    # L'export deve restare condizionato all'esistenza dell'opzione: e' cio' che
    # distingue "opzione assente" (default protettivo) da "opzione svuotata".
    assert 'has("execute_api_read_denylist")' in sh


def test_server_reads_the_env_var():
    py = (_BASE / "app" / "server.py").read_text(encoding="utf-8")
    assert 'os.environ.get("EXECUTE_API_READ_DENYLIST")' in py
    assert 'app["read_denylist"]' in py
    assert 'app["local_execute_token"]' in py


def test_translations_present():
    for f in ("it.yaml", "en.yaml"):
        t = (_BASE / "translations" / f).read_text(encoding="utf-8")
        assert "execute_api_read_denylist" in t


def test_local_client_sends_the_marker():
    py = (_BASE / "app" / "mcp" / "local_client.py").read_text(encoding="utf-8")
    assert "LOCAL_CHAT_HEADER" in py


@pytest.mark.asyncio
async def test_execute_action_tools_are_untouched(aiohttp_client, tmp_path):
    # La denylist e' di LETTURA: non tocca il percorso delle azioni.
    app = _make_app(tmp_path, denylist=_DENY, result={"ok": True})
    app["execute_policy"]["tools"].append("send_notification")
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "send_notification",
                                "input": {"channel": "ha_persistent", "message": "lock.porta"}})
    assert resp.status == 200
    assert (await resp.json())["result"] == {"ok": True}
