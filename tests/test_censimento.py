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
    assert "mqtt.host" in nomi
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


def test_envvar_letta_con_env_bool_e_mai_esportata(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh", 'export HIRIS_VIVA="1"\n')
    app = _scrivi(tmp_path, "app.py", '''
from .env_util import env_bool
a = env_bool("HIRIS_VIVA")
b = env_bool("HIRIS_MORTA", True)
''')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    nomi = {r.nome for r in reperti if r.categoria == "envvar-mai-esportata"}
    assert nomi == {"HIRIS_MORTA"}


def test_config_mancante_non_esplode(tmp_path):
    assert censimento.censisci_configurazione(
        tmp_path / "assente.yaml", tmp_path / "assente.sh", []
    ) == []


def test_opzione_letta_solo_da_run_sh_non_e_un_reperto(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", '''name: "HIRIS"
version: "1.0.0"
options:
  usata: ""
  fantasma: ""
schema:
  usata: str
''')
    run_sh = _scrivi(tmp_path, "run.sh",
                     "export FANTASMA=$(bashio::config 'fantasma' '')\n")
    app = _scrivi(tmp_path, "app.py", 'valore = opzioni.get("usata")\n')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    assert [r.nome for r in reperti if r.categoria == "opzione-mai-letta"] == []


def test_opzione_annidata_letta_in_forma_puntata(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh",
                     "export H=$(bashio::config 'mqtt.host' '')\n"
                     "export F=$(bashio::config 'fantasma' '')\n")
    app = _scrivi(tmp_path, "app.py", 'valore = opzioni.get("usata")\n')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    assert [r.nome for r in reperti if r.categoria == "opzione-mai-letta"] == []


def test_foglia_generica_non_e_salvata_da_una_citazione_estranea(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh", "export U=$(bashio::config 'usata' '')\n")
    app = _scrivi(tmp_path, "app.py", 'intestazioni = {"host": "esempio.it"}\n')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    nomi = {r.nome for r in reperti if r.categoria == "opzione-mai-letta"}
    assert "mqtt.host" in nomi


def test_il_contenitore_non_e_una_opzione(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh", "")
    reperti = censimento.censisci_configurazione(cfg, run_sh, [])
    nomi = {r.nome for r in reperti if r.categoria == "opzione-mai-letta"}
    assert "mqtt" not in nomi
    assert "mqtt.host" in nomi


def test_envvar_letta_solo_in_un_commento_non_conta(tmp_path):
    cfg = _scrivi(tmp_path, "config.yaml", _CONFIG_YAML)
    run_sh = _scrivi(tmp_path, "run.sh", "")
    app = _scrivi(tmp_path, "app.py", '# os.environ.get("HIRIS_COMMENTATA")\n')
    reperti = censimento.censisci_configurazione(cfg, run_sh, [app])
    assert [r.nome for r in reperti if r.categoria == "envvar-mai-esportata"] == []


def test_rotta_senza_chiamanti(tmp_path):
    app = _scrivi(tmp_path, "server.py", '''
app.router.add_get("/api/viva", h1)
app.router.add_post("/api/morta", h2)
''')
    fe = _scrivi(tmp_path, "pagina.js", 'fetch("api/viva")')
    reperti = censimento.censisci_rotte([app], [fe], [])
    assert [r.nome for r in reperti] == ["/api/morta"]


def test_rotta_chiamata_dai_soli_test_e_un_reperto(tmp_path):
    app = _scrivi(tmp_path, "server.py", 'app.router.add_get("/api/solo-test", h)')
    t = _scrivi(tmp_path, "test_x.py", 'await client.get("/api/solo-test")')
    reperti = censimento.censisci_rotte([app], [], [t])
    assert [r.categoria for r in reperti] == ["rotta-solo-test"]


def test_rotta_parametrica_si_cerca_per_prefisso(tmp_path):
    app = _scrivi(tmp_path, "server.py", 'app.router.add_get("/api/item/{id}", h)')
    fe = _scrivi(tmp_path, "pagina.js", 'fetch(`api/item/${x}`)')
    assert censimento.censisci_rotte([app], [fe], []) == []


def test_add_route_con_metodo_esplicito(tmp_path):
    app = _scrivi(tmp_path, "server.py", 'app.router.add_route("GET", "/api/vecchia", h)')
    reperti = censimento.censisci_rotte([app], [], [])
    assert [r.nome for r in reperti] == ["/api/vecchia"]


def test_rotta_non_parametrica_non_combacia_con_una_rotta_sorella(tmp_path):
    # /api/knowledge (non parametrica) non deve risultare viva per colpa di
    # /api/knowledge/pending, che e' una rotta sorella diversa: il match deve
    # avere un confine, non essere una sottostringa libera.
    app = _scrivi(tmp_path, "server.py", '''
app.router.add_post("/api/knowledge", handle_manual_add)
app.router.add_get("/api/knowledge/pending", handle_list_pending)
''')
    fe = _scrivi(tmp_path, "pagina.js", '''
fetch('api/knowledge/pending');
fetch('api/knowledge/' + id + '/approve');
''')
    reperti = censimento.censisci_rotte([app], [fe], [])
    nomi = {r.nome for r in reperti}
    assert "/api/knowledge" in nomi
    assert "/api/knowledge/pending" not in nomi


def test_rotta_nominata_solo_in_un_commento_resta_senza_chiamanti(tmp_path):
    app = _scrivi(tmp_path, "server.py", '''
app.router.add_get("/api/dismessa", h)
# la /api/dismessa non si usa piu', va tolta
''')
    reperti = censimento.censisci_rotte([app], [], [])
    assert [r.nome for r in reperti] == ["/api/dismessa"]


def test_funzione_senza_chiamanti(tmp_path):
    app = _scrivi(tmp_path, "modulo.py", '''
def viva():
    return 1

def morta():
    return 2

def usa():
    return viva()
''')
    reperti = censimento.censisci_simboli([app], [])
    nomi = {r.nome for r in reperti if r.categoria == "simbolo-orfano"}
    assert "morta" in nomi
    assert "viva" not in nomi


def test_funzione_usata_solo_dai_test(tmp_path):
    app = _scrivi(tmp_path, "modulo.py", "def solo_test():\n    return 1\n")
    t = _scrivi(tmp_path, "test_m.py", "def test_x():\n    assert solo_test() == 1\n")
    reperti = censimento.censisci_simboli([app], [t])
    assert [(r.categoria, r.nome) for r in reperti] == [("simbolo-solo-test", "solo_test")]


def test_simbolo_nominato_solo_in_un_commento_resta_orfano(tmp_path):
    app = _scrivi(tmp_path, "m.py", '''
def dismessa():
    pass

# `dismessa` e' tenuta solo come helper testato, non piu' chiamata da qui
''')
    reperti = censimento.censisci_simboli([app], [])
    assert [(r.categoria, r.nome) for r in reperti] == [("simbolo-orfano", "dismessa")]


def test_nome_ambiguo_si_salta(tmp_path):
    # A e B sono referenziate da main() apposta: altrimenti sarebbero due
    # classi davvero orfane per conto loro, ed estranee a cio' che il test
    # vuole verificare (che "salva", ambiguo fra le due classi, si salta).
    a = _scrivi(tmp_path, "a.py",
               "class A:\n    def salva(self):\n        pass\n\n"
               "def main():\n    return A()\n")
    b = _scrivi(tmp_path, "b.py",
               "class B:\n    def salva(self):\n        pass\n\n"
               "def main():\n    return B()\n")
    assert censimento.censisci_simboli([a, b], []) == []


def test_nome_citato_come_stringa_viene_segnalato(tmp_path):
    app = _scrivi(tmp_path, "modulo.py", '''
def forse_dinamica():
    return 1

CATALOGO = {"forse_dinamica": None}
''')
    reperti = censimento.censisci_simboli([app], [])
    assert len(reperti) == 1
    assert "dinamic" in reperti[0].nota


def test_dunder_e_ingressi_si_saltano(tmp_path):
    # C e' referenziata da main() apposta: altrimenti sarebbe una classe
    # davvero orfana per conto suo, ed estranea a cio' che il test vuole
    # verificare (che __init__ e main, come dunder e punto d'ingresso, si
    # saltano).
    app = _scrivi(tmp_path, "modulo.py", '''
class C:
    def __init__(self):
        pass

def main():
    return C()
''')
    assert censimento.censisci_simboli([app], []) == []


def test_file_con_errore_di_sintassi_non_ferma_il_censimento(tmp_path):
    rotto = _scrivi(tmp_path, "rotto.py", "def (:\n")
    buono = _scrivi(tmp_path, "buono.py", "def orfana():\n    pass\n")
    reperti = censimento.censisci_simboli([rotto, buono], [])
    assert [r.nome for r in reperti] == ["orfana"]


def test_il_file_con_il_bom_viene_letto(tmp_path):
    p = tmp_path / "conbom.py"
    p.write_bytes(b"\xef\xbb\xbfdef orfana_con_bom():\n    pass\n")
    reperti = censimento.censisci_simboli([p], [])
    assert [r.nome for r in reperti] == ["orfana_con_bom"]


def test_la_copertura_viene_registrata(tmp_path):
    app = _scrivi(tmp_path, "m.py", '''
def orfana():
    pass

class A:
    def salva(self):
        pass

class B:
    def salva(self):
        pass
''')
    censimento.censisci_simboli([app], [])
    copertura = censimento.COPERTURA_SIMBOLI
    assert copertura["ambigui"] == 1          # `salva`, definita due volte
    assert copertura["esaminati"] >= 3        # orfana, A, B
    assert copertura["illeggibili"] == 0


def test_un_file_illeggibile_viene_contato(tmp_path):
    rotto = _scrivi(tmp_path, "rotto.py", "def (:\n")
    buono = _scrivi(tmp_path, "buono.py", "def orfana():\n    pass\n")
    censimento.censisci_simboli([rotto, buono], [])
    assert censimento.COPERTURA_SIMBOLI["illeggibili"] == 1


def test_un_nome_di_tabella_composto_a_runtime_non_e_una_tabella_morta(tmp_path):
    """E' successo davvero, sulle sette tabelle dell'anagrafe: si scrivono per
    nome e si leggono con `SELECT * FROM {tabella}`. Il rilevatore le dava per
    morte, e fidandosi del report si sarebbe cancellata la casa intera."""
    _scrivi(tmp_path, "archivio.py", '''
TABELLE = ["aree", "entita"]

def crea(db):
    db.execute("CREATE TABLE aree (id TEXT)")
    db.execute("CREATE TABLE entita (id TEXT)")

def salva(db):
    db.execute("INSERT INTO aree (id) VALUES (?)", ("x",))

def leggi(db):
    for t in TABELLE:
        db.execute(f"SELECT * FROM {t}")
''')
    reperti = censimento.censisci_tabelle([tmp_path / "archivio.py"])
    assert {r.categoria for r in reperti} == {"tabella-non-concludibile"}
    assert sorted(r.nome for r in reperti) == ["aree", "entita"]


def test_un_file_senza_nomi_dinamici_conclude_ancora(tmp_path):
    """La prudenza vale per il file che compone i nomi, non per tutti."""
    _scrivi(tmp_path, "store.py", '''
db.execute("CREATE TABLE morta (id TEXT)")
db.execute("INSERT INTO morta (id) VALUES (1)")
''')
    reperti = censimento.censisci_tabelle([tmp_path / "store.py"])
    assert [r.categoria for r in reperti] == ["tabella-scritta-mai-letta"]


def test_una_rotta_nominata_in_una_docstring_non_e_viva(tmp_path):
    """19 rotte su 54 di questa codebase sono nominate in una docstring: erano
    esenti per sempre dal rilevatore, e non comparivano in NESSUNA categoria."""
    _scrivi(tmp_path, "server.py", '''
def avvia(app):
    """Registra le rotte. Vedi /api/dismessa per il caso della cartella."""
    app.router.add_get("/api/dismessa", h)
''')
    reperti = censimento.censisci_rotte([tmp_path / "server.py"], [], [])
    assert [r.nome for r in reperti] == ["/api/dismessa"]


def test_un_simbolo_nominato_solo_in_una_docstring_resta_orfano(tmp_path):
    _scrivi(tmp_path, "m.py", '''
def dismessa():
    pass

def altra():
    """Sostituisce `dismessa`, che non si usa piu'."""
    pass
''')
    reperti = censimento.censisci_simboli([tmp_path / "m.py"], [])
    assert "dismessa" in [r.nome for r in reperti]
