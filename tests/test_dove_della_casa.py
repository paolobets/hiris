"""DOVE sta un'entita' (Tappa 3, Task 6: B-10, B-37, B-38, B-40; D3).

`House.where(id)` risponde con area, area ereditata, piano, dispositivo e
integrazione, componendo l'albero di `topology.hierarchy` (che usa
`topology.actual_area`); la scheda di `view("entita", ...)` lo porta come
`dove`. La casa e' quella sintetica della sonda (`tests/_casa_sintetica.py`),
che ha tre entita' che ereditano l'area dal dispositivo.

I cancelli di B-37, B-38 e B-40 CHIEDONO il loro elenco: gli id delle
pseudo-aree a `topology` (le costanti `_ID_*`), i file a `hiris/app`.

Rosse prima del codice, il 04/10/2026, per la ragione giusta: la scheda senza
`dove` (KeyError), la sonda senza `house.where`, quattro pseudo-aree
riconosciute a mano (tre `startswith("__")` e `_NOWHERE`), la mappa delle
etichette in `handlers_home_space`, «(id: X)» in `briefing`.

Mutazioni ESEGUITE il 04/10/2026 e ripristinate (`git status` pulito):
- `House.where` che legge il solo `area_id` (senza, «Senza area») -- rosse
  quattro prove, fra cui la sonda: 7 casi `area_dove`, il primo
  `sensor.sensore_a_temperatura` (vera `stanza_uno`, emessa `__senza_area__`);
- la derivazione: un `_ID_PROVA = "__prova__"` nuovo in `topology` e lo stesso
  letterale in `house_query` -- rossa, senza toccare la prova.

La prova sulla domanda `dove` della sonda e' uscita col Task 12 (04/10/2026),
insieme alla domanda: l'osservatore chiede l'area a `House.where`, e non c'e'
piu' una seconda copia da confrontare.
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import sonda_parita
from _casa_sintetica import synthetic_inputs

from hiris.app.home_space import topology
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view

CLOCK = 1_790_000_000.0


@pytest.fixture()
def house():
    inputs = sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK)
    return House(inputs["home_space"], inputs["mirror"])


def test_l_area_ereditata_dal_dispositivo_arriva_col_suo_piano(house):
    assert house.where("sensor.sensore_a_temperatura") == {
        "area": {"id": "stanza_uno", "nome": "Stanza uno"},
        "area_ereditata": True,
        "piano": {"id": "piano_terra", "nome": "Piano terra"},
        "dispositivo": {"id": "dev_a", "nome": "Sensore A"},
        "integrazione": "marca_uno",
    }


def test_l_area_propria_non_e_ereditata(house):
    assert house.where("switch.presa_uno") == {
        "area": {"id": "stanza_due", "nome": "Stanza due"},
        "area_ereditata": False,
        "piano": {"id": "piano_terra", "nome": "Piano terra"},
        "dispositivo": {"id": "dev_b", "nome": "Sensore B"},
        "integrazione": "marca_uno",
    }
    assert house.where("light.luce_uno")["dispositivo"] is None


def test_senza_area_resta_la_pseudo_area_col_suo_id_e_il_piano_tace(house):
    where = house.where("automation.automazione_uno")
    assert where["area"] == {"id": "__senza_area__", "nome": "Senza area"}
    assert where["area_ereditata"] is False
    assert where["piano"] is None


def test_anche_una_disabilitata_ha_un_dove(house):
    assert house.where("sensor.sensore_d_spento")["area"]["id"] == "stanza_uno"


def test_un_entita_che_il_registro_non_conosce_non_ha_un_dove(house):
    assert house.where("sensor.inesistente") is None


def test_coi_dispositivi_non_letti_il_dove_lo_dice_invece_di_tacere():
    inputs = sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK)
    house = House(inputs["home_space"], inputs["mirror"], ("dispositivi",))
    where = house.where("sensor.sensore_a_temperatura")
    assert where["area"] == {"id": "__dispositivi_non_letti__",
                             "nome": "Dispositivi non letti"}
    assert where["area_ereditata"] is False


def test_la_scheda_di_un_entita_dice_dove_sta(house):
    """B-10: fino al Task 6 la scheda di `guarda` non diceva l'area."""
    detail = view(house, [], [], "entita", "sensor.sensore_a_temperatura",
                  judgments=None)
    assert detail["dove"] == house.where("sensor.sensore_a_temperatura")


# --- i cancelli: ogni regola dalla sua funzione ---------------------------

def _app_trees():
    files = sorted(APP.rglob("*.py"))
    assert len(files) > 50, "l'elenco dei moduli si e' svuotato"
    for path in files:
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _pseudo_ids() -> set[str]:
    ids = {value for name, value in vars(topology).items()
           if name.startswith("_ID_") and isinstance(value, str)}
    assert {"__senza_area__", "__dispositivi_non_letti__"} <= ids, \
        "la derivazione degli id delle pseudo-aree si e' svuotata"
    return ids


def test_una_pseudo_area_si_riconosce_solo_in_topology():
    """B-37: «e' una pseudo-area?» era scritto a mano tre volte
    (`startswith("__")`), e `_NOWHERE` ricopiava l'id `__senza_area__`."""
    ids = _pseudo_ids()
    found = []
    for path, tree in _app_trees():
        if path.name == "topology.py" and path.parent.name == "home_space":
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "startswith" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "__"):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno} startswith('__')")
            if isinstance(node, ast.Constant) and node.value in ids:
                found.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.value!r}")
    assert found == []


def test_la_mappa_delle_etichette_si_chiede_a_label_names():
    """B-38: `{label_id: nome}` riscritta a mano in `handlers_home_space`."""
    found = []
    for path, tree in _app_trees():
        if path.name == "topology.py" and path.parent.name == "home_space":
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.comprehension):
                continue
            for inner in ast.walk(node.iter):
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "get" and inner.args
                        and isinstance(inner.args[0], ast.Constant)
                        and inner.args[0].value == "etichette"
                        and isinstance(inner.func.value, ast.Name)
                        and inner.func.value.id == "home_space"):
                    found.append(f"{path.relative_to(ROOT)}:{node.iter.lineno}")
    assert found == []


def test_il_segno_dell_id_si_scrive_solo_in_topology():
    """B-40: «(id: X)» scritto a mano in `briefing._device_annotation`."""
    found = []
    for path, tree in _app_trees():
        if path.name == "topology.py" and path.parent.name == "home_space":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr) and any(
                    isinstance(part, ast.Constant) and "(id: " in str(part.value)
                    for part in node.values):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert found == []


def test_il_dispositivo_senza_nome_ha_lo_stesso_nome_da_ogni_porta():
    """Un dispositivo senza nome in Home Assistant (`name_by_user` e `name`
    entrambi nullable, `reader._device`) si chiama col suo id (A-16,
    `topology.device_name`). Fino al 05/10/2026 `where` diceva `nome: None`
    mentre `House.name` e la scheda del dispositivo dicevano l'id: lo stesso
    oggetto con due nomi a seconda della porta (fondamenta 3; revisione
    cloud, giro 1, R1)."""
    from hiris.app.home_space.reader import build_home_space
    from hiris.app.home_space.topology import live_mirror

    registries = {
        "entita": [{"entity_id": "light.x", "platform": "hue", "device_id": "d1",
                    "disabled_by": None, "hidden_by": None}],
        "dispositivi": [{"id": "d1", "name": None, "name_by_user": None}],
    }
    house = House(build_home_space(registries), live_mirror([]))
    assert house.where("light.x")["dispositivo"] == {"id": "d1", "nome": "d1"}
    assert house.where("light.x")["dispositivo"]["nome"] == house.name("dispositivo", "d1")
    assert view(house, [], [], "dispositivo", "d1")["nome"] == "d1"
