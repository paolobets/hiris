"""I registri uno per uno, e il giro delle condizioni (Tappa 2, Task 5).

**Cosa difende.** Fino al 03/10/2026 chi voleva UN registro di Home Assistant
li chiedeva tutti: `read_registries` manda dieci comandi e poi un secondo giro
`config/entity_registry/get_entries` su ogni entita' della casa, per gli alias
che solo l'anagrafe usa. Lo pagavano il giro delle condizioni (ogni dieci
minuti, per la sola tabella `integrazioni`), il recapito delle promesse (per
`entita` e `dispositivi`) e l'officina (per `entita`) -- A-01, A-06. Le
etichette avevano una lettura propria, `list_labels`, che rendeva `[]` muto
quando la risposta non era una lista (A-33). E il giro delle condizioni
rileggeva `repairs/list_issues` che il giro dei cinque minuti aveva appena
letto (A-02).

Adesso: `HAClient.read_registry(nome)` legge un registro solo, dalla stessa
tabella `_REGISTRIES`, con la busta d'errore; `read_registries` resta
all'anagrafe; il giro delle condizioni legge i problemi da `app["ha_problems"]`
(A-02). Le integrazioni, che il Task 5 faceva leggere al giro e consegnare
all'anagrafe (A-11), dal Task 7 arrivano per evento: l'iscrizione
`config_entries/subscribe` (`integration_follower`).

Le prove girano sulla `CasaFinta`: il client vero col trasporto sostituito, che
registra i comandi e le connessioni.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.registry import ServiceRegistry
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.topology import rebuild
from hiris.app.keeper.recipient import recipients_for
from hiris.app.proxy.ha_client import HAClient
from hiris.app.server import integration_follower, watch_system_conditions
from tests._casa_sintetica import synthetic_inputs


def _run(coroutine):
    return asyncio.run(coroutine)


def _commands(house) -> list[str]:
    return [command for command, _extra in house.calls]


class _Observer:
    """L'osservatore, quanto basta: cio' che riceve."""

    def __init__(self):
        self.received: list[dict] = []

    def watch_system(self, *, problems, integrations, log_entries):
        self.received.append({"problems": problems, "integrations": integrations,
                              "log_entries": log_entries})
        return len(problems) + len(integrations) + len(log_entries)


# ── read_registry ────────────────────────────────────────────────────────────

def test_un_registro_solo_e_un_comando_solo_senza_alias():
    house = CasaFinta(synthetic_inputs())

    answer = _run(house.read_registry("entita"))

    assert _commands(house) == ["config/entity_registry/list"]
    assert len(house.connections) == 1
    assert [row["entity_id"] for row in answer["entita"]] == [
        row["entity_id"] for row in synthetic_inputs()["registries"]["entita"]]


def test_le_categorie_sono_una_connessione_e_portano_il_loro_ambito():
    inputs = synthetic_inputs()
    inputs["registries"]["categorie"] = [
        {"category_id": "c1", "name": "Luci", "ambito": "automation"},
        {"category_id": "c1", "name": "Luci", "ambito": "script"}]
    house = CasaFinta(inputs)

    answer = _run(house.read_registry("categorie"))

    assert len(house.connections) == 1
    assert set(_commands(house)) == {"config/category_registry/list"}
    assert sorted(row["ambito"] for row in answer["categorie"]) == ["automation", "script"]


def test_le_etichette_in_forma_inattesa_sono_un_guasto_non_un_elenco_vuoto():
    """A-33, cambia comportamento (approvato nella tabella del piano): prima
    `list_labels` rendeva `[]` -- «questa casa non ha etichette» -- quando Home
    Assistant rispondeva con qualcosa che non era un elenco."""
    house = CasaFinta(synthetic_inputs(),
                      answers={"config/label_registry/list": lambda extra: {"non": "lista"}})

    answer = _run(house.read_registry("etichette"))

    assert answer.get("causa") == "forma", answer
    assert answer.get("errore")


def test_un_registro_rifiutato_porta_il_motivo_di_home_assistant():
    house = CasaFinta(synthetic_inputs(), refuse={
        "config_entries/get": {"code": "unauthorized", "message": "niente"}})

    answer = _run(house.read_registry("integrazioni"))

    assert answer == {"errore": "niente", "causa": "rifiuto", "codice": "unauthorized"}


def test_un_registro_che_non_esiste_non_parte():
    house = CasaFinta(synthetic_inputs())

    answer = _run(house.read_registry("fantasmi"))

    assert answer.get("causa") == "richiesta", answer
    assert house.connections == []


def test_list_labels_non_c_e_piu():
    assert not hasattr(HAClient, "list_labels")


# ── il giro delle condizioni (A-02), e le integrazioni per evento (Task 7) ──

def _snapshot(rows) -> list[dict]:
    """L'elenco iniziale dell'iscrizione alle integrazioni, nella forma di Home
    Assistant (`config_entries_subscribe`, vedi `CONFIG_ENTRIES_SUBSCRIPTION`
    in `proxy/ha_client.py`)."""
    return [{"type": None, "entry": row} for row in rows]


def _conditions_app(tmp_path, house, *, problems=None, rebuilt=True, followed=True):
    store = HomeSpace(str(tmp_path))
    if rebuilt:
        _run(rebuild(house, store))
    house.calls.clear()
    house.connections.clear()
    app = {"watcher": _Observer(), "home_space_store": store}
    if problems is not None:
        app["ha_problems"] = problems
    if followed:
        integration_follower(app)(_snapshot(synthetic_inputs()["registries"]["integrazioni"]))
    return app


def test_il_giro_delle_condizioni_non_rilegge_i_problemi_ne_i_registri(tmp_path):
    """Misurato il 03/10/2026 sul codice di prima del Task 5, su questa casa: 4
    connessioni e 13 comandi (`repairs/list_issues`, i dieci dei registri --
    sei, piu' le categorie per quattro ambiti --, `get_entries` per gli alias,
    `system_log/list`). Il Task 5 li ha portati a 2 (integrazioni e registro
    di errori); dal Task 7 le integrazioni arrivano per evento
    (`config_entries/subscribe`), e il giro legge solo il registro di errori.

    Mutazione ESEGUITA (03/10/2026, Task 7): rimessa nel giro la lettura
    `read_registry("integrazioni")` -- rossa (`config_entries/get` fra i
    comandi, 2 connessioni)."""
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": [
        {"domain": "hue", "issue_id": "x"}]})

    written = _run(watch_system_conditions(app, house))

    assert _commands(house) == ["system_log/list"]
    assert len(house.connections) == 1
    assert written == 1 + 2
    assert app["watcher"].received[0]["problems"] == [{"domain": "hue", "issue_id": "x"}]
    assert app["watcher"].received[0]["integrations"] == \
        synthetic_inputs()["registries"]["integrazioni"]


def test_senza_problemi_in_memoria_li_legge_una_volta_e_li_lascia_li(tmp_path):
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house)

    _run(watch_system_conditions(app, house))

    assert _commands(house).count("repairs/list_issues") == 1
    assert app["ha_problems"] == {"problemi": []}


def test_i_problemi_in_memoria_non_letti_saltano_il_giro(tmp_path):
    """La stessa disciplina di prima («meglio un buco nella storia che una
    bugia nella storia»): un elenco dei problemi non letto non e' un elenco
    vuoto."""
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={
        "errore": "Home Assistant non ha risposto", "causa": "silenzio", "codice": None})

    assert _run(watch_system_conditions(app, house)) is None
    assert app["watcher"].received == []


def test_le_integrazioni_non_ancora_annunciate_saltano_il_giro(tmp_path):
    """Finche' l'iscrizione non ha mandato l'elenco iniziale le integrazioni
    non si sanno: un elenco vuoto chiuderebbe ogni integrazione gia' rotta
    come se si fosse appena risolta. E il giro non va a rileggerle da se':
    sarebbe la copia che il Task 7 ha tolto."""
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": []}, followed=False)

    assert _run(watch_system_conditions(app, house)) is None
    assert app["watcher"].received == []
    assert house.calls == []


def test_un_cambio_annunciato_arriva_all_anagrafe_senza_aspettare_un_giro(tmp_path):
    """Task 7, aggiunta di Paolo («avviso», 03/10/2026): lo stato di
    un'integrazione nell'anagrafe e' quello dell'ultimo annuncio di Home
    Assistant -- non vecchio fino a dieci minuti (A-11 col giro), ne' fino al
    prossimo evento di registro (prima del Task 5)."""
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": []})
    store = app["home_space_store"]
    assert {row["stato"] for row in store.read()["integrazioni"]} == {"loaded"}

    changed = {**synthetic_inputs()["registries"]["integrazioni"][0], "state": "setup_error"}
    integration_follower(app)([{"type": "updated", "entry": changed}])
    # Lo stesso ascoltatore che l'avvio iscrive: il suo stato e' l'anagrafe e
    # `app["ha_integrations"]`, non una memoria sua. Il secondo ascoltatore
    # qui sopra parte vuoto, e un cambio solo non e' l'elenco intero.
    states = {row["entry_id"]: row["stato"] for row in store.read()["integrazioni"]}
    assert states == {"voce_uno": "setup_error", "voce_due": "loaded"}
    assert house.calls == []


def test_l_elenco_iniziale_sostituisce_quello_di_prima(tmp_path):
    """Alla riconnessione l'iscrizione rimanda l'elenco intero: una voce
    tolta mentre la connessione era giu' sparisce, perche' l'elenco nuovo
    sostituisce il vecchio invece di sommarsi."""
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": []})
    follow = integration_follower(app)
    rows = synthetic_inputs()["registries"]["integrazioni"]
    follow(_snapshot(rows))

    follow(_snapshot(rows[1:]))

    assert [row["entry_id"] for row in app["ha_integrations"]] == ["voce_due"]
    assert [row["entry_id"] for row in app["home_space_store"].read()["integrazioni"]] == \
        ["voce_due"]


def test_una_voce_tolta_esce_e_una_aggiunta_entra(tmp_path):
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": [], }, followed=False)
    follow = integration_follower(app)
    rows = synthetic_inputs()["registries"]["integrazioni"]
    follow(_snapshot(rows))
    added = {**rows[0], "entry_id": "voce_tre", "domain": "marca_tre"}

    follow([{"type": "removed", "entry": rows[0]}])
    follow([{"type": "added", "entry": added}])

    assert [row["entry_id"] for row in app["ha_integrations"]] == ["voce_due", "voce_tre"]


def test_un_elenco_iniziale_vuoto_e_una_casa_senza_integrazioni(tmp_path):
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": []})

    integration_follower(app)([])

    assert app["ha_integrations"] == []
    assert app["home_space_store"].read()["integrazioni"] == []


def test_un_anagrafe_mai_letta_non_nasce_dalle_sole_integrazioni(tmp_path):
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, problems={"problemi": []}, rebuilt=False)

    _run(watch_system_conditions(app, house))

    assert app["home_space_store"].read() == {}
    assert app["home_space_store"].updated_at() is None


def test_le_integrazioni_tornate_escono_dai_non_disponibili(tmp_path):
    house = CasaFinta(synthetic_inputs(), silence={"config_entries/get"})
    store = HomeSpace(str(tmp_path))
    _run(rebuild(house, store))
    assert "integrazioni" in store.unavailable()

    store.hold_integrations(synthetic_inputs()["registries"]["integrazioni"])

    assert "integrazioni" not in store.unavailable()
    assert len(store.read()["integrazioni"]) == 2


def test_dal_websocket_all_anagrafe(tmp_path):
    """Il percorso intero, sul codice vero: il client si iscrive, la casa
    finta manda l'elenco iniziale e poi un cambio nella forma di Home
    Assistant, l'ascoltatore li porta all'anagrafe."""
    house = CasaFinta(synthetic_inputs())
    app = _conditions_app(tmp_path, house, followed=False)
    house.add_integration_listener(integration_follower(app))
    store = app["home_space_store"]
    changed = {**synthetic_inputs()["registries"]["integrazioni"][1], "state": "not_loaded"}

    async def scenario():
        await house.start_websocket()
        await asyncio.wait_for(house.ws_ready.wait(), 2)
        while "ha_integrations" not in app:
            await asyncio.sleep(0)
        house._session.push_config_entry_change("updated", changed)
        while store.read()["integrazioni"][1]["stato"] != "not_loaded":
            await asyncio.sleep(0)
        house._ws_task.cancel()

    _run(asyncio.wait_for(scenario(), 2))
    assert len(app["ha_integrations"]) == 2


# ── i due chiamanti che non usavano gli alias (A-01, A-06) ───────────────────

_USER = "utente_uno"
_PERSON = {"entity_id": "person.uno", "state": "home", "attributes": {
    "user_id": _USER, "device_trackers": ["device_tracker.telefono_uno"]}}


def _recipient_house():
    inputs = synthetic_inputs()
    inputs["states"] = inputs["states"] + [_PERSON]
    inputs["registries"]["entita"].append(
        {"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
         "device_id": "dev_telefono"})
    inputs["registries"]["dispositivi"].append(
        {"id": "dev_telefono", "name": "Telefono uno"})
    inputs["services"] = inputs["services"] + [
        {"domain": "notify", "services": {"mobile_app_telefono_uno": {}}}]
    return CasaFinta(inputs)


def test_il_recapito_legge_entita_e_dispositivi_e_basta():
    house = _recipient_house()

    found = _run(recipients_for({"specie": "persona", "id": _USER}, house,
                              ServiceRegistry()))

    assert found.services == ("notify.mobile_app_telefono_uno",), found
    registry_commands = [c for c in _commands(house) if c.startswith("config")]
    assert registry_commands == ["config/entity_registry/list",
                                 "config/device_registry/list"]


def test_il_recapito_senza_registro_delle_entita_non_legge_i_dispositivi():
    house = _recipient_house()
    house.mute("config/entity_registry/list")

    found = _run(recipients_for({"specie": "persona", "id": _USER}, house,
                              ServiceRegistry()))

    assert found.services == ()
    assert found.reason
    assert "config/device_registry/list" not in _commands(house)


def test_l_officina_legge_solo_il_registro_delle_entita():
    inputs = synthetic_inputs()
    inputs["registries"]["entita"].append(
        {"entity_id": "input_boolean.vacanza", "platform": "input_boolean",
         "unique_id": "vacanza_2"})
    house = CasaFinta(inputs)
    workshop = Workshop(house, None, None)

    found, missing = _run(workshop._helper_entities([("input_boolean", "vacanza_2")]))

    assert (found, missing) == (["input_boolean.vacanza"], [])
    assert _commands(house) == ["config/entity_registry/list"]


def test_l_officina_trova_l_etichetta_dal_registro_delle_etichette():
    inputs = synthetic_inputs()
    inputs["registries"]["etichette"] = [{"label_id": "hiris_1", "name": "HIRIS"}]
    house = CasaFinta(inputs)
    workshop = Workshop(house, None, None)

    assert _run(workshop._resolve_label()) is True
    assert workshop._label_id == "hiris_1"
    assert _commands(house) == ["config/label_registry/list"]


# ── un registro caduto non svuota la sua tabella (A-10, Task 7) ──────────────

def _with_alias() -> dict:
    inputs = synthetic_inputs()
    inputs["registries"]["entita"][0]["aliases"] = ["lampada della nonna"]
    return inputs


def _aliases(store) -> dict[str, list]:
    return {row["id"]: row["alias"] for row in store.read()["entita"] if row["alias"]}


def test_una_ricostruzione_senza_alias_tiene_gli_alias_della_precedente(tmp_path):
    """A-10, cambia comportamento (approvato nella tabella del piano): fino al
    03/10/2026 un `get_entries` caduto dava `entita:alias` fra i non
    disponibili e TUTTI gli alias sparivano dall'anagrafe -- «lampada della
    nonna» smetteva di trovare la lampada per un comando fallito. Adesso la
    tabella tiene cio' che la ricostruzione precedente sapeva, e resta
    marcata: `entita:alias` e' ancora fra i non disponibili.

    Mutazione ESEGUITA (03/10/2026): in `HomeSpace.hold_registries` tolta la
    ripresa dalla precedente -- rossa (gli alias vuoti)."""
    house = CasaFinta(_with_alias())
    store = HomeSpace(str(tmp_path))
    _run(rebuild(house, store))
    first = _aliases(store)
    assert first, "la prima ricostruzione non ha alias: la prova guarderebbe il vuoto"

    house.mute("config/entity_registry/get_entries")
    _run(rebuild(house, store))

    assert "entita:alias" in store.unavailable()
    assert _aliases(store) == first


def test_un_registro_caduto_tiene_la_tabella_della_precedente(tmp_path):
    house = CasaFinta(synthetic_inputs())
    store = HomeSpace(str(tmp_path))
    _run(rebuild(house, store))
    areas = store.read()["aree"]
    assert areas

    house.mute("config/area_registry/list")
    _run(rebuild(house, store))

    assert "aree" in store.unavailable()
    assert store.read()["aree"] == areas


class _ScopeFallsSilent(CasaFinta):
    """La casa finta in cui un AMBITO delle categorie tace: le categorie sono
    un comando per ambito, tutti con lo stesso nome, e `silence=` li farebbe
    tacere tutti."""

    silent_scope: str | None = None

    def _ws_reply(self, msg_type, extra):
        if (msg_type == "config/category_registry/list"
                and (extra or {}).get("scope") == self.silent_scope):
            return None
        return super()._ws_reply(msg_type, extra)


def test_un_ambito_di_categorie_caduto_tiene_le_sue_categorie(tmp_path):
    inputs = synthetic_inputs()
    inputs["registries"]["categorie"] = [
        {"category_id": "cat_luci", "name": "Luci", "ambito": "automation"},
        {"category_id": "cat_notte", "name": "Notte", "ambito": "script"}]
    house = _ScopeFallsSilent(inputs)
    store = HomeSpace(str(tmp_path))
    _run(rebuild(house, store))
    before = sorted(row["id"] for row in store.read()["categorie"])
    assert before == ["cat_luci", "cat_notte"]

    house.silent_scope = "automation"
    _run(rebuild(house, store))

    assert "categorie:automation" in store.unavailable()
    assert sorted(row["id"] for row in store.read()["categorie"]) == before


def test_la_prima_ricostruzione_non_ha_niente_da_riprendere(tmp_path):
    house = CasaFinta(_with_alias(), silence={"config/entity_registry/get_entries"})
    store = HomeSpace(str(tmp_path))
    _run(rebuild(house, store))

    assert "entita:alias" in store.unavailable()
    assert _aliases(store) == {}
