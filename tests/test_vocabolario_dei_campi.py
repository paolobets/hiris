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
from hiris.app.home_space.house_query import KINDS
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS

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


def _parameters(schema, found: set[str]) -> set[str]:
    if isinstance(schema, dict):
        for name, sub in (schema.get("properties") or {}).items():
            found.add(name)
            _parameters(sub, found)
        _parameters(schema.get("items"), found)
    return found


def _descriptions(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                yield value
            else:
                yield from _descriptions(value)
    elif isinstance(node, list):
        for value in node:
            yield from _descriptions(value)


def test_le_descrizioni_non_nominano_un_campo_tolto():
    """G102-1 (revisore, giro 102): la descrizione di `search` diceva ancora
    «una voce con `nascosta: true`» quando le voci portano gia' `fuori`. Il
    modello legge la descrizione e cerca un campo che non c'e' piu'.

    I nomi tolti si chiedono al vocabolario (`Field.replaces`), non si
    ricopiano. Restano ammessi i nomi che sono anche un parametro dello
    stesso strumento (il `tipo` di un'ancora di `remember` e' la colonna
    del ricordo, non un campo della resa) e i generi (`entita`).
    Mutazione ESEGUITA: rimettere «`nascosta: true`» nella descrizione di
    `search` -- rossa con `('search', 'nascosta')`."""
    retired = set().union(*(f.replaces for f in FIELDS.values())) - set(FIELDS) - set(KINDS)
    assert {"da_quando", "piattaforma", "nascosta"} <= retired, \
        "la derivazione dei nomi tolti si e' svuotata"
    named = []
    for tool in KNOWLEDGE_TOOLS:
        parameters = _parameters(tool["input_schema"], set())
        for text in _descriptions(tool):
            named.extend((tool["name"], word) for word in re.findall(r"`([a-z_]+)", text)
                         if word in retired and word not in parameters)
    assert not named, named
