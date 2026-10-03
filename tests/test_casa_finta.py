"""La casa finta e' il client vero col trasporto sostituito (D8, T-04).

**Cosa difende.** Le finte di Home Assistant delle prove imitavano i metodi
pubblici di `HAClient` a mano: la forma della risposta, il filtro di
`get_states`, gli errori erano scritti una seconda volta, e potevano mentire
(quattro finte sollevavano dove il vero non solleva; diciassette ignoravano il
filtro). `scripts/casa_finta.py::CasaFinta` E' un `HAClient`: sostituisce solo
il trasporto e risponde con i messaggi GREZZI di Home Assistant presi dagli
ingressi. Forma, filtro e busta d'errore sono quelli del codice vero per
costruzione.

**Le due prove della derivazione** (CLAUDE.md, «Un cancello CHIEDE il suo
elenco»): i metodi che la finta sovrascrive si chiedono alle due classi, e le
letture che si chiamano si chiedono a `HAClient` (`_client_reads`, lo stesso
elenco di `test_fonte_unica.py` e `test_ha_client_invio.py`).

Mutazioni ESEGUITE (03/10/2026, Tappa 2, Task 4):

- aggiunto a `HAClient` un metodo `ghost_read` che manda il comando
  `ghost/command`: la prova parametrica ha un caso in piu',
  `[ghost_read]`, VERDE senza toccare la prova -- e il caso registra che la
  finta ha sollevato `UnservedCommand` nominando `ghost/command`;
- la finta torna a rispondere `{"success": true, "result": {}}` a un comando
  WebSocket che non conosce (cio' che faceva `CountingHouse`): rossa su dieci
  letture -- `automation_traces`, `extract_from_target`, `hourly_statistics`,
  `panels`, `recorded_changes`, `related`, `trace`, `traces`, `users`,
  `validate_config` -- «ha risposto a un comando che gli ingressi non
  servono»;
- `CasaFinta` sovrascrive anche `get_states` (rende gli stati degli ingressi
  cosi' come sono): rosse quattro prove -- la sovrascrittura non e' il
  trasporto; il filtro non c'e' piu'; il rifiuto iniettato su `/api/states`
  non arriva; la lettura REST non si registra.
"""
import asyncio
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casa_finta
from casa_finta import CasaFinta, UnservedCommand

from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs
from tests.test_fonte_unica import _client_reads
from tests.test_ha_client_invio import _arguments


def _run(coroutine):
    return asyncio.run(coroutine)


# ── e' il client vero ───────────────────────────────────────────────────────

def test_la_casa_finta_e_un_client_vero():
    assert isinstance(CasaFinta(synthetic_inputs()), HAClient)


def _overridden() -> set[str]:
    """I nomi che `CasaFinta` ridefinisce sopra `HAClient`, chiesti alle due
    classi. I dunder restano fuori: `__init__` costruisce, non trasporta."""
    return {name for name in vars(CasaFinta)
            if name in vars(HAClient) and not name.startswith("__")}


def test_la_casa_finta_sostituisce_solo_il_trasporto():
    """(a) della derivazione: tutto cio' che `HAClient` sa fare arriva alla
    finta per ereditarieta', meno il trasporto. `TRANSPORT` e' una lista di
    AMMISSIONE (enuncia il cancello): un metodo nuovo sovrascritto e' vietato
    finche' qualcuno non lo scrive li', con la ragione."""
    assert _overridden() == set(casa_finta.TRANSPORT)
    public = {name for name, member in inspect.getmembers(HAClient)
              if not name.startswith("_") and callable(member)}
    # La derivazione non si e' svuotata: le letture di oggi ci sono.
    assert len(public) >= 30 and {"get_states", "read_registries", "problems"} <= public
    inherited = {name for name in public
                 if getattr(CasaFinta, name) is getattr(HAClient, name)}
    assert inherited == public - set(casa_finta.TRANSPORT)


# ── ogni lettura risponde come il vero, o si nomina ─────────────────────────

def _reads() -> list[str]:
    return sorted(name for name in _client_reads()
                  if inspect.iscoroutinefunction(getattr(HAClient, name)))


def test_la_derivazione_delle_letture_non_e_vuota():
    reads = _reads()
    assert len(reads) >= 20, reads
    assert {"get_states", "read_registries", "behavior_configs", "related"} <= set(reads)


@pytest.mark.parametrize("name", _reads())
def test_ogni_lettura_risponde_dagli_ingressi_o_si_nomina(name):
    """(b) della derivazione. Ogni lettura di `HAClient`, chiamata sulla casa
    sintetica: o risponde -- e allora ogni comando che ha mandato e' uno di
    quelli che gli ingressi servono --, o solleva `UnservedCommand` col nome
    del comando che ha mandato. Mai un vuoto: una lettura nuova che chiede
    qualcosa di nuovo si vede."""
    house = CasaFinta(synthetic_inputs())
    method = getattr(house, name)
    try:
        _run(method(**_arguments(getattr(HAClient, name))))
    except UnservedCommand as unserved:
        # Di un percorso REST si nomina il percorso, senza la domanda.
        asked = house.calls[-1][0].split("?", 1)[0]
        assert unserved.command == asked
        assert asked in str(unserved)
        assert asked not in house.served()
        return
    answered = {command for command, _extra in house.calls}
    assert answered <= house.served(), (
        f"`{name}` ha risposto a un comando che gli ingressi non servono: "
        f"{sorted(answered - house.served())}")


# ── la forma del vero, dagli ingressi ───────────────────────────────────────

def test_le_letture_della_cattura_rendono_gli_ingressi():
    inputs = synthetic_inputs()
    house = CasaFinta(synthetic_inputs())
    assert _run(house.read_registries()) == (inputs["registries"], [])
    assert _run(house.get_states([])) == inputs["states"]
    assert _run(house.statistic_ids()) == set(inputs["statistic_ids"])
    assert _run(house.behavior_configs(["automation.automazione_uno"])) == inputs["behavior"]
    assert _run(house.get_config()) == inputs["ha_config"]
    assert _run(house.get_services()) == inputs["services"]
    assert _run(house.get_translations("it")) == inputs["translations"]["report"]
    assert _run(house.problems()) == inputs["problems"]
    assert _run(house.system_log()) == inputs["system_log"]
    dashboards = inputs["dashboards"]
    assert _run(house.read_dashboards()) == (dashboards["entries"], dashboards["unavailable"])


def test_get_states_filtra_come_il_vero():
    """Diciassette finte ignoravano il filtro: qui il filtro e' quello del
    client, perche' la finta risponde a `GET /api/states` e basta."""
    house = CasaFinta(synthetic_inputs())
    rows = _run(house.get_states(["light.luce_uno", "sensor.non_esiste"]))
    assert [row["entity_id"] for row in rows] == ["light.luce_uno"]


def test_una_plancia_senza_corpo_torna_fra_le_non_disponibili():
    """La forma della casa vera (01/10/2026): la principale in modalita'
    automatica non ha un corpo. La finta la ricostruisce col rifiuto che Home
    Assistant manda (`config_not_found`), e il client la mette fra le non
    disponibili da se'."""
    entries = [{"url_path": None, "title": "Principale", "config": None},
               {"url_path": "plancia-uno", "title": "Plancia uno", "mode": "storage",
                "config": {"views": []}}]
    inputs = {**synthetic_inputs(),
              "dashboards": {"entries": entries, "unavailable": ["principale"]}}
    house = CasaFinta(inputs)
    assert _run(house.read_dashboards()) == (entries, ["principale"])


def test_un_alias_viaggia_con_le_voci_estese_non_con_l_elenco():
    """`config/entity_registry/list` non manda gli alias
    (`RegistryEntry.as_partial_dict`), `get_entries` si'
    (`extended_dict`): la finta li mette dove li mette Home Assistant, e il
    client li riporta sulla riga da se'."""
    inputs = synthetic_inputs()
    inputs["registries"]["entita"][0]["aliases"] = ["lampada della nonna"]
    house = CasaFinta(inputs)
    listed = house._ws_reply("config/entity_registry/list", None)["result"]
    assert all("aliases" not in row for row in listed)
    registries, unavailable = _run(house.read_registries())
    assert registries["entita"][0]["aliases"] == ["lampada della nonna"]
    assert unavailable == []


# ── gli errori si iniettano per comando, e la busta e' quella vera ──────────

def test_un_rifiuto_iniettato_arriva_nella_busta_del_client():
    house = CasaFinta(synthetic_inputs(), refuse={
        "repairs/list_issues": {"code": "unknown_command", "message": "Unknown command."},
        "/api/states": 500})
    assert _run(house.problems()) == {"errore": "Unknown command.", "causa": "rifiuto",
                                      "codice": "unknown_command"}
    assert _run(house.get_states([])) == {"errore": "Home Assistant ha risposto 500",
                                          "causa": "rifiuto", "codice": 500}


def test_un_silenzio_iniettato_e_un_silenzio_del_client():
    house = CasaFinta(synthetic_inputs(), silence={"system_log/list", "/api/services"})
    assert _run(house.system_log())["causa"] == "silenzio"
    assert _run(house.get_services())["causa"] == "silenzio"


def test_una_risposta_aggiunta_serve_un_comando_che_gli_ingressi_non_portano():
    house = CasaFinta(synthetic_inputs(), answers={
        "search/related": lambda extra: {"automation": [f"automation.{extra['item_id']}"]}})
    assert _run(house.related("entity", "x")) == {"automation": ["automation.x"]}
    assert "search/related" in house.served()


# ── un comando non servito solleva, e il prodotto non lo inghiotte ──────────

def test_un_comando_non_servito_solleva_nominandosi_anche_sotto_un_except():
    """`UnservedCommand` non e' un `Exception`: un `except Exception` del
    prodotto lo trasformerebbe in «Home Assistant non ha risposto», cioe' in
    una prova verde per la ragione sbagliata."""
    house = CasaFinta(synthetic_inputs())

    async def swallowing():
        try:
            return await house.history(["sensor.contatore_uno"],
                                       "2026-10-01T00:00:00+00:00",
                                       "2026-10-01T01:00:00+00:00")
        except Exception:
            return "inghiottito"

    with pytest.raises(UnservedCommand, match="/api/history/period"):
        _run(swallowing())


def test_una_scrittura_non_servita_solleva_nominandosi():
    house = CasaFinta(synthetic_inputs())
    with pytest.raises(UnservedCommand, match="/api/services/light/turn_on"):
        _run(house.call_service("light", "turn_on", {"entity_id": "light.luce_uno"}))


# ── registra chiamate e connessioni ─────────────────────────────────────────

def test_registra_chiamate_e_connessioni_come_le_dichiara_il_client():
    house = CasaFinta(synthetic_inputs())
    _run(house.read_registries())
    _run(house.get_states([]))
    assert [kind for kind, _what in house.connections] == ["ws", "ws", "rest"]
    assert len([c for c in house.connections if c[0] == "ws"]) == \
        HAClient.read_registries.cost["ws"]
    assert house.calls[-1] == ("/api/states", None)
    assert ("config/entity_registry/get_entries",
            {"entity_ids": [row["entity_id"] for row in
                            synthetic_inputs()["registries"]["entita"]]}) in house.calls


def test_ogni_ingresso_catturato_serve_almeno_un_comando():
    """Un ingresso che la casa finta non serve a nessuno e' un file scritto e
    mai letto. Si chiede alla finta: tolto un ingresso, cio' che serve
    diminuisce. Gli ingressi si chiedono a `casa.INPUTS`."""
    import casa

    whole = CasaFinta(synthetic_inputs()).served()
    for name in casa.INPUTS:
        without = {key: value for key, value in synthetic_inputs().items() if key != name}
        assert CasaFinta(without).served() < whole, f"l'ingresso `{name}` non serve niente"


# ── il websocket di lunga vita: eventi, iscrizioni, caduta, autenticazione ──
#
# La forma dei messaggi e' quella di Home Assistant al tag `2026.9.4`, letta il
# 03/10/2026 (`websocket_api/auth.py`, `websocket_api/messages.py`,
# `websocket_api/commands.py`, `core.py`, `config/config_entries.py`): vedi il
# docstring di `casa_finta.SilentConnection`.

async def _open(connection) -> list[dict]:
    """Apre una connessione come fa il client: chiede, si autentica, e rende
    i due messaggi dell'autenticazione."""
    ws = connection.ws_connect("ws://casa.invalid/api/websocket")
    required = await ws.receive_json()
    await ws.send_json({"type": "auth", "access_token": "segreto"})
    return [required, await ws.receive_json()]


async def _next(connection) -> dict:
    return (await asyncio.wait_for(connection.__anext__(), 1)).json()


def test_l_autenticazione_si_rifiuta_come_la_rifiuta_home_assistant():
    connection = casa_finta.SilentConnection()
    connection.refuse_next_auth()

    async def two():
        return await _open(connection), await _open(connection)

    refused, accepted = _run(two())
    assert refused[0]["type"] == "auth_required" and "ha_version" in refused[0]
    assert refused[1] == {"type": "auth_invalid",
                          "message": "Invalid access token or password"}
    assert accepted[1]["type"] == "auth_ok"
    assert connection.opened == 2
    # Il gettone non si registra: e' una credenziale.
    assert all(message.get("type") != "auth" for message in connection.sent)


def test_un_evento_arriva_solo_a_chi_si_e_iscritto_con_l_id_dell_iscrizione():
    connection = casa_finta.SilentConnection()

    async def scenario():
        await _open(connection)
        await connection.send_json({"id": 7, "type": "subscribe_events",
                                    "event_type": "state_changed"})
        aiter(connection)
        confirmed = await _next(connection)
        delivered = connection.push_event("state_changed", {"entity_id": "light.uno"})
        refused = connection.push_event("lovelace_updated", {})
        return confirmed, delivered, refused, await _next(connection)

    confirmed, delivered, refused, event = _run(scenario())
    assert confirmed == {"id": 7, "type": "result", "success": True, "result": None}
    assert delivered and not refused
    assert event["id"] == 7 and event["type"] == "event"
    assert set(event["event"]) == {"event_type", "data", "origin", "time_fired", "context"}
    assert event["event"]["event_type"] == "state_changed"
    assert event["event"]["data"] == {"entity_id": "light.uno"}


def test_l_iscrizione_alle_integrazioni_manda_l_elenco_poi_i_cambi():
    rows = synthetic_inputs()["registries"]["integrazioni"]
    house = CasaFinta(synthetic_inputs())
    connection = house._session

    async def scenario():
        await _open(connection)
        await connection.send_json({"id": 9, "type": "config_entries/subscribe"})
        aiter(connection)
        confirmed, snapshot = await _next(connection), await _next(connection)
        changed = {**rows[0], "state": "setup_retry"}
        connection.push_config_entry_change("updated", changed)
        return confirmed, snapshot, await _next(connection)

    confirmed, snapshot, change = _run(scenario())
    assert confirmed == {"id": 9, "type": "result", "success": True, "result": None}
    assert snapshot == {"id": 9, "type": "event",
                        "event": [{"type": None, "entry": row} for row in rows]}
    assert change["id"] == 9
    assert change["event"] == [{"type": "updated",
                                "entry": {**rows[0], "state": "setup_retry"}}]


def test_le_integrazioni_senza_ingresso_non_si_servono():
    inputs = synthetic_inputs()
    del inputs["registries"]["integrazioni"]
    connection = CasaFinta(inputs)._session

    async def scenario():
        await _open(connection)
        await connection.send_json({"id": 9, "type": "config_entries/subscribe"})

    with pytest.raises(UnservedCommand, match="config_entries/subscribe"):
        _run(scenario())


def test_un_comando_sconosciuto_sulla_connessione_lunga_si_nomina():
    connection = casa_finta.SilentConnection()

    async def scenario():
        await _open(connection)
        await connection.send_json({"id": 3, "type": "ghost/subscribe"})

    with pytest.raises(UnservedCommand, match="ghost/subscribe"):
        _run(scenario())


def test_la_connessione_cade_quando_la_si_fa_cadere():
    connection = casa_finta.SilentConnection()

    async def scenario():
        await _open(connection)
        aiter(connection)
        connection.drop()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(connection.__anext__(), 1)
        return connection.listening

    assert _run(scenario()) == 1
