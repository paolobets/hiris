"""Il filo negli archivi: una condizione, una lettura, una casa (B-52).

Quattro archivi portano il filo nelle stesse due colonne, `subject_key` ed
`entry_point`: le sessioni della chat, le promesse, le costruzioni, la coda del
ponte. Fino alla Tappa 6 (Task 2) la condizione «di questo filo» era scritta a
mano in dodici righe di tre file (misurato da questa stessa prova sul commit
`5bce65d`), e il filo si ricostruiva dalla riga in tre: una copia sola che
cambiasse -- un `IS` al posto di `=`, una colonna rinominata -- e un archivio
avrebbe risposto per un filo diverso dagli altri.

La casa e' `chat_thread.py`. Le prove chiedono al sorgente dove sta la
condizione: un archivio nuovo che la riscrivesse a mano entra nella prova
senza toccarla.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from hiris.app.chat_thread import (
    ChatThread,
    thread_condition,
    thread_from_columns,
    thread_params,
)

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
HOME = APP / "chat_thread.py"

#: La condizione scritta a mano: `subject_key = ? AND ...entry_point`, con o
#: senza alias. Un `SET subject_key = ?, entry_point = ?` (l'adozione delle
#: righe orfane) e' un'assegnazione, non una condizione, e non la prende.
_HANDWRITTEN_CONDITION = re.compile(r"subject_key\s*=\s*\?\s+AND\s+(\w+\.)?entry_point")
#: Il filo ricostruito a mano da una riga.
_HANDWRITTEN_ROW = re.compile(r"ChatThread\(\s*\w+\[\s*[\"']subject_key")


def _sources() -> list[Path]:
    return [p for p in sorted(APP.rglob("*.py")) if p != HOME]


def test_the_search_sees_the_four_stores():
    """Prova della derivazione: se la ricerca non vede piu' i quattro
    archivi, e' un cancello che sembra vivo e non guarda niente."""
    stores = {p.name for p in _sources()
              if "subject_key" in p.read_text(encoding="utf-8")}
    assert {"chat_store.py", "store.py", "revisions.py", "queue.py"} <= stores


def test_no_store_writes_the_thread_condition_by_hand():
    found = [f"{p.relative_to(APP)}:{n}"
             for p in _sources()
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if _HANDWRITTEN_CONDITION.search(line)]
    assert not found, (
        "la condizione del filo scritta a mano fuori da chat_thread.py "
        f"(usare `thread_condition`): {found}")


def test_no_store_rebuilds_the_thread_from_a_row_by_hand():
    found = [f"{p.relative_to(APP)}:{n}"
             for p in _sources()
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if _HANDWRITTEN_ROW.search(line)]
    assert not found, (
        "il filo ricostruito a mano da una riga fuori da chat_thread.py "
        f"(usare `thread_from_columns`): {found}")


def test_condition_and_params_select_exactly_the_thread():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (id TEXT, subject_key TEXT, entry_point TEXT)")
    paolo = ChatThread("persona:p", "pannello")
    conn.executemany("INSERT INTO t VALUES (?, ?, ?)", [
        ("mio", *thread_params(paolo)),
        ("altro ingresso", "persona:p", "firma"),
        ("altra persona", "persona:m", "pannello"),
        ("senza filo", *thread_params(None))])
    rows = conn.execute(f"SELECT id FROM t AS s WHERE {thread_condition('s')}",
                        thread_params(paolo)).fetchall()
    assert rows == [("mio",)]
    rows = conn.execute(f"SELECT id FROM t WHERE {thread_condition()}",
                        thread_params(paolo)).fetchall()
    assert rows == [("mio",)]


def test_a_row_without_thread_has_no_thread():
    assert thread_from_columns(None, None) is None
    assert thread_from_columns("persona:p", "pannello") == ChatThread("persona:p", "pannello")
