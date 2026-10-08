"""Il vocabolario dei campi: il glossario e il modulo dicono la stessa cosa
(Tappa 9, F2; piano della Tappa 4, Task 7, passo 1).

`docs/GLOSSARIO.md`, «Il vocabolario dei campi», e' il registro dei nomi che
il proprietario approva; `home_space/field_vocabulary.py` e' la sua forma nel
codice, che il prodotto legge. Questa prova li confronta nei due versi: ogni
campo del modulo ha la sua riga nel glossario, ogni campo del glossario e' nel
modulo, con gli stessi proprietari e gli stessi nomi tolti. Le due tabelle si
CHIEDONO ai due file: nessun elenco e' scritto qui.

Mutazioni ESEGUITE l'08/10/2026:
- rinominato `"regola"` in `"_regola_x"` dentro `FIELDS` -- rossa: «nel
  modulo e non nel glossario: ['_regola_x']»;
- tolto `scena` dai proprietari della riga `stato` del glossario -- rossa,
  col campo e i due insiemi;
- tolto `"letto"` dai nomi tolti di `lette` nel modulo -- rossa, col campo.
"""
from __future__ import annotations

import re
from pathlib import Path

from hiris.app.home_space.field_vocabulary import FIELDS

GLOSSARY = Path(__file__).resolve().parents[1] / "docs" / "GLOSSARIO.md"


def glossary_rows() -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """campo -> (proprietari, nomi tolti), dalla tabella del glossario."""
    text = GLOSSARY.read_text(encoding="utf-8")
    section = text[text.index("## Il vocabolario dei campi"):
                   text.index("### Il controllo di collisione, eseguito")]
    rows: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = line.strip().strip("|").split("|")
        owners = frozenset(re.findall(r"`([a-z_]+)`", cells[3]))
        replaced = frozenset(re.findall(r"`([a-z_]+)`", cells[4]))
        for name in re.findall(r"`([a-z_]+)`", cells[0]):
            rows[name] = (owners, replaced)
    return rows


def test_la_tabella_del_glossario_si_legge():
    """La derivazione non si e' svuotata: una tabella letta male renderebbe
    la prova verde senza guardare niente."""
    rows = glossary_rows()
    assert len(rows) >= 30, sorted(rows)
    assert {"stato", "ultimo_cambio", "fuori", "integrazione"} <= set(rows)


def test_stessi_campi_nei_due_versi():
    rows = glossary_rows()
    assert not set(FIELDS) - set(rows), (
        f"nel modulo e non nel glossario: {sorted(set(FIELDS) - set(rows))}")
    assert not set(rows) - set(FIELDS), (
        f"nel glossario e non nel modulo: {sorted(set(rows) - set(FIELDS))}")


def test_stessi_proprietari_e_stessi_nomi_tolti():
    rows = glossary_rows()
    for name, field in FIELDS.items():
        owners, replaced = rows[name]
        assert field.owners == owners, (name, sorted(field.owners), sorted(owners))
        assert field.replaces == replaced, (name, sorted(field.replaces), sorted(replaced))
