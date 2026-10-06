"""Il catalogo degli strumenti, misurato e dichiarato una volta (Tappa 5, Task 1).

Tre cancelli, tutti sullo stesso oggetto: cio' che il modello legge per primo
a ogni giro.

1. **Il peso.** Il catalogo e' il primo pezzo del prompt e si paga a ogni
   giro, sulla catena e sul ponte. Misurato il 05/10/2026 su `5bce65d`:
   **32.853** caratteri (la somma, strumento per strumento, del JSON che la
   fotografia delle porte salva nella sua porta `catalogo`). La soglia e' il
   valore misurato al commit di partenza della tappa e puo' solo SCENDERE: chi
   toglie caratteri la abbassa nello stesso commit, chi ne aggiunge deve
   prima toglierne altrove (spec dello sprint, R18; a fine tappa <= 32.425).
2. **Nessuna tabella a mano.** Ogni strumento e' dichiarato in UNA riga della
   tabella (`tools.TOOLS`); l'elenco delle definizioni, i gestori, le risorse
   e il soffitto si CHIEDONO alla riga. Una seconda lista indicizzata per nome
   di strumento dentro `tools.py` e' il doppione D-39.
3. **La derivazione non si e' rotta.** Un insieme di strumenti improvvisamente
   piccolo e' un cancello che sembra vivo e non guarda piu' niente: si
   confronta con quante definizioni `*_TOOL_DEF` il modulo dichiara, contate
   sul sorgente e non scritte qui.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from hiris.app.home_space import tools
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS

_SOURCE = Path(tools.__file__).read_text(encoding="utf-8")

# Misurata il 05/10/2026 su `5bce65d` (Tappa 5, piano: «Misurato prima di
# disegnare»). Scende a ogni task che toglie caratteri, mai sale. 06/10/2026
# (attori, Task 4.3): il campo `livello` di `propose` entra, e la frase che
# ripeteva i vocabolari di `gesto` e `dominio` esce -- due caratteri in meno.
CATALOG_CEILING = 32851


def catalog_chars(definitions) -> int:
    """I caratteri del catalogo: la somma del JSON di ogni definizione, nella
    forma in cui la salva la porta `catalogo` di `scripts/fotografia_porte.py`
    (`ensure_ascii=False`: le lettere accentate contano uno)."""
    return sum(len(json.dumps(definition, ensure_ascii=False)) for definition in definitions)


def test_il_catalogo_non_supera_la_soglia():
    """Mutazione ESEGUITA il 05/10/2026: un carattere in piu' nella
    descrizione di `cancel` -- rossa con «catalogo: 32854 > soglia 32853»."""
    size = catalog_chars(KNOWLEDGE_TOOLS)
    assert size <= CATALOG_CEILING, f"catalogo: {size} > soglia {CATALOG_CEILING}"


def _tool_definition_names() -> set[str]:
    """I nomi delle costanti `*_TOOL_DEF` assegnate a livello di modulo in
    `tools.py`, chiesti al sorgente."""
    return set(re.findall(r"^([A-Z_]+_TOOL_DEF)\s*=", _SOURCE, flags=re.MULTILINE))


def test_la_derivazione_vede_ogni_definizione_del_modulo():
    """Il catalogo non e' vuoto, e ha almeno tante voci quante definizioni
    `*_TOOL_DEF` il modulo dichiara: una definizione scritta e non messa in
    tabella non arriva al modello, e un catalogo improvvisamente piccolo
    spegnerebbe in silenzio i cancelli che lo leggono."""
    declared = _tool_definition_names()
    assert len(declared) >= 10, f"il sorgente dichiara solo {sorted(declared)}"
    names = [definition["name"] for definition in KNOWLEDGE_TOOLS]
    assert len(names) == len(set(names)), f"nomi ripetuti nel catalogo: {names}"
    assert len(names) >= len(declared), (
        f"il catalogo ha {len(names)} strumenti, il modulo dichiara "
        f"{len(declared)} definizioni: {sorted(declared)}")


def _hand_tables(tree: ast.AST, tool_names: set[str]) -> list[str]:
    """Le tabelle scritte a mano per nome di strumento: un dizionario con
    almeno due chiavi che sono nomi di strumento, o un elenco di almeno due
    costanti `*_TOOL_DEF` nude."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [key.value for key in node.keys
                    if isinstance(key, ast.Constant) and key.value in tool_names]
            if len(keys) >= 2:
                found.append(f"riga {node.lineno}: dizionario per nome ({', '.join(keys)})")
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            bare = [element.id for element in node.elts
                    if isinstance(element, ast.Name) and element.id.endswith("_TOOL_DEF")]
            if len(bare) >= 2:
                found.append(f"riga {node.lineno}: elenco di definizioni ({', '.join(bare)})")
    return found


def test_nessuna_tabella_a_mano_per_nome_di_strumento():
    """D-39: l'elenco delle definizioni, la mappa nome -> gestore e la mappa
    nome -> risorsa erano tre tabelle scritte a mano, da tenere d'accordo da
    sole. Dalla tabella degli strumenti si chiedono alla riga.

    I nomi si chiedono al catalogo, non si scrivono qui. Rossa prima del
    Task 2 (05/10/2026), con le tre tabelle nominate per riga."""
    tool_names = {definition["name"] for definition in KNOWLEDGE_TOOLS}
    found = _hand_tables(ast.parse(_SOURCE), tool_names)
    assert not found, "tabelle a mano in home_space/tools.py:\n" + "\n".join(found)
