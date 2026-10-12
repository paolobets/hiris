"""R9: ogni nome che una descrizione mette fra backtick esiste nella risposta
(Tappa 9, F8; Tappa 5, Task 7).

La descrizione di uno strumento e' cio' che il modello legge per sapere come
leggere la risposta. Un nome fra backtick che la risposta non porta e' una
istruzione falsa detta con sicurezza: X-33 (`related` diceva «`related` e' un
dizionario», la chiave e' `legami`), X-16 (`tipo` dove la riga porta
`genere`), X-34 (`run_id` dove la riga lo porta sotto `esecuzione`).

**Il catalogo dei nomi resi si chiede facendo girare lo strumento**, non si
ricopia: l'app vera si avvia sulla casa sintetica
(`fotografia_porte.mounted`), il dispatcher e' quello del prodotto
(`create_tool_dispatcher`), e ogni strumento risponde a un giro di chiamate.
Le chiavi e i valori di testo di tutte le risposte sono cio' che lo strumento
rende. Un nome fra backtick e' in regola quando e':

- un parametro o un valore di `enum` del suo schema (a qualunque profondita');
- il nome di un ALTRO strumento -- il proprio no: nella propria descrizione
  e' una chiave (X-33 era esattamente questo);
- una chiave o un valore di testo che lo strumento ha reso; `chiave: valore`
  quando quella chiave e' uscita con quel valore;
- oppure e' ammesso in `ADMITTED`, con la ragione.

`ADMITTED` e' una lista di AMMISSIONE (CLAUDE.md, I-0): chiude per difetto, e
una voce nuova si scrive con la sua ragione. Puo' solo scendere.
"""
from __future__ import annotations

import contextlib
import copy
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte
from casa_finta import CasaFinta, Refused

from hiris.app.api import handlers_chat
from hiris.app.api.soffitto import consente
from hiris.app.chat_thread import ChatThread
from hiris.app.home_space.house import House
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
from hiris.app.home_space.topology import Mirror
from hiris.app.proxy import ha_client
from tests._casa_sintetica import synthetic_inputs
from tests.test_history_tool import _HISTORY_PATH, _RUN, _ha_history, _traccia
from tests.test_knowledge_tools import _raw_timed_event

_BACKTICK = re.compile(r"`([^`]+)`")
_PAIR = re.compile(r"^(\w+): (.+)$")


def descriptions(node) -> list[str]:
    """Ogni `description` di una definizione, a qualunque profondita'."""
    if isinstance(node, dict):
        return [text for key, value in node.items()
                for text in ([value] if key == "description" and isinstance(value, str)
                             else descriptions(value))]
    if isinstance(node, list):
        return [text for item in node for text in descriptions(item)]
    return []


def schema_words(node) -> set[str]:
    """I parametri e i valori di `enum` di uno schema, a qualunque profondita'."""
    words: set[str] = set()
    if isinstance(node, dict):
        words |= set(node.get("properties") or {})
        words |= {str(value) for value in node.get("enum") or ()}
        for value in node.values():
            words |= schema_words(value)
    elif isinstance(node, list):
        for item in node:
            words |= schema_words(item)
    return words


def backticked(definition: dict) -> set[str]:
    return {word for text in descriptions(definition) for word in _BACKTICK.findall(text)}


class Rendered:
    """Cio' che uno strumento ha reso: chiavi, valori di testo, e per ogni
    chiave i valori con cui e' uscita."""

    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.texts: set[str] = set()
        self.values: dict[str, set[str]] = {}

    def add(self, node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                self.keys.add(str(key))
                self.values.setdefault(str(key), set()).update(
                    {json.dumps(value, ensure_ascii=False), str(value).lower()
                     if isinstance(value, bool) else str(value)})
                self.add(value)
        elif isinstance(node, list):
            for item in node:
                self.add(item)
        elif isinstance(node, str):
            self.texts.add(node)

    def says(self, word: str) -> bool:
        pair = _PAIR.match(word)
        if pair:
            key, value = pair.groups()
            return value in self.values.get(key, ())
        return word in self.keys or word in self.texts


#: Le parole di Home Assistant: valori e sintassi che il modello scrive o
#: legge cosi' come Home Assistant li scrive, e che nessuna risposta di HIRIS
#: rende come chiave.
_HA_WORDS = {
    "home": "lo stato di una persona in casa, la parola di Home Assistant",
    "not_home": "lo stato di una persona fuori casa, la parola di Home Assistant",
    "sensor": "un dominio di Home Assistant, come esempio di id",
    "!include": "la direttiva YAML di Home Assistant",
    "brightness_pct": "un parametro di servizio di Home Assistant, come esempio di `dati`",
    "label_id": "il nome che Home Assistant da' all'id di un'etichetta",
    "trigger:": "la chiave YAML di Home Assistant dentro una voce di `innesco`",
    "action:": "la chiave YAML di Home Assistant dentro una voce di `azioni`",
    "entity_id": "la chiave di Home Assistant in una voce di `stati`",
    "fields": "la chiave di Home Assistant dei parametri di uno script",
}

#: Lista di AMMISSIONE: `{strumento: {parola: ragione}}`. Puo' solo scendere.
ADMITTED: dict[str, dict[str, str]] = {
    "search": {word: _HA_WORDS[word] for word in ("home", "not_home", "sensor")},
    "related": {"!include": _HA_WORDS["!include"]},
    "execute": {word: _HA_WORDS[word] for word in ("brightness_pct", "label_id")},
    "propose": {**{word: _HA_WORDS[word]
                   for word in ("trigger:", "action:", "entity_id", "fields")},
                "dati": "la chiave di una voce di `helper`, che lo schema dichiara "
                        "solo come oggetto"},
    "history": {"home": _HA_WORDS["home"], "not_home": _HA_WORDS["not_home"],
                "<secret nome>": "la forma del sigillo dentro un messaggio, non una "
                                 "chiave: a freddo `secrets.yaml` non c'e'"},
}


def _definition(name: str) -> dict:
    return next(tool for tool in KNOWLEDGE_TOOLS if tool["name"] == name)


def named_tools(name: str) -> set[str]:
    """Gli ALTRI strumenti che la descrizione nomina, fra backtick o fra «»:
    di loro parla, e i loro nomi valgono anche qui."""
    texts = " ".join(descriptions(_definition(name)))
    return {tool["name"] for tool in KNOWLEDGE_TOOLS
            if tool["name"] != name
            and (f"`{tool['name']}`" in texts or f"«{tool['name']}»" in texts)}


def unaccounted(name: str, rendered: dict[str, Rendered]) -> list[str]:
    """Le parole fra backtick della descrizione di `name` che non sono in
    regola (vedi il docstring del modulo)."""
    others = {tool["name"] for tool in KNOWLEDGE_TOOLS} - {name}
    speakers = [name, *sorted(named_tools(name))]
    allowed = set().union(*(schema_words(_definition(tool)["input_schema"])
                            for tool in speakers))
    admitted = ADMITTED.get(name, {})
    out = []
    for word in sorted(backticked(_definition(name))):
        if word in allowed or word in others or word in admitted:
            continue
        if any(rendered[tool].says(word) for tool in speakers):
            continue
        out.append(word)
    return out


# -- la casa e i giri ---------------------------------------------------------

_PERSON = {"specie": "persona", "id": "u-admin"}
_NOW = datetime.now(UTC)


def _ago(hours: float) -> str:
    return (_NOW - timedelta(hours=hours)).isoformat()


def _ms(hours: float) -> int:
    return int((_NOW - timedelta(hours=hours)).timestamp() * 1000)


#: La scena del giro: le risposte della casa la leggono per guastarsi.
_SCENE = {"guasta": False}


def _calendars(path):
    if urlsplit(path).path == "/api/calendars":
        return [{"name": "Famiglia", "entity_id": "calendar.famiglia"}]
    if _SCENE["guasta"]:
        return Refused(500)
    start = _NOW + timedelta(days=1)
    return [_raw_timed_event(f"Visita {n}", (start + timedelta(hours=n)).isoformat(),
                             (start + timedelta(hours=n + 1)).isoformat(),
                             description="controllo", location="studio")
            for n in range(3)]


def _traces(extra):
    if _SCENE["guasta"]:
        return Refused("unknown_error", "tracce non lette")
    return [_traccia("run-1"), _traccia("run-2", ore=2, error="boom")]


def _house(inputs):
    #: La configurazione scritta: Home Assistant la rilegge per chiave.
    written: dict[str, dict] = {}

    def _write_config(path, body):
        written[path.split("?", 1)[0]] = body
        return {"result": "ok"}

    #: Il contatore registrato da tre ore: la finestra predefinita (24 ore)
    #: comincia prima, e la riga lo dice con `dal`.
    series = {"sensor.contatore_uno": [{"quando": _ago(3), "valore": "1530"},
                                       {"quando": _ago(2), "valore": "unavailable"},
                                       {"quando": _ago(1), "valore": "1532.4"}],
              "light.luce_uno": [{"quando": _ago(3), "valore": "off"},
                                 {"quando": _ago(1), "valore": "on"}]}
    bands = {"sensor.contatore_uno": [
        {"start": _ms(30), "end": _ms(29), "state": 1531.0, "sum": 79.8, "change": 0.4},
        {"start": _ms(29), "end": _ms(28), "state": 1532.4, "sum": 80.2, "change": 1.4}]}
    answers = {
        "search/related": lambda extra: {"automation": ["automation.automazione_uno"],
                                         "area": ["stanza_uno"]},
        "POST /api/services/": lambda path, body: [],
        _HISTORY_PATH: _ha_history(series),
        "recorder/statistics_during_period": lambda extra: {
            i: bands[i] for i in extra["statistic_ids"] if i in bands},
        "trace/list": _traces,
        "trace/get": lambda extra: copy.deepcopy(_RUN),
        "/api/calendars": _calendars,
        "extract_from_target": lambda extra: {
            "referenced_entities": ["light.luce_uno", "sensor.sensore_a_temperatura"],
            "referenced_devices": [], "referenced_areas": ["stanza_uno"],
            "missing_devices": [], "missing_areas": [], "missing_floors": [],
            "missing_labels": []},
        "validate_config": lambda extra: {key: {"valid": True, "error": None}
                                          for key in ("triggers", "conditions", "actions")
                                          if key in extra},
        "POST /api/config/": _write_config,
        "/api/config/": lambda path: written.get(path.split("?", 1)[0],
                                                 Refused(404, "Resource not found")),
    }
    # Un contatore che riparte a ogni ciclo (`total` con `last_reset`): i
    # suoi cambi non dicono quando riparte, e il consumato non si calcola.
    inputs["registries"]["entita"].append(
        {**inputs["registries"]["entita"][6], "entity_id": "sensor.ciclo_uno",
         "original_name": "Ciclo"})
    inputs["states"].append(
        {"entity_id": "sensor.ciclo_uno", "state": "3.1",
         "attributes": {"friendly_name": "Ciclo", "unit_of_measurement": "kWh",
                        "device_class": "energy", "state_class": "total",
                        "last_reset": _ago(30)},
         "last_changed": _ago(1), "last_updated": _ago(1)})
    series["sensor.ciclo_uno"] = [{"quando": _ago(3), "valore": "2.0"},
                                  {"quando": _ago(1), "valore": "3.1"}]
    inputs["system_log"]["voci"] = [
        {"level": "ERROR", "message": ["zigbee giu'"], "name": "zha", "source": ["zha.py", 1],
         "count": 3, "first_occurred": _NOW.timestamp() - 3600 * 200,
         "timestamp": _NOW.timestamp() - 600}]

    def build(base_url=None, token=None):
        return CasaFinta(inputs, answers=answers)
    return build


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def mounted_app(tmp_path_factory):
    inputs = synthetic_inputs()
    data_dir = str(tmp_path_factory.mktemp("r9"))
    async with fotografia_porte.mounted(inputs, data_dir, _house(inputs)) as app:
        # Un atto di HIRIS nell'istante in cui la luce si e' accesa: la storia
        # lo abbina (`per_mano_di`).
        app["journal"].log(actor="chat", service="light.turn_on", entity=["light.luce_uno"],
                           executed=True, now=_NOW.timestamp() - 3600)
        yield app


def _dispatcher(app, house=None, exchange="giro-1"):
    return handlers_chat.create_tool_dispatcher(
        app, exchange=exchange, soffitto=consente(_PERSON, ruolo="amministratore"),
        soggetto=_PERSON, frase="si', procedi",
        thread=ChatThread("persona:u-admin", "pannello"), house=house)


@contextlib.contextmanager
def _healthy(app):
    """La casa dell'avvio, intera."""
    yield _dispatcher(app)


@contextlib.contextmanager
def _bodies_read(app):
    """La casa dell'avvio con ogni corpo letto: a freddo i corpi non si
    archiviano (manca `secrets.yaml`), e un corpo non letto e' un guasto di
    adesso che spegne `nulla_riconosciuto` (`ToolDispatcher._blind_spots`)."""
    store = app["home_space_store"]
    with mock.patch.object(store, "unread_bodies", return_value={}):
        yield _dispatcher(app)


@contextlib.contextmanager
def _next_turn(app):
    """Il turno dopo: `confirm` non applica una proposta nata nello stesso."""
    yield _dispatcher(app, exchange="giro-2")


@contextlib.contextmanager
def _few_events(app):
    """Un calendario con piu' eventi di quanti il client ne tiene."""
    with mock.patch.object(ha_client, "MAX_CALENDAR_EVENTS", 2):
        yield _dispatcher(app)


@contextlib.contextmanager
def _broken(app):
    """La casa che non si e' potuta guardare: registri di aree e piani
    caduti, specchio illeggibile, cronaca illeggibile, tracce e calendari
    che non rispondono."""
    store = app["home_space_store"]
    house = House(store.read(), Mirror({}, readable=False), unavailable=("aree", "piani"))
    _SCENE["guasta"] = True
    try:
        with mock.patch.object(app["journal"], "list", side_effect=OSError("disco")):
            yield _dispatcher(app, house)
    finally:
        _SCENE["guasta"] = False


#: I giri: per strumento, le chiamate che fanno uscire le forme che la sua
#: descrizione nomina -- la riuscita, il rifiuto, il taglio, il vuoto, il
#: guasto -- ognuna nella sua scena.
CALLS: dict[str, list[tuple[dict, Callable]]] = {
    "search": [({}, _healthy), ({"limite": 1}, _healthy), ({"salta": 1000}, _healthy),
               ({"riferimento": "light.luce_uno"}, _healthy),
               ({"riferimento": "light.non_c_e"}, _healthy),
               ({"genere": "area", "riferimento": "stanza_uno"}, _healthy),
               ({"includi_nascoste": True, "includi_servizio": True}, _healthy),
               ({"genere": "area", "classe": "door"}, _healthy),
               ({"nome": "zzz inesistente"}, _bodies_read),
               ({"nome": "zzz inesistente"}, _broken)],
    "related": [({"genere": "entita", "riferimento": "light.luce_uno"}, _healthy),
                ({"genere": "nessuno", "riferimento": "x"}, _healthy)],
    "remember": [({"testo": "La luce uno e' quella sopra il tavolo",
                   "ancore": [{"tipo": "entita", "riferimento": "light.luce_uno"}]},
                  _healthy)],
    "execute": [({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.luce_uno"]}}, _healthy),
                ({"servizio": "light.turn_on",
                  "bersaglio": {"aree": ["stanza_uno"]}}, _healthy)],
    "promise": [({"specie": "fai", "frase": "fra un'ora accendi la luce uno",
                  "quando": (_NOW + timedelta(hours=1)).isoformat(),
                  "chiamata": {"servizio": "light.turn_on",
                               "bersaglio": {"entita": ["light.luce_uno"]}}}, _healthy),
                ({"specie": "chiedi", "frase": "fra un'ora dimmi se fa piu' caldo",
                  "quando": (_NOW + timedelta(hours=1)).isoformat(),
                  "domanda": "la temperatura e' salita?",
                  "da_confrontare": ["sensor.sensore_a_temperatura"]}, _healthy)],
    "agenda": [({}, _healthy)],
    "cancel": [({"id": "nessuna"}, _healthy)],
    "propose": [({"gesto": "crea", "dominio": "automation", "alias": "Luce alla porta",
                  "innesco": [{"trigger": "state", "entity_id": "binary_sensor.porta_uno",
                               "to": "on"}],
                  "azioni": [{"action": "light.turn_on",
                              "target": {"entity_id": "light.luce_uno"}}]}, _healthy)],
    "confirm": [({"proposta_id": "nessuna"}, _healthy), ({}, _next_turn)],
    "history": [({"riferimento": "light.luce_uno"}, _healthy),
                ({"riferimento": "sensor.contatore_uno", "cosa": "valori"}, _healthy),
                ({"riferimento": "sensor.contatore_uno", "cosa": "valori", "ore": 48},
                 _healthy),
                ({"cosa": "valori"}, _healthy),
                ({"riferimento": "sensor.sensore_a_umidita"}, _healthy),
                ({}, _healthy), ({"limite": 1}, _healthy), ({"salta": 1000}, _healthy),
                ({"ore": 1, "da": "ieri"}, _healthy),
                ({"cosa": "esecuzioni"}, _healthy),
                ({"cosa": "esecuzioni", "riferimento": "automation.automazione_uno",
                  "esecuzione": "run-1"}, _healthy),
                ({"cosa": "errori"}, _healthy),
                ({"riferimento": "light.luce_uno"}, _broken),
                ({"cosa": "esecuzioni"}, _broken)],
    "calendar": [({}, _healthy), ({}, _few_events), ({}, _broken)],
    "mind": [({"cosa": "scope"}, _healthy)],
}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def rendered_by_tool(mounted_app) -> dict[str, Rendered]:
    """Cio' che ogni strumento ha reso nel suo giro."""
    rendered = {name: Rendered() for name in CALLS}
    for name, calls in CALLS.items():
        for arguments, scene in calls:
            with scene(mounted_app) as dispatcher:
                rendered[name].add(await dispatcher.dispatch(name, arguments))
    return rendered


@pytest.mark.asyncio(loop_scope="module")
async def test_ogni_nome_fra_backtick_e_reso_dallo_strumento(rendered_by_tool):
    """Il cancello. Rosso alla nascita (12/10/2026) su tre falsita':
    `related` nominava la chiave `related` (la risposta porta `legami`,
    X-33) e diceva che `search` risponde `non_so_guardare` sui generi che non
    apre (il suo `genere` li rifiuta prima); `history` diceva `run_id` dove
    la riga porta `esecuzione` (X-34)."""
    missing = {name: words for name in CALLS
               if (words := unaccounted(name, rendered_by_tool))}
    assert not missing, missing


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(("name", "word"), [("search", "colore"), ("search", "tipo"),
                                            ("related", "related")])
async def test_un_nome_che_la_risposta_non_porta_arrossisce_col_suo_nome(
        rendered_by_tool, monkeypatch, name, word):
    """La mutazione del piano, tenuta: `colore` in coda alla descrizione di
    `search` fa arrossire il cancello, col nome. `tipo` e' il nome che il
    vocabolario ha tolto (D7, X-16) e che nessuna risposta porta piu';
    `related` lo strumento che nomina se' stesso (X-33).

    Mutazioni ESEGUITE anche sul sorgente (12/10/2026): `colore` scritto
    nella descrizione di `search` in `tools.py` -- rossa la prova del
    cancello, «'search': ['colore']»; `run_id` rimesso nella descrizione di
    `history` -- rossa, «'history': ['run_id']»; lo strumento contato fra
    quelli che puo' nominare -- rossa qui su `related`."""
    mutated = copy.deepcopy(_definition(name))
    mutated["description"] += f" `{word}`"
    monkeypatch.setattr(sys.modules[__name__], "KNOWLEDGE_TOOLS",
                        [mutated if tool["name"] == name else tool
                         for tool in KNOWLEDGE_TOOLS])
    assert unaccounted(name, rendered_by_tool) == [word]


@pytest.mark.asyncio(loop_scope="module")
async def test_ogni_strumento_ha_un_giro_e_il_giro_rende_qualcosa(rendered_by_tool):
    """La derivazione non si e' rotta: i giri coprono ESATTAMENTE gli
    strumenti del catalogo (chiesti a `KNOWLEDGE_TOOLS`, non scritti qui), e
    ognuno ha reso chiavi. Uno strumento nuovo senza giro arrossisce qui."""
    assert set(CALLS) == {tool["name"] for tool in KNOWLEDGE_TOOLS}
    assert all(rendered_by_tool[name].keys for name in CALLS), {
        name for name in CALLS if not rendered_by_tool[name].keys}


def test_le_ammissioni_nominano_parole_che_la_descrizione_dice():
    """Un'ammissione che nessuna descrizione usa piu' e' una porta aperta
    che nessuno guarda: esce."""
    stale = {name: sorted(set(words) - backticked(_definition(name)))
             for name, words in ADMITTED.items()}
    assert not any(stale.values()), stale
