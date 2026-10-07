"""Cosa Home Assistant riserva agli amministratori: una casa sola (Tappa 7,
Task 5: D-43, F-22, D-29).

Fino al 07/10/2026 lo stesso fatto stava in quattro posti -- i servizi del
nucleo negli strumenti, i generi della storia, il corpo nell'anteprima
dell'officina (automazioni e scene) e il corpo nella porta che legge la casa
(solo automazioni). Adesso vive in `home_space/privacy.py`, con la fonte in
Home Assistant scritta accanto, e le porte lo chiedono.

E con loro D-29, la parte rimasta: un taglio e una maschera nel registro dei
turni si dichiarano con i segni della casa (`proxy/_sanitize.py`), non con
`value[:200]` muto e un `"..."` suo.
"""
import ast
from pathlib import Path

import pytest

from hiris.app.home_space import house_history, privacy
from hiris.app.proxy import _sanitize
from hiris.app.usage.store import compact_tool_args

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


# ── il corpo: una regola per le tre porte ──────────────────────────────────

@pytest.mark.parametrize(("kind", "riservato"), [
    ("automation", True), ("automazione", True),
    ("scene", True), ("scena", True),
    ("script", False),
])
def test_il_corpo_di_automazioni_e_scene_e_riservato_quello_degli_script_no(kind, riservato):
    """Riletto nel sorgente di Home Assistant al tag 2026.9.4 (la fonte e' nel
    commento di `BODY_ADMIN_ONLY_DOMAINS`). Il tipo nostro e il dominio di HA
    danno la stessa risposta: la traduzione e' quella del confine.

    Mutazione (eseguita): togliere `"scene"` dall'insieme -- rosse le due righe
    della scena, qui e nell'anteprima dell'officina
    (`test_admission.py::test_la_BOZZA_di_chi_non_amministra_non_rivela_com_e_adesso`)."""
    assert privacy.body_is_admin_only(kind) is riservato


def test_la_porta_che_legge_la_casa_copre_anche_la_scena():
    """F-22: fino al 07/10/2026 la porta che legge la casa copriva solo le
    automazioni, l'officina automazioni e scene. Mutazione (eseguita):
    rimettere `kind != "automazione"` in `cover_reserved_body` -- rossa sulla
    scena."""
    for kind in ("automazione", "scena"):
        coperta = privacy.cover_reserved_body({"corpo": {"x": 1}}, kind=kind)
        assert coperta["corpo"] is None
        assert coperta["corpo_non_disponibile"] == privacy.BODY_ADMIN_ONLY
    script = {"corpo": {"sequence": []}}
    assert privacy.cover_reserved_body(script, kind="script") is script
    vuota = {"corpo": None}
    assert privacy.cover_reserved_body(vuota, kind="automazione") is vuota


# ── i generi della storia ──────────────────────────────────────────────────

def test_i_generi_riservati_sono_generi_veri_della_storia():
    """L'insieme vive in `privacy`, i generi in `house_history.KINDS`: si
    chiede alla storia che esistano, invece di fidarsi della copia dei nomi.
    Mutazione (eseguita): `"esecuzione"` al singolare nell'insieme -- rossa."""
    assert privacy.ADMIN_ONLY_HISTORY_KINDS
    assert privacy.ADMIN_ONLY_HISTORY_KINDS <= set(house_history.KINDS)


# ── una casa sola: nessun altro modulo la riscrive ─────────────────────────

_GONE = {"_BODY_ADMIN_ONLY", "_BEFORE_ADMIN_ONLY", "_HA_CORE_USER_SERVICES",
         "ADMIN_KINDS", "AUTOMATION_BODY_ADMIN_ONLY", "cover_automation_body"}


def _assigned_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
    return names


def test_le_vecchie_case_non_ci_sono_piu():
    """Le quattro case di prima sono uscite: nessun modulo del prodotto (la
    cartella, non un elenco) ridefinisce uno di quei nomi. Mutazione
    (eseguita): rimettere `_BODY_ADMIN_ONLY` in `workshop.py` -- rossa."""
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found += [f"{path.relative_to(APP).as_posix()}: {name}"
                  for name in _assigned_names(tree) & _GONE]
    assert found == []


# ── D-29: il taglio e la maschera si dichiarano ────────────────────────────

def test_nel_registro_dei_turni_il_taglio_si_dichiara():
    """Mutazione (eseguita): rimettere `value[:_ARG_TEXT_MAX]` -- rossa, il
    testo accorciato non dice di esserlo."""
    [fuori] = compact_tool_args([{"testo": "x" * 1000,
                                  "a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}])
    assert len(fuori["testo"]) == 200
    assert fuori["testo"].endswith(_sanitize.CUT)
    assert fuori["a"]["b"]["c"]["d"]["e"] == _sanitize.CUT


def test_la_maschera_di_un_segreto_e_una_sola():
    """Il segnaposto di un segreto ha una casa, `_sanitize.MASK`: nessun altro
    modulo del prodotto lo scrive come letterale (si chiede all'albero di ogni
    modulo). Mutazione (eseguita): rimettere `_ARG_MASK = "***"` in
    `usage/store.py` -- rossa."""
    assert compact_tool_args([{"code": "1234"}]) == [{"code": _sanitize.MASK}]
    found = []
    for path in sorted(APP.rglob("*.py")):
        if path.relative_to(APP).as_posix() == "proxy/_sanitize.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and node.value == _sanitize.MASK:
                found.append(f"{path.relative_to(APP).as_posix()}:{node.lineno}")
    assert found == []
