"""Lo specchio risponde per id (Tappa 2, Task 6: A-35, A-24, A-03, A-31, A-09; D4).

**Cosa difende.** Fino al 03/10/2026 lo specchio dello stato (`EntityCache`)
sapeva dire una cosa sola: «ecco tutte le righe» (`all_states()`). Chi voleva
UNA entita' se la cercava da se', scandendo l'elenco intero: l'id di
configurazione delle automazioni (`automation_config_id`), l'attuatore
(`ActionActuator._states`), gli strumenti della chat (`ToolDispatcher.
_state_readings`, copia riga per riga del precedente) e i nomi vivi della
pagina del cervello (`handlers_mind._entity_names`, copia dei nomi di
`topology.live_mirror`). Il comportamento rileggeva da Home Assistant l'intera
casa per tenerne le automazioni (`behavior.reread`, A-03). E lo specchio
rileggeva in due modi: `reload` proteggeva gli eventi arrivati durante la
lettura, `load` no (A-31); e una rilettura fallita dopo il primo caricamento
non la riprovava nessuno (A-09).

**Le prove usano lo specchio vero**, con una spia che fa sollevare
`all_states()`: chi risponde lo stesso non scandisce. E la casa e' quella
finta col client vero (`scripts/casa_finta.py::CasaFinta`), non una finta
scritta qui.

Rosso letto il 03/10/2026, sul codice di prima (`2357fc9`): le tre risposte
per id cadono sulla scansione (`automation_config_id` solleva la spia;
l'attuatore risponde «non vedo lo stato di questa casa»; la promessa
«chiedi» si rifiuta allo stesso modo); l'evento arrivato durante `load` si
perde (lo specchio dice `off`); il giro dei due minuti non riprova dopo una
rilettura fallita (`False`); il cancello trova tre funzioni che scandiscono per
id (e, sulle copie di prima, anche la vecchia `automation_config_id`). La prova
del comportamento era rossa per la firma nuova: la sua ragione l'ha data la
mutazione qui sotto.

Mutazioni ESEGUITE (03/10/2026), ognuna ripristinata e verificata con `cmp`:

- `automation_config_id` torna a cercare la riga scandendo `all_states()` --
  rossa (la spia: «ha scandito tutto lo specchio»);
- la rilettura unica non riapplica il tampone -- rosse questa prova sul primo
  caricamento (`'on' == 'off'`) e le due di `test_entity_cache.py` sulla
  rilettura;
- rimesso in `ActionActuator` il vecchio `_states` -- rosso il cancello;
- `behavior.reread` torna a chiedere `get_states([])` -- rosse la prova del
  comportamento (`/api/states` chiesto) e `test_costi_avvio.py` (`get_states`
  4, tetto 2);
- `reload_entity_inventory` torna a guardare solo `loaded` -- rossa la prova
  del giro dei due minuti (`False`);
- `user_id` in coda al motivo `_REASON_NO_ACTIVE_NOTIFY` -- rosse le due prove
  di D4 (`senza_notify` e lo strumento della chat).
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
from datetime import UTC, datetime, timedelta

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

from hiris.app.action.actuator import _BLIND_MIRROR, ActionActuator
from hiris.app.action.registry import ServiceRegistry
from hiris.app.chat_thread import ChatThread
from hiris.app.home_space.behavior import reread
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.keeper.recipient import _REASON_NO_ACTIVE_NOTIFY, recipients_for
from hiris.app.keeper.store import AgendaStore
from hiris.app.proxy.entity_cache import EntityCache, automation_config_id
from hiris.app.server import reload_entity_inventory
from tests._casa_sintetica import synthetic_inputs


def _in_an_hour() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat()


class _SpyMirror(EntityCache):
    """Lo specchio vero, che si rifiuta di essere scandito."""

    def all_states(self):
        raise AssertionError("ha scandito tutto lo specchio per cercare un id")


async def _loaded_spy(inputs: dict | None = None) -> _SpyMirror:
    spy = _SpyMirror()
    await spy.load(CasaFinta(inputs or synthetic_inputs()))
    return spy


# ── A-35, A-24: una entita' si chiede per id ────────────────────────────────

@pytest.mark.asyncio
async def test_automation_config_id_does_not_scan_the_mirror():
    spy = await _loaded_spy()
    assert automation_config_id(spy, "automation.automazione_uno") == "auto_uno"
    assert automation_config_id(spy, "automation.mai_vista") is None


@pytest.mark.asyncio
async def test_the_actuator_sees_the_mirror_without_scanning_it():
    """Un'entita' che non c'e', su uno specchio pieno: il rifiuto e' «non
    esiste», non «non vedo la casa». Con la scansione la spia solleva,
    l'attuatore lo prende per uno specchio illeggibile e dice la frase
    sbagliata."""
    house = CasaFinta(synthetic_inputs())
    actuator = ActionActuator(house, ServiceRegistry(), await _loaded_spy())
    outcome = await actuator.execute(
        {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.non_esiste"]}},
        actor="prova")
    assert outcome["eseguito"] is False
    assert outcome["errore"] != _BLIND_MIRROR
    assert "light.non_esiste" in outcome["errore"]


@pytest.mark.asyncio
async def test_a_chat_promise_takes_its_snapshot_without_scanning(tmp_path):
    """Lo strumento della chat: la promessa «chiedi» verifica i riferimenti e
    prende l'istantanea dallo specchio, per id."""
    agenda = AgendaStore(str(tmp_path / "promesse.db"))
    try:
        dispatcher = ToolDispatcher(None, None, agenda=agenda,
                                    thread=ChatThread("persona:paolo", "pannello"),
                                    cache=await _loaded_spy())
        outcome = await dispatcher.dispatch("promise", {
            "specie": "chiedi", "frase": "verifica la temperatura",
            "quando": _in_an_hour(), "domanda": "e' salita?",
            "da_confrontare": ["sensor.sensore_a_temperatura"]})
    finally:
        agenda.close()
    assert "errore" not in outcome, outcome
    snapshot = outcome["promessa"]["istantanea"]
    assert [(m["entita"], m["valore"], m["unita"]) for m in snapshot] == [
        ("sensor.sensore_a_temperatura", "21.5", "°C")]


def test_the_mirror_answers_by_id():
    mirror = EntityCache()
    assert mirror.get("light.luce_uno") is None
    assert mirror.states_for() == {}
    for raw in synthetic_inputs()["states"]:
        mirror.on_state_changed({"entity_id": raw["entity_id"], "new_state": raw})
    assert mirror.get("light.luce_uno")["state"] == "on"
    assert mirror.get("light.non_esiste") is None
    assert set(mirror.states_for(["light.luce_uno", "light.non_esiste"])) == {
        "light.luce_uno"}
    assert len(mirror.states_for()) == len(synthetic_inputs()["states"])
    # Una COPIA: l'attuatore confronta il «prima» con il «dopo», e un «prima»
    # che cambiasse sotto i suoi occhi direbbe che non e' successo niente.
    before = mirror.states_for()
    mirror.on_state_changed({"entity_id": "light.luce_uno", "new_state": {
        "entity_id": "light.luce_uno", "state": "off", "attributes": {}}})
    assert before["light.luce_uno"]["state"] == "on"


# ── A-31: una rilettura sola, che non perde gli eventi ──────────────────────

def _event(entity_id: str, state: str) -> dict:
    return {"entity_id": entity_id,
            "new_state": {"entity_id": entity_id, "state": state, "attributes": {}}}


@pytest.mark.asyncio
async def test_an_event_arriving_during_the_first_load_is_not_lost():
    """L'evento arriva MENTRE Home Assistant risponde alla lettura intera: la
    risposta e' la fotografia di prima (luce accesa), l'evento la spegne. Lo
    stato finale e' l'evento. Il `load` di prima riempiva lo specchio dalla
    fotografia dopo l'evento e lo cancellava."""
    mirror = EntityCache()
    inputs = synthetic_inputs()

    def _states_while_an_event_arrives(path):
        mirror.on_state_changed(_event("light.luce_uno", "off"))
        return inputs["states"]

    await mirror.load(CasaFinta(inputs, answers={"/api/states":
                                                 _states_while_an_event_arrives}))
    assert mirror.get("light.luce_uno")["state"] == "off"
    assert mirror.loaded


@pytest.mark.asyncio
async def test_the_first_load_still_raises_when_home_assistant_is_down():
    from hiris.app.proxy.ha_client import HAReadError
    mirror = EntityCache()
    with pytest.raises(HAReadError):
        await mirror.load(CasaFinta(synthetic_inputs(), refuse={"/api/states": 500}))
    assert not mirror.loaded


# ── A-09: una rilettura fallita si riprova ──────────────────────────────────

@pytest.mark.asyncio
async def test_a_failed_reread_is_retried_by_the_two_minute_round():
    """Lo specchio e' caricato; Home Assistant si riavvia e la rilettura della
    riconnessione fallisce: lo specchio resta quello di prima, dichiarato
    vecchio. Il giro dei due minuti lo rilegge appena la casa risponde."""
    mirror = EntityCache()
    await mirror.load(CasaFinta(synthetic_inputs()))
    assert not mirror.stale

    await mirror.reload(CasaFinta(synthetic_inputs(), refuse={"/api/states": 500}))
    assert mirror.loaded and mirror.stale

    after_restart = synthetic_inputs()
    after_restart["states"] = [dict(raw, state="off") if raw["entity_id"] == "light.luce_uno"
                               else raw for raw in after_restart["states"]]
    assert await reload_entity_inventory(mirror, CasaFinta(after_restart)) is True
    assert mirror.get("light.luce_uno")["state"] == "off"
    assert not mirror.stale

    # Uno specchio fresco non si rilegge: il giro torna a essere il
    # controllo di una bandiera.
    untouched = CasaFinta(synthetic_inputs())
    assert await reload_entity_inventory(mirror, untouched) is False
    assert untouched.calls == []


# ── A-03: il comportamento legge lo specchio ────────────────────────────────

@pytest.mark.asyncio
async def test_behavior_reads_the_mirror_not_the_whole_house(tmp_path):
    house = CasaFinta(synthetic_inputs())
    mirror = EntityCache()
    await mirror.load(house)
    before = len(house.calls)
    home_space = HomeSpace(str(tmp_path))
    try:
        outcome = await reread(house, mirror, home_space, None)
        entries = home_space.behavior()
    finally:
        home_space.close()
    asked = [name for name, _extra in house.calls[before:]]
    assert "/api/states" not in asked
    assert asked == ["automation/config"]
    assert [(e["id"], e["tipo"], e["nome"], e.get("attiva")) for e in entries] == [
        ("automation.automazione_uno", "automazione", "Automazione uno", True)]
    assert outcome["conteggi"] == {"automazione": 1}


@pytest.mark.asyncio
async def test_behavior_does_not_read_a_mirror_that_is_not_ready(tmp_path):
    """Uno specchio mai caricato non e' una casa senza automazioni: la
    rilettura si ferma e la replica resta quella di prima."""
    home_space = HomeSpace(str(tmp_path))
    try:
        with pytest.raises(RuntimeError):
            await reread(CasaFinta(synthetic_inputs()), EntityCache(), home_space, None)
    finally:
        home_space.close()


# ── D4: cio' che il recapito legge non arriva ai modelli ────────────────────

USER_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
TRACKER = "device_tracker.telefono_di_prova"


def _house_with_one_person(*, notify: bool = True, mobile_app: bool = True,
                         linked: bool = True, twice: bool = False) -> CasaFinta:
    inputs = synthetic_inputs()
    person = {"entity_id": "person.prova", "state": "home",
              "attributes": {"friendly_name": "Prova", "id": "prova",
                             "user_id": USER_ID if linked else "altro",
                             "device_trackers": [TRACKER]}}
    inputs["states"] = inputs["states"] + [person] + (
        [dict(person, entity_id="person.copia")] if twice else [])
    inputs["registries"]["entita"].append({
        "entity_id": TRACKER, "platform": "mobile_app" if mobile_app else "gps",
        "name": None, "original_name": "Telefono", "area_id": None,
        "device_id": "dev_telefono", "entity_category": None, "disabled_by": None,
        "hidden_by": None, "labels": [], "categories": {}})
    inputs["registries"]["dispositivi"].append(
        {"id": "dev_telefono", "name": "Telefono di prova", "area_id": None})
    if notify:
        inputs["services"] = inputs["services"] + [{"domain": "notify", "services": {
            "mobile_app_telefono_di_prova": {"name": "Send", "fields": {}}}}]
    return CasaFinta(inputs)


def _leaks(text: str) -> list[str]:
    return [secret for secret in (USER_ID, "device_tracker.") if secret in text]


@pytest.mark.parametrize("house_kwargs", [
    {}, {"notify": False}, {"mobile_app": False}, {"linked": False}, {"twice": True}],
    ids=["recapito", "senza_notify", "senza_app", "non_collegata", "due_persone"])
@pytest.mark.asyncio
async def test_the_recipient_does_not_hand_personal_data_to_the_models(house_kwargs):
    """La condizione di Paolo su D4 (03/10/2026): il recapito resta su
    `get_states([])` solo se `user_id` e i tracker non arrivano ai modelli.
    Ogni uscita di `recipients_for`, sulla casa finta che li porta.

    Mutazione ESEGUITA (03/10/2026): `_REASON_NO_ACTIVE_NOTIFY + user_id` come
    motivo -- rossa su `senza_notify` e sulla prova dello strumento qui sotto."""
    found = await recipients_for({"specie": "persona", "id": USER_ID},
                                 _house_with_one_person(**house_kwargs),
                                 ServiceRegistry())
    text = json.dumps([found.services, found.reason], ensure_ascii=False)
    assert not _leaks(text), text
    if not house_kwargs:
        assert found.services == ("notify.mobile_app_telefono_di_prova",)


@pytest.mark.asyncio
async def test_the_chat_tool_does_not_hand_personal_data_to_the_models(tmp_path):
    agenda = AgendaStore(str(tmp_path / "promesse.db"))
    try:
        # Il registro dei servizi c'e', come nell'app: senza, il recapito si
        # fermerebbe prima di leggere la persona (A-04), e la prova non
        # guarderebbe piu' la strada che porta `user_id` e tracker.
        dispatcher = ToolDispatcher(None, None, agenda=agenda,
                                    thread=ChatThread("persona:paolo", "pannello"),
                                    ha=_house_with_one_person(notify=False),
                                    registry=ServiceRegistry(),
                                    subject={"specie": "persona", "id": USER_ID})
        outcome = await dispatcher.dispatch("promise", {
            "specie": "chiedi", "frase": "ricordamelo",
            "quando": _in_an_hour(), "domanda": "fatto?"})
    finally:
        agenda.close()
    assert "avviso" in outcome, outcome
    assert outcome["avviso"].endswith(_REASON_NO_ACTIVE_NOTIFY), outcome
    text = json.dumps(outcome, ensure_ascii=False)
    assert not _leaks(text), text


# ── Il cancello: fuori dallo specchio nessuno lo scandisce per un id ─────────

MIRROR_MODULE = "proxy/entity_cache.py"


def _id_read_on(node: ast.AST) -> str | None:
    """Il nome della riga di cui si legge l'`id` -- `riga.get("id")` o
    `riga["id"]`, la chiave per id delle righe dello specchio (`_to_minimal`)
    -- o `None`."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == "id"
            and isinstance(node.func.value, ast.Name)):
        return node.func.value.id
    if (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
            and node.slice.value == "id" and isinstance(node.value, ast.Name)):
        return node.value.id
    return None


def _is_the_id(node: ast.AST) -> bool:
    """L'id di una riga, anche passato da `str()`: la chiave stessa, non un
    valore che se ne ricava (il dominio, per dirne uno)."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "str" and len(node.args) == 1):
        node = node.args[0]
    return _id_read_on(node) is not None


def _looks_up_by_id(nodes: list[ast.AST]) -> bool:
    """Le tre forme di «cercare per id» fra le righe:

    - un CONFRONTO con l'id di una riga (`riga.get("id") == cercato`, `in`);
    - una mappa per comprensione con l'id come CHIAVE (`{r.get("id"): r ...}`);
    - una mappa riempita a mano con la RIGA come valore, sotto una chiave
      qualunque, in una funzione che dell'id di quella riga si serve
      (`eid = r.get("id"); stati[eid] = r`).

    Usare l'id per altro -- il dominio di una riga, l'elenco degli id da
    chiedere a Home Assistant -- non e' cercare un'entita'."""
    rows_with_id_read = {name for node in nodes if (name := _id_read_on(node))}
    for node in nodes:
        if isinstance(node, ast.Compare) and any(
                _is_the_id(side) for side in [node.left, *node.comparators]):
            return True
        if isinstance(node, ast.DictComp) and _is_the_id(node.key):
            return True
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Name)
                and node.value.id in rows_with_id_read
                and any(isinstance(target, ast.Subscript) for target in node.targets)):
            return True
    return False


def _reaches_all_states(node: ast.AST) -> bool:
    """`specchio.all_states` -- chiamato o preso come riferimento -- o
    `getattr(specchio, "all_states")`: la vecchia `automation_config_id` lo
    prendeva cosi'."""
    if isinstance(node, ast.Attribute) and node.attr == "all_states":
        return True
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "getattr" and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "all_states")


def mirror_scans(sources: dict[str, ast.AST]) -> tuple[set[str], set[str]]:
    """`(chi legge tutto lo specchio, chi lo scandisce per un id)`, per
    funzione: `file::funzione`.

    La proprieta', non la forma: una funzione che chiama `all_states()` e,
    nello stesso corpo, cerca una riga per id o se ne costruisce la mappa
    (`_looks_up_by_id`) fa cio' che lo specchio sa fare da se'
    (`EntityCache.get`, `states_for`). Chi legge tutto lo specchio per
    guardare la casa intera -- la ricerca, il conteggio, `live_mirror`, il
    comportamento che ne tiene le automazioni -- non e' una scansione per
    id."""
    readers: set[str] = set()
    scanners: set[str] = set()
    for relative, tree in sources.items():
        if relative == MIRROR_MODULE:
            continue
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            nodes = list(ast.walk(function))
            if not any(_reaches_all_states(node) for node in nodes):
                continue
            name = f"{relative}::{function.name}"
            readers.add(name)
            if _looks_up_by_id(nodes):
                scanners.add(name)
    return readers, scanners


def _product() -> dict[str, ast.AST]:
    return {path.relative_to(APP).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
            for path in sorted(APP.rglob("*.py"))}


def test_nobody_outside_the_mirror_scans_it_for_an_id():
    """Mutazione ESEGUITA (03/10/2026): rimesso in `ActionActuator` il vecchio
    `_states` che costruisce la mappa da `all_states()` -- rossa
    (`action/actuator.py::_states`)."""
    _readers, scanners = mirror_scans(_product())
    assert not scanners, (
        "scandiscono lo specchio per un id invece di chiederlo "
        f"(`EntityCache.get`, `states_for`): {sorted(scanners)}")


def test_the_derivation_still_sees_the_readers_of_the_mirror():
    """La derivazione non si e' svuotata: chi legge tutto lo specchio c'e'
    ancora (la ricerca, le pagine, il conteggio d'avvio), e una scansione per
    id scritta apposta si vede."""
    readers, _scanners = mirror_scans(_product())
    assert len(readers) >= 4, sorted(readers)
    _readers, planted = mirror_scans({f"mind/prova_{n}.py": ast.parse(source)
                                      for n, source in enumerate(_PLANTED_SCANS)})
    assert planted == {f"mind/prova_{n}.py::f" for n in range(len(_PLANTED_SCANS))}
    _readers, innocent = mirror_scans({"mind/prova.py": ast.parse(
        "def f(cache):\n"
        "    return [s['id'] for s in cache.all_states() if s.get('domain') == 'light']\n")})
    assert innocent == set()


#: Le tre forme che il cancello deve vedere: quelle delle copie che sono uscite
#: il 03/10/2026 (`automation_config_id`, `_entity_names`, `_states` e
#: `_state_readings`).
_PLANTED_SCANS = (
    ("def f(cache, eid):\n"
     "    for s in cache.all_states():\n"
     "        if s.get('id') == eid:\n"
     "            return s\n"),
    ("def f(cache):\n"
     "    return {str(s.get('id')): s.get('name') for s in cache.all_states()}\n"),
    ("def f(cache):\n"
     "    states = {}\n"
     "    for entry in cache.all_states():\n"
     "        eid = entry.get('id')\n"
     "        if eid:\n"
     "            states[eid] = entry\n"
     "    return states\n"),
)


def test_the_by_id_base_of_the_fake_mirrors_has_the_real_signatures():
    """Le finte dello specchio delle prove rispondono per id da
    `tests/_mirror_by_id.py`: con le firme dello specchio vero, o una finta
    accetterebbe domande che il vero rifiuta."""
    import inspect

    from tests._mirror_by_id import MirrorById
    for name in ("get", "states_for"):
        assert (inspect.signature(getattr(MirrorById, name))
                == inspect.signature(getattr(EntityCache, name))), name
