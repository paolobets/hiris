"""TIPO (spec §4.1; Tappa 3, Task 7, B-17): il dominio, la classe e l'unita'
DI ADESSO di un'entita', da `House.kind_of`.

Fino al 04/10/2026 l'anagrafe scriveva la classe e l'unita' dello specchio al
momento della ricostruzione e le teneva ferme fino alla ricostruzione dopo
(`reader._entity`, `live_first` con le mappe vive passate da `rebuild`).
Osservatore e ricette leggevano quelle: un sensore passato da °C a °F in Home
Assistant arrivava al modello in °C finche' un evento di registro non faceva
rileggere i registri. Ora l'anagrafe porta solo cio' che il registro dichiara,
e chi vuole il vivo lo chiede alla casa del giro.

La casa e' quella sintetica (`tests/_casa_sintetica.py`), montata come la
monta il prodotto: l'anagrafe dal lettore vero, lo specchio da `_to_minimal`
e `live_mirror`.

Mutazioni ESEGUITE (04/10/2026), ognuna ripristinata e verificata con
`git status`:
- `observer.house_lines` torna a leggere `entity.get("unita")` (il campo
  dell'anagrafe) invece di `House.kind_of` -- rossa
  (`test_cambiata_l_unita_nello_specchio_l_osservatore_la_vede`: la riga non
  porta piu' nessuna unita');
- `reader._entity` torna a mettere nell'anagrafe un'unita' che non viene dal
  registro (la costante `"°C"` al posto di `unit_of_measurement`, cioe' un
  valore congelato alla ricostruzione) -- rossa
  (`test_l_anagrafe_non_congela_l_unita_della_ricostruzione`).
"""
from __future__ import annotations

import pytest

from hiris.app import server
from hiris.app.api.handlers_home_space import _live_kinds
from hiris.app.home_space.ha_vocabulary import has_statistics
from hiris.app.home_space.house import House
from hiris.app.home_space.reader import build_home_space
from hiris.app.home_space.topology import live_mirror
from hiris.app.mind import observer, recipe_turn
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.entity_cache import _to_minimal
from tests._avvio import started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs
from tests.test_giro_statistic_ids import _call_graph, _reaches

TERMOMETRO = "sensor.sensore_a_temperatura"


def _house(unit: str = "°C", statistic_ids=None) -> House:
    inputs = synthetic_inputs()
    for row in inputs["states"]:
        if row["entity_id"] == TERMOMETRO:
            row["attributes"]["unit_of_measurement"] = unit
    mirror = live_mirror([_to_minimal(row) for row in inputs["states"]])
    return House(build_home_space(inputs["registries"]), mirror,
                 statistic_ids=statistic_ids)


def _line(lines: list[str], entity_id: str) -> str:
    return next(line for line in lines if line.split(" · ")[0] == entity_id)


def test_kind_of_da_dominio_classe_e_unita_dello_specchio():
    house = _house()
    assert house.kind_of(TERMOMETRO) == {
        "dominio": "sensor", "classe": "temperature", "unita": "°C",
        "statistiche": True, "statistiche_da": "regola"}
    assert house.kind_of("light.luce_uno") == {
        "dominio": "light", "classe": None, "unita": None,
        "statistiche": False, "statistiche_da": "regola"}


def test_kind_of_non_inventa_un_entita_che_nessuno_conosce():
    assert _house().kind_of("sensor.non_esiste") is None


def test_l_anagrafe_non_congela_l_unita_della_ricostruzione():
    """La voce dell'anagrafe porta cio' che il registro dichiara: per il
    termometro sintetico, niente (come su 842 entita' su 842 della casa vera,
    misurato il 10/09/2026)."""
    entry = next(e for e in _house().home_space["entita"] if e["id"] == TERMOMETRO)
    assert entry["classe"] is None
    assert entry["unita"] is None


def test_cambiata_l_unita_nello_specchio_l_osservatore_la_vede():
    """La prova rossa del piano (Task 7, passo 2): la stessa anagrafe, lo
    specchio cambiato dopo -- l'osservatore e le ricette vedono l'unita' di
    adesso."""
    before, after = _house("°C"), _house("°F")
    assert _line(observer.house_lines(before), TERMOMETRO).split(" · ")[3] == "°C"
    assert _line(observer.house_lines(after), TERMOMETRO).split(" · ")[3] == "°F"
    recipe = _line(recipe_turn.device_lines(after, "dev_a"), TERMOMETRO)
    assert recipe.split(" · ")[2:4] == ["temperature", "°F"]


def test_l_albero_della_pagina_porta_la_classe_e_l_unita_di_adesso():
    """`GET /api/home-space`: la pagina dell'albero mostrava la classe che la
    ricostruzione aveva copiato. Ora la chiede alla casa, e le voci
    dell'anagrafe non si toccano."""
    house = _house("°F")
    rows = [entry for floor in _live_kinds(house) for area in floor["aree"]
            for entry in area.get("entita") or [] if entry["id"] == TERMOMETRO]
    assert [(row["classe"], row["unita"]) for row in rows] == [("temperature", "°F")]
    assert next(e for e in house.home_space["entita"]
                if e["id"] == TERMOMETRO)["unita"] is None


# -- B-12: «ha statistiche?» = cio' che Home Assistant tiene -----------------
#
# Mutazioni ESEGUITE (04/10/2026), ognuna ripristinata e verificata con
# `git status`:
# - `ha_vocabulary.has_statistics` che ignora l'elenco e usa sempre la regola
#   -- rosse le prove dell'elenco (la casa e il watcher);
# - il watcher che torna alla sua formula (`sensor.` e uno `state_class`
#   qualunque) -- rossa `test_il_watcher_registra_il_sensore_che_home_
#   assistant_non_tiene`;
# - `Watcher.hold_statistic_ids` che accetta anche la busta del guasto --
#   rossa `test_una_lettura_fallita_non_cancella_l_ultima_buona`;
# - il giro delle condizioni senza `hold_watcher_statistic_ids` -- rossa
#   `test_il_giro_delle_condizioni_consegna_l_elenco_al_watcher`.

#: La regola del ripiego, letta nel sorgente il 04/10/2026: una banderuola le
#: statistiche le ha (la media circolare).
BANDERUOLA = "sensor.vento_direzione"


def test_con_l_elenco_di_home_assistant_la_risposta_e_sua():
    """`sensor.sensore_b_segnale` dichiara `state_class: measurement` ma la
    casa sintetica non lo mette fra le statistiche (`statistic_ids`): la
    regola direbbe di si', Home Assistant dice di no. Con l'elenco vince lui."""
    ids = set(synthetic_inputs()["statistic_ids"]) - {"sensor.sensore_b_segnale"}
    house = _house(statistic_ids=ids)
    assert house.has_statistics(TERMOMETRO) is True
    assert house.has_statistics("sensor.sensore_b_segnale") is False
    assert house.kind_of("sensor.sensore_b_segnale")["statistiche_da"] == "home_assistant"
    assert _house().has_statistics("sensor.sensore_b_segnale") is True


def test_senza_elenco_vale_la_regola_del_sorgente():
    assert has_statistics(BANDERUOLA, "measurement_angle", None) is True
    assert has_statistics("binary_sensor.fumo", "measurement", None) is False
    assert has_statistics("sensor.solare", None, None) is False
    assert has_statistics(BANDERUOLA, "measurement_angle", frozenset()) is False


class _Archivio:
    """L'archivio dell'osservatore, ridotto a cio' che `watch_reading` chiede."""

    def __init__(self):
        self.annotati = []

    def is_watched(self, subject):
        return True

    def record(self, **row):
        self.annotati.append(row)


def _reading(entity_id: str, state_class: str | None) -> dict:
    attributes = {"state_class": state_class} if state_class else {}
    return {"entity_id": entity_id, "old_state": {"state": "1", "attributes": attributes},
            "new_state": {"state": "2", "attributes": attributes,
                          "last_updated": "2026-10-04T10:00:00+00:00"}}


def test_il_watcher_registra_il_sensore_che_home_assistant_non_tiene():
    """Il cambio di comportamento di B-12 (tabella del piano): un `sensor` con
    `state_class` che il recorder non tiene (escluso dal filtro, o con uno
    stato non numerico) fino al 04/10/2026 si perdeva da tutte e due le parti.
    Ora si scrive. E una statistica importata sotto un `entity_id` senza
    `state_class` non si ricopia."""
    archivio = _Archivio()
    watcher = Watcher(archivio, now=lambda: 1_790_000_000.0)
    watcher.hold_statistic_ids({"sensor.importata"})
    assert watcher.watch_reading(_reading("sensor.non_tenuto", "measurement")) is True
    assert watcher.watch_reading(_reading("sensor.importata", None)) is False
    assert [row["subject"] for row in archivio.annotati] == ["sensor.non_tenuto"]


def test_prima_del_primo_giro_il_watcher_usa_la_regola():
    watcher = Watcher(_Archivio(), now=lambda: 1_790_000_000.0)
    assert watcher.watch_reading(_reading(BANDERUOLA, "measurement_angle")) is False
    assert watcher.watch_reading(_reading("sensor.solare", None)) is True


def test_una_lettura_fallita_non_cancella_l_ultima_buona():
    watcher = Watcher(_Archivio(), now=lambda: 1_790_000_000.0)
    watcher.hold_statistic_ids({"sensor.importata"})
    watcher.hold_statistic_ids({"errore": "websocket giu'", "causa": "rete"})
    assert watcher.watch_reading(_reading("sensor.importata", None)) is False


@pytest.mark.asyncio
async def test_il_giro_delle_condizioni_consegna_l_elenco_al_watcher(started_app):
    """La consegna si fa con la lettura condivisa dei giri, e il lavoro
    periodico che la fa e' chiesto allo schedulatore dell'app avviata (non
    scritto qui)."""
    graph = _call_graph()
    jobs = [job.id for job in started_app["scheduler"].get_jobs()
            if _reaches(graph, job.func.__name__, "hold_watcher_statistic_ids")]
    assert jobs == ["hiris_mind_conditions"]
    await server.hold_watcher_statistic_ids(started_app, started_app["ha_client"])
    assert started_app["watcher"]._statistic_ids == frozenset(
        synthetic_inputs()["statistic_ids"])
