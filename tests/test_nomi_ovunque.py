"""I nomi delle persone non arrivano a un attore, ovunque compaiano (Fase S,
S.8, scelta del proprietario del 30/10/2026: «ovunque compaia il nome»).

**La misura che l'ha chiesta** (Sprint, 30/10/2026, solo conti). Fino a oggi
l'osservatore copriva solo le righe delle presenze (`person.*`,
`device_tracker.*`): la domanda che apre la campagna portava il nome di una
persona in 27 righe su 383, dentro gli id e i nomi di dispositivi personali
-- uno speaker «... di <persona>», un'automazione «... notifica iPhone
<persona>». Le ricette non coprivano niente, nemmeno la frase «Il dispositivo
si chiama ...». L'analista copriva gia' la domanda intera.

**La regola**: ogni attore copre la domanda intera con la stessa maschera
(`privacy.PresenceMask`): un'entita' che porta il nome di una persona nell'id
esce col segnaposto, e il nome di una persona, dovunque stia nel testo, col
segnaposto della persona. La risposta torna agli id veri prima di ogni
controllo.
"""
from __future__ import annotations

import json
import os

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.privacy import PLACEHOLDER_HINT, PresenceMask
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import analyst_turn as at
from hiris.app.mind import observer
from hiris.app.mind import recipe_turn as rt
from hiris.app.mind.knowledge import KnowledgeStore
from hiris.app.mind.store import ObservationsStore
from tests._runner_finto import RunnerFinto

_NAMES = ("paolo", "giulia")


def _row(entity_id, name, **extra):
    row = {"id": entity_id, "nome": name, "classe": None, "unita": None,
           "translation_key": None, "categoria": None, "disabilitata": 0,
           "nascosta": 0, "area_id": None, "piattaforma": "x"}
    row.update(extra)
    return row


def _house():
    """Le forme della misura: un'automazione col nome nell'id, uno speaker
    col nome nel solo nome (non nell'id) e nel suo dispositivo, un sensore
    del dispositivo dello speaker, e un'area col nome di una persona."""
    rows = [
        _row("climate.camera_t", "Termostato Camera", area_id="camera"),
        _row("person.paolo", "Paolo"),
        _row("person.giulia", "Giulia"),
        _row("automation.notifica_iphone_paolo", "Notifica iPhone Paolo"),
        _row("media_player.salotto", "Speaker di Giulia", dispositivo_id="d1",
             area_id="studio"),
        _row("sensor.speaker_volume", "Volume", dispositivo_id="d1",
             classe="sound_pressure", unita="dB"),
    ]
    return House({"entita": rows,
                  "dispositivi": [{"id": "d1", "nome": "Speaker di Giulia"}],
                  "aree": [{"id": "camera", "nome": "Camera"},
                           {"id": "studio", "nome": "Studio di Paolo"}]},
                 Mirror(state={row["id"]: "on" for row in rows}))


def _without_names(text: str) -> None:
    for name in _NAMES:
        assert name not in text.lower(), f"il nome «{name}» arriva al modello:\n{text}"


@pytest.fixture
def archivio(tmp_path):
    store = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield store
    store.close()


@pytest.fixture
def sapere(tmp_path):
    store = KnowledgeStore(os.path.join(str(tmp_path), "sapere.db"))
    yield store
    store.close()


# -- l'osservatore -------------------------------------------------------------

@pytest.mark.asyncio
async def test_sulla_CATENA_la_domanda_dell_osservatore_non_porta_nessun_nome(archivio):
    """Mutazione ESEGUITA: in `question_parts` le righe fuori dalla maschera
    -- rossa, lo speaker «di Giulia» e l'automazione arrivano col nome (e
    rossa anche la prova del ponte)."""
    archivio.set_objective("che Paolo trovi la casa calda", when_ts=1000.0)
    model = RunnerFinto('[{"id": "automation.#1", "dentro": false, '
                        '"motivo": "notifica, non pesa"}]')

    outcome = await observer.reconsider(model, archivio, _house(), reason="prova",
                                        now=1000.0)

    question = model.chiamate[0]["user_message"]
    _without_names(question)
    assert PLACEHOLDER_HINT in question
    assert "Termostato Camera" in question, "il resto della casa resta com'e'"
    assert outcome["decise"] >= 1, outcome
    assert archivio.scope()["automation.notifica_iphone_paolo"]["dentro"] is False


def test_sul_PONTE_l_obiettivo_e_le_righe_escono_coperte(archivio):
    """Mutazione ESEGUITA: in `question_parts` l'obiettivo fuori dalla
    maschera -- rossa, «Paolo» arriva dall'obiettivo."""
    archivio.set_objective("che Paolo trovi la casa calda", when_ts=1000.0)

    turn = observer.bridge_turn(archivio, _house())

    _without_names(turn["history"][0]["content"])


def test_la_decisione_del_ponte_torna_all_id_vero(archivio):
    """Mutazione ESEGUITA: `apply_answer` senza `presence.unmask` -- rossa,
    il segnaposto finisce fra le ignorate (e rosse le due prove del ritorno
    in `test_osservatore_senza_persone.py`)."""
    house = _house()
    handle = PresenceMask(house).handles["automation.notifica_iphone_paolo"]

    outcome = observer.apply_answer(
        archivio, house,
        json.dumps([{"id": handle, "dentro": True, "motivo": "dice chi arriva"}]),
        reason="il ponte ha risposto", asked=set(observer.watched_ids(house)),
        now=1000.0)

    assert outcome["decise"] == 1, outcome
    assert archivio.scope()["automation.notifica_iphone_paolo"]["dentro"] is True


# -- le ricette ----------------------------------------------------------------

def test_la_domanda_della_ricetta_non_porta_il_nome_del_dispositivo():
    """La frase «Il dispositivo si chiama ...» portava il nome della persona.

    Mutazione ESEGUITA: `build_device_question_body` che non copre la
    domanda -- rossa."""
    question = rt.build_device_question("che Paolo stia bene", _house(), "d1")

    _without_names(question)
    assert question.startswith(PLACEHOLDER_HINT)
    assert "sensor.speaker_volume" in question


def test_una_casa_senza_nomi_nella_domanda_non_spiega_nessun_segnaposto():
    house = House({"entita": [_row("sensor.forno", "Forno", dispositivo_id="d9")],
                   "dispositivi": [{"id": "d9", "nome": "Forno"}], "aree": []},
                  Mirror(state={"sensor.forno": "20"}))

    assert PLACEHOLDER_HINT not in rt.build_device_question("x", house, "d9")


def test_la_ricetta_scritta_coi_segnaposto_torna_agli_id_veri(sapere):
    """Una ricetta nomina le entita' che ha letto, cioe' i segnaposto.

    Mutazione ESEGUITA: `apply_recipe` senza `unmask` -- rossa, «l'entita'
    non e' fra quelle consegnate»."""
    house = _row_house_named_after_person()
    handle = PresenceMask(house).handles["sensor.giulia_energia"]
    recipe = {"why": "l'energia della sua stanza",
              "steps": [{"name": "energia", "operation": "somma_periodo",
                         "inputs": [f"@{handle}"], "params": {"unit": "kWh"}}]}

    outcome = rt.apply_recipe(sapere, house, "d2", json.dumps(recipe),
                              who="prova", when_ts=1000.0)

    assert outcome["scritta"], outcome
    written = json.loads(sapere.get("dispositivo", "d2", rt.RECIPE_FIELD).value)
    assert written["steps"][0]["inputs"] == ["@sensor.giulia_energia"]


def _row_house_named_after_person():
    rows = [_row("person.giulia", "Giulia"),
            _row("sensor.giulia_energia", "Energia", dispositivo_id="d2",
                 classe="energy", unita="kWh")]
    return House({"entita": rows, "dispositivi": [{"id": "d2", "nome": "Presa"}],
                  "aree": []},
                 Mirror(state={row["id"]: "70" for row in rows}))


# -- l'analista ----------------------------------------------------------------

def test_la_domanda_dell_analista_spiega_il_segnaposto_quando_c_e():
    """L'analista copriva gia' la domanda: ora dice anche come leggerla, con
    la stessa frase degli altri due.

    Mutazione ESEGUITA: `build_question_body` senza `PLACEHOLDER_HINT` --
    rossa."""
    serie = {"giorni": ["2026-10-29"], "obiettivi": [],
             "serie": [{"soggetto": "d1", "nome": "Speaker di Giulia",
                        "misura": "volume", "unita": "dB",
                        "valori": [40.0], "coperture": [1.0]}]}
    presence = PresenceMask(_house())

    question = at.build_question(serie, presence=presence)

    _without_names(question)
    assert question.startswith(PLACEHOLDER_HINT)
    serie["serie"][0]["nome"] = "Forno"
    assert PLACEHOLDER_HINT not in at.build_question(serie, presence=presence)


def test_un_soggetto_che_tace_e_porta_un_nome_nell_id_esce_coperto(archivio):
    """I soggetti dentro che tacciono (`gone_lines`) portano l'id grezzo:
    uno col nome di una persona nell'id lo porterebbe al modello (R230-2,
    giro 230 della revisione).

    Mutazione ESEGUITA: in `question_parts` i soggetti che tacciono fuori
    dalla maschera -- rossa."""
    rows = [_row("climate.camera_t", "Termostato Camera"),
            _row("person.paolo", "Paolo"),
            _row("automation.paolo_arriva", "Arrivo", disabilitata=1)]
    house = House({"entita": rows, "aree": []},
                  Mirror(state={"climate.camera_t": "heat", "person.paolo": "home"}))
    assert archivio.decide_scope("automation.paolo_arriva", inside=True,
                                 reason="dice chi arriva", author="observer",
                                 when_ts=1000.0)
    assert any("automation.paolo_arriva" in line
               for line in observer.gone_lines(archivio, house)), "la premessa"

    turn = observer.bridge_turn(archivio, house)

    _without_names(turn["history"][0]["content"])
