"""Gli archivi SQLite: un idioma delle migrazioni, scritto una volta (G-13).

Fino alla Tappa 8 il gradino delle migrazioni era gia' unico
(`storage.init_schema`), ma l'idioma dentro ogni gradino -- `PRAGMA
table_info` e poi un `ALTER TABLE ... ADD COLUMN` per colonna -- era
ricopiato in nove archivi (venticinque occorrenze, misurate il 07/10/2026).
Adesso vive in `storage.add_missing_columns`, e questo cancello impedisce che
torni: **nessun `PRAGMA table_info` fuori da `storage.py`**, se non quelli che
`archivi_eccezioni.json` ammette per iscritto, col conto e la ragione.

**Il conto e' esatto in tutte e due le direzioni.** Un'occorrenza in piu' e'
l'idioma che rientra; una in meno e' un'eccezione guarita, che esce
dall'elenco nello stesso commit. E il cancello deve vedere l'occorrenza di
`storage.py` stessa: se non la vede, ha smesso di guardare.

Si contano i letterali del programma, anche dentro una f-string; i docstring
no -- raccontano l'idioma, non lo eseguono.
"""
import ast
import json
import pathlib
import sqlite3

import pytest

from hiris.app import storage

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
EXCEPTIONS = json.loads((ROOT / "tests" / "archivi_eccezioni.json").read_text(
    encoding="utf-8"))
PRAGMA = "PRAGMA table_info"
#: La casa dell'idioma: chiesta al modulo che lo definisce, non scritta.
HOME = pathlib.Path(storage.__file__).resolve().relative_to(ROOT).as_posix()


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                found.add(id(first.value))
    return found


def literal_count(tree: ast.AST, needle: str) -> int:
    """Quante volte `needle` compare nei letterali di `tree`, docstring
    esclusi. Un pezzo di f-string e' un letterale come gli altri."""
    skip = _docstrings(tree)
    return sum(node.value.count(needle) for node in ast.walk(tree)
               if isinstance(node, ast.Constant) and isinstance(node.value, str)
               and id(node) not in skip)


def _product() -> dict[str, ast.AST]:
    return {path.relative_to(ROOT).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
            for path in sorted(APP.rglob("*.py"))}


def pragma_sites(trees: dict[str, ast.AST]) -> dict[str, int]:
    counts = {where: literal_count(tree, PRAGMA) for where, tree in trees.items()}
    return {where: n for where, n in counts.items() if n}


def pragma_violations(sites: dict[str, int],
                      exceptions: dict | None = None) -> list[str]:
    entries = EXCEPTIONS["pragma-table-info"] if exceptions is None else exceptions
    admitted = {where: entry["conta"] for where, entry in entries.items()}
    problems = []
    for where, n in sorted(sites.items()):
        if where == HOME:
            continue
        allowed = admitted.get(where, 0)
        if n > allowed:
            problems.append(f"{where}: {n} `{PRAGMA}` ({allowed} ammessi) -- "
                            "si usa `storage.add_missing_columns`")
    for where, allowed in sorted(admitted.items()):
        if sites.get(where, 0) < allowed:
            problems.append(f"{where}: ammessi {allowed}, ne restano "
                            f"{sites.get(where, 0)} -- l'eccezione guarita esce "
                            "da `archivi_eccezioni.json`")
    return problems


def test_nessun_pragma_table_info_fuori_da_storage():
    """Mutazione ESEGUITA (08/10/2026): rimessa in `journal._migration_3` la
    lettura `PRAGMA table_info(esecuzioni)` con l'`ALTER` a mano -- rossa,
    «hiris/app/action/journal.py: 1 `PRAGMA table_info` (0 ammessi)»."""
    sites = pragma_sites(_product())
    assert HOME in sites, (
        "il cancello non vede piu' l'occorrenza di storage.py: la derivazione "
        "si e' rotta, e un cancello che non guarda niente resta verde")
    assert not pragma_violations(sites), pragma_violations(sites)


def test_ogni_eccezione_porta_la_sua_ragione():
    for where, entry in EXCEPTIONS["pragma-table-info"].items():
        assert entry.get("ragione"), f"{where}: ammesso senza una ragione scritta"


def test_il_cancello_vede_la_f_string_e_salta_il_docstring():
    fake = ast.parse(
        '"""Un modulo che racconta PRAGMA table_info nel docstring."""\n'
        't = "x"\n'
        'conn.execute(f"PRAGMA table_info({t})")\n')
    assert literal_count(fake, PRAGMA) == 1


def test_un_eccezione_guarita_e_un_rosso():
    """L'elenco puo' solo accorciarsi: un file ammesso che ha smesso di usare
    l'idioma esce dall'elenco nello stesso commit. L'elenco vero e' vuoto
    dalla Tappa 8 (Task 5: `mind/store.py` e' passato a `storage`), quindi
    l'eccezione qui e' finta."""
    finta = {"hiris/app/x.py": {"conta": 2, "ragione": "prova"}}
    assert pragma_violations({HOME: 1}, finta) == [(
        "hiris/app/x.py: ammessi 2, ne restano 0 -- l'eccezione guarita "
        "esce da `archivi_eccezioni.json`")]


# ---------------------------------------------------------------------------
# Il comportamento dell'aiuto, sull'archivio vero.
# ---------------------------------------------------------------------------


def _columns(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_le_colonne_mancanti_si_aggiungono_e_le_presenti_no(tmp_path):
    conn = storage.connect(str(tmp_path / "a.db"))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, gia TEXT)")
    storage.add_missing_columns(conn, "t", {"gia": "TEXT", "nuova": "REAL",
                                            "conto": "INTEGER NOT NULL DEFAULT 0"})
    assert _columns(conn, "t") == ["id", "gia", "nuova", "conto"]
    # La seconda volta non c'e' niente da fare, e niente solleva.
    storage.add_missing_columns(conn, "t", {"nuova": "REAL"})
    assert _columns(conn, "t") == ["id", "gia", "nuova", "conto"]


def test_l_indice_dopo_le_migrazioni(tmp_path):
    """`after_sql` gira DOPO le migrazioni: un indice su una colonna che la
    migrazione aggiunge, su un archivio vecchio, non fa fallire l'apertura.

    Mutazione ESEGUITA (08/10/2026): `after_sql` eseguito prima del giro
    delle migrazioni -- rossa, `no such column: filo`."""
    path = str(tmp_path / "b.db")
    old = storage.connect(path)
    storage.init_schema(old, "CREATE TABLE IF NOT EXISTS t (id INTEGER);", version=1)
    old.execute("INSERT INTO t VALUES (1)")
    old.commit()
    old.close()

    conn = storage.connect(path)
    storage.init_schema(
        conn, "CREATE TABLE IF NOT EXISTS t (id INTEGER, filo TEXT);", version=2,
        migrations={2: lambda c: storage.add_missing_columns(c, "t", {"filo": "TEXT"})},
        after_sql="CREATE INDEX IF NOT EXISTS idx_t_filo ON t(filo)")
    assert "filo" in _columns(conn, "t")
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type='index' "
                        "AND name='idx_t_filo'").fetchone()[0] == 1
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert conn.execute("SELECT id FROM t").fetchall()[0][0] == 1


def test_after_sql_e_una_frase_sola(tmp_path):
    conn = storage.connect(str(tmp_path / "c.db"))
    # `ProgrammingError` dalla 3.12, `Warning` prima.
    with pytest.raises((sqlite3.ProgrammingError, sqlite3.Warning)):
        storage.init_schema(conn, "CREATE TABLE IF NOT EXISTS t (id INTEGER);",
                            version=1, after_sql="SELECT 1; SELECT 2")


def test_la_ricostruzione_toglie_la_colonna_e_tiene_righe_e_indici(tmp_path):
    """`storage.rebuild_table`: la colonna esce, le righe e gli indici
    restano, e un passo che fallisce lascia la tabella com'era."""
    conn = storage.connect(str(tmp_path / "d.db"))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, tiene TEXT, via TEXT)")
    conn.execute("CREATE INDEX idx_t_tiene ON t(tiene)")
    conn.execute("INSERT INTO t VALUES (1, 'a', 'x')")
    conn.commit()
    storage.rebuild_table(
        conn, "t", "CREATE TABLE t (id INTEGER PRIMARY KEY, tiene TEXT)",
        ("id", "tiene"), indexes=("CREATE INDEX IF NOT EXISTS idx_t_tiene ON t(tiene)",))
    conn.commit()
    assert _columns(conn, "t") == ["id", "tiene"]
    assert conn.execute("SELECT id, tiene FROM t").fetchall()[0][:] == (1, "a")
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type='index' "
                        "AND name='idx_t_tiene'").fetchone()[0] == 1

    with pytest.raises(sqlite3.OperationalError):
        storage.rebuild_table(conn, "t", "CREATE TABLE t (id INTEGER PRIMARY KEY)",
                              ("id", "manca"))
    assert _columns(conn, "t") == ["id", "tiene"]
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1
