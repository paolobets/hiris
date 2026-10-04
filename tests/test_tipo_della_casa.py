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

from hiris.app.api.handlers_home_space import _live_kinds
from hiris.app.home_space.house import House
from hiris.app.home_space.reader import build_home_space
from hiris.app.home_space.topology import live_mirror
from hiris.app.mind import observer, recipe_turn
from hiris.app.proxy.entity_cache import _to_minimal
from tests._casa_sintetica import synthetic_inputs

TERMOMETRO = "sensor.sensore_a_temperatura"


def _house(unit: str = "°C") -> House:
    inputs = synthetic_inputs()
    for row in inputs["states"]:
        if row["entity_id"] == TERMOMETRO:
            row["attributes"]["unit_of_measurement"] = unit
    mirror = live_mirror([_to_minimal(row) for row in inputs["states"]])
    return House(build_home_space(inputs["registries"]), mirror)


def _line(lines: list[str], entity_id: str) -> str:
    return next(line for line in lines if line.split(" · ")[0] == entity_id)


def test_kind_of_da_dominio_classe_e_unita_dello_specchio():
    house = _house()
    assert house.kind_of(TERMOMETRO) == {
        "dominio": "sensor", "classe": "temperature", "unita": "°C"}
    assert house.kind_of("light.luce_uno") == {
        "dominio": "light", "classe": None, "unita": None}


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
