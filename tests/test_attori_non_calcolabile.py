"""Il «non lo so» degli attori ha una forma sola (B-27, Chiusura, F7,
13/10/2026).

Un rifiuto e' `NotComputable`: la frase per chi legge, la causa del
vocabolario chiuso per chi conta (`operations.CAUSES`). Scritto in una riga,
e' `non_calcolabile` + `causa`, e lo scrive `NotComputable.as_fields`. Fino a
quel giorno il resoconto, i passi di un calcolo e le ricette mute componevano
i due campi a mano, e l'analista (`analyst._deviation`) diceva il suo «non lo
so» con la sola frase: la stessa cosa con due forme, a seconda della porta.

**Chi scrive la chiave si chiede al sorgente**, non si elenca: ogni funzione
del prodotto che scrive `non_calcolabile` in un dizionario o in una riga. Le
sole ammesse stanno in `AMMESSE`, ognuna con la sua ragione (una lista di
AMMISSIONE: chiude per difetto).

Mutazioni ESEGUITE il 13/10/2026, ripristino verificato con `git status`:
- `_deviation` che rimette `out["non_calcolabile"] = ...` per la storia corta
  -- rossa (il cancello nomina `analyst.py::_deviation`, e la prova della
  forma: manca `causa`);
- `index_row` che copia la sola frase -- rossa (manca `causa` nella riga
  dell'indice).
"""
from __future__ import annotations

import ast
import pathlib

from hiris.app.mind import analyst
from hiris.app.mind.operations import CAUSES

APP = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"

#: funzione -> perche' puo' scrivere la chiave da se'.
AMMESSE = {
    "mind/operations.py::as_fields": "e' la forma: l'unico posto che la scrive",
    "mind/analyst.py::index_row": (
        "copia nella riga dell'indice un rifiuto gia' formato da `as_fields` "
        "in `_deviation`, con la sua causa accanto"),
    "mind/store.py::_migration_8": (
        "una migrazione dell'archivio, gia' girata sulle case avviate: riscrive "
        "righe di resoconti archiviati prima che la causa esistesse. Il file e' "
        "della fetta F4"),
}


def _writers_in(tree: ast.AST, name: str) -> set[str]:
    found = set()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Dict) and any(
                    isinstance(key, ast.Constant) and key.value == "non_calcolabile"
                    for key in node.keys):
                found.add(f"{name}::{func.name}")
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "non_calcolabile"
                    for target in node.targets):
                found.add(f"{name}::{func.name}")
    return found


def writers() -> set[str]:
    """Le funzioni del prodotto che scrivono la chiave, chieste al sorgente."""
    found = set()
    for path in sorted(APP.rglob("*.py")):
        found |= _writers_in(ast.parse(path.read_text(encoding="utf-8")),
                             path.relative_to(APP).as_posix())
    return found


def test_la_chiave_la_scrive_solo_la_forma():
    found = writers()
    assert "mind/operations.py::as_fields" in found, "la derivazione si e' svuotata"
    assert found <= set(AMMESSE), sorted(found - set(AMMESSE))


def test_la_derivazione_vede_le_due_scritture():
    planted = ast.parse("def f(row):\n    row['non_calcolabile'] = 'x'\n"
                        "def g():\n    return {'non_calcolabile': 'x'}\n"
                        "def h(row):\n    return row.get('non_calcolabile')\n")
    assert _writers_in(planted, "p") == {"p::f", "p::g"}


def _series(values):
    return {"serie": [{"soggetto": "d", "nome": "N", "misura": "m", "chiave": None,
                       "unita": "kWh", "valori": values, "coperture": [1.0] * len(values)}]}


def test_ogni_rifiuto_dell_analista_porta_la_sua_causa():
    """Storia corta, storia che non varia (oggi uguale e oggi diversa), ultimo
    valore che non e' un numero: quattro rifiuti, quattro cause del
    vocabolario, e la riga dell'indice le porta."""
    for values in ([10.0, 20.0], [5.0] * 5, [10.0] * 4 + [20.0], ["x", "y", "z"]):
        row = analyst.with_deviation(_series(values))["serie"][0]
        deviation = row["scostamento"]
        assert deviation.get("non_calcolabile"), values
        assert deviation.get("causa") in CAUSES, (values, deviation)
        line = analyst.index_row(row, [])
        assert (line["non_calcolabile"], line["causa"]) == (
            deviation["non_calcolabile"], deviation["causa"]), values
