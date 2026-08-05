import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "censimento", Path(__file__).parent.parent / "scripts" / "censimento.py"
)
censimento = importlib.util.module_from_spec(_SPEC)
sys.modules["censimento"] = censimento
_SPEC.loader.exec_module(censimento)


def _scrivi(base: Path, nome: str, testo: str) -> Path:
    p = base / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(testo, encoding="utf-8")
    return p


def test_tabella_scritta_e_mai_letta(tmp_path):
    _scrivi(tmp_path, "store.py", '''
def crea(db):
    db.execute("CREATE TABLE insight (id INTEGER PRIMARY KEY, testo TEXT)")

def salva(db, testo):
    db.execute("INSERT INTO insight (testo) VALUES (?)", (testo,))
''')
    reperti = censimento.censisci_tabelle([tmp_path / "store.py"])
    categorie = {r.categoria: r for r in reperti}
    assert "tabella-scritta-mai-letta" in categorie
    assert categorie["tabella-scritta-mai-letta"].nome == "insight"


def test_tabella_letta_e_scritta_non_e_un_reperto(tmp_path):
    _scrivi(tmp_path, "store.py", '''
db.execute("CREATE TABLE memoria (id INTEGER)")
db.execute("INSERT INTO memoria (id) VALUES (1)")
db.execute("SELECT id FROM memoria")
''')
    assert censimento.censisci_tabelle([tmp_path / "store.py"]) == []


def test_tabella_mai_toccata(tmp_path):
    _scrivi(tmp_path, "store.py", 'db.execute("CREATE TABLE orfana (id INTEGER)")')
    reperti = censimento.censisci_tabelle([tmp_path / "store.py"])
    assert [r.categoria for r in reperti] == ["tabella-mai-toccata"]


def test_delete_from_non_conta_come_lettura(tmp_path):
    _scrivi(tmp_path, "store.py", '''
db.execute("CREATE TABLE coda (id INTEGER)")
db.execute("INSERT INTO coda (id) VALUES (1)")
db.execute("DELETE FROM coda WHERE id = 1")
''')
    reperti = censimento.censisci_tabelle([tmp_path / "store.py"])
    assert [r.categoria for r in reperti] == ["tabella-scritta-mai-letta"]


def test_from_minuscolo_di_un_import_non_conta_come_lettura(tmp_path):
    _scrivi(tmp_path, "store.py", '''
from history import qualcosa
db.execute("CREATE TABLE history (id INTEGER)")
db.execute("INSERT INTO history (id) VALUES (1)")
''')
    reperti = censimento.censisci_tabelle([tmp_path / "store.py"])
    assert [r.categoria for r in reperti] == ["tabella-scritta-mai-letta"]


def test_sql_dentro_un_commento_non_e_una_tabella(tmp_path):
    _scrivi(tmp_path, "store.py", '''
db.execute("CREATE TABLE vera (id INTEGER)")
db.execute("INSERT INTO vera (id) VALUES (1)")
db.execute("SELECT id FROM vera")
# il `CREATE TABLE IF NOT EXISTS` qui sopra basta anche per un archivio nuovo
''')
    assert censimento.censisci_tabelle([tmp_path / "store.py"]) == []


def test_cancelletto_dentro_una_stringa_non_e_un_commento(tmp_path):
    _scrivi(tmp_path, "store.py", '''
etichetta = "# CREATE TABLE finta (id INTEGER)"
db.execute("CREATE TABLE vera (id INTEGER)")
''')
    reperti = censimento.censisci_tabelle([tmp_path / "store.py"])
    assert sorted(r.nome for r in reperti) == ["finta", "vera"]


_CONFIG_YAML = '''name: "HIRIS"
version: "1.0.0"
options:
  usata: ""
  fantasma: ""
  mqtt:
    host: ""
schema:
  usata: str
'''


def test_opzione_mai_letta(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh", "#!/usr/bin/env bash\n")
    app = _scrivi(tmp_path, "app.py", 'valore = opzioni.get("usata")\n')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    nomi = {r.nome for r in reperti if r.categoria == "opzione-mai-letta"}
    assert "fantasma" in nomi
    assert "usata" not in nomi


def test_envvar_letta_e_mai_esportata(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh", 'export HIRIS_VIVA="1"\n')
    app = _scrivi(tmp_path, "app.py", '''
import os
a = os.environ.get("HIRIS_VIVA")
b = os.getenv("HIRIS_MORTA", "0")
c = os.environ["HIRIS_ALTRA"]
''')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    nomi = {r.nome for r in reperti if r.categoria == "envvar-mai-esportata"}
    assert nomi == {"HIRIS_MORTA", "HIRIS_ALTRA"}


def test_config_mancante_non_esplode(tmp_path):
    assert censimento.censisci_configurazione(
        tmp_path / "assente.yaml", tmp_path / "assente.sh", []
    ) == []
