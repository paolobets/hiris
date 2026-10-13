"""L'indice delle voci dell'anagrafe per id vive in un posto solo (A-16).

F1 della Chiusura (13/10/2026): `house_history.read_runs` e
`topology.compare_with_home_assistant` si rifacevano ognuna il loro
`{e.get("id"): e for e in home["entita"]}`, accanto a quello di `House`. Ora la
storia chiede `House.entry`, e il confronto (puro, sull'anagrafe che gli passa
il giro) e `House` chiedono `topology.entity_index`.

Mutazione ESEGUITA e ripristinata (`git status` pulito): in `read_runs` torna
`registry = {e.get("id"): e for e in house.home_space.get("entita") or []}` --
rossa `test_nessuna_delle_tre_si_rifa_l_indice` (`read_runs` nell'elenco).
La copia che resta in `home_space/briefing.py` (i nomi dei dispositivi del
nucleo) e' della fetta F3a, padrone di quel file: la modifica le arriva a parte.
"""
import ast
from pathlib import Path

from hiris.app.home_space import topology
from hiris.app.home_space.house import House

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
#: Le funzioni che si rifacevano l'indice, col loro file. E' il FATTO della
#: voce A-16 (le tre copie che il registro nomina), non una copia di un elenco.
WHERE = {"home_space/house_history.py": ("read_runs",),
         "home_space/topology.py": ("compare_with_home_assistant",),
         "home_space/house.py": ("_entity_index",)}


def _functions(relative: str, names: tuple[str, ...]) -> dict[str, ast.AST]:
    tree = ast.parse((APP / relative).read_text(encoding="utf-8"))
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in names}


def _indexes_the_registry(node: ast.AST) -> bool:
    """Un dizionario costruito scorrendo le voci dell'anagrafe (`entita`)."""
    return isinstance(node, ast.DictComp) and any(
        "entita" in ast.unparse(generator.iter) for generator in node.generators)


def test_nessuna_delle_tre_si_rifa_l_indice():
    rebuilt = []
    for relative, names in WHERE.items():
        found = _functions(relative, names)
        assert set(found) == set(names), f"{relative}: non trovo {names}"
        rebuilt += [name for name, function in found.items()
                    if any(_indexes_the_registry(node) for node in ast.walk(function))]
    assert rebuilt == [], f"si rifanno l'indice dell'anagrafe: {rebuilt}"


def test_la_casa_e_il_confronto_leggono_lo_stesso_indice():
    voce = {"id": "light.cucina", "nome": "Cucina"}
    home_space = {"entita": [voce, "non una voce", {"nome": "senza id"}]}
    assert topology.entity_index(home_space) == {"light.cucina": voce}
    house = House(home_space, topology.live_mirror([]))
    assert house.entry("light.cucina") is voce
    assert house.entry("senza id") is None
