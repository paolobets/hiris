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


# ── Scritture fuori dalle tabelle del proprio modulo ────────────────────────


def test_scrittura_verso_la_tabella_di_un_altro_modulo(tmp_path):
    """Un file che scrive una tabella che non dichiara e' un reperto.

    Mutazione che la fa arrossire: in `censisci_scritture`, cambiare
    `if tabella in dichiarate: continue` in `continue` incondizionato — cioe'
    il controllo che guarda ma non denuncia mai.
    """
    _scrivi(tmp_path, "queue.py", '''
db.execute("CREATE TABLE IF NOT EXISTS reasoning_jobs (id INTEGER)")
db.execute("INSERT INTO reasoning_jobs (id) VALUES (1)")
db.execute("UPDATE cambi SET visto = 1 WHERE id = ?", (1,))
''')
    reperti = censimento.censisci_scritture([tmp_path / "queue.py"])
    assert [(r.categoria, r.nome) for r in reperti] == [
        ("scrittura-fuori-schema", "cambi")]


def test_scrittura_verso_la_propria_tabella_non_e_un_reperto(tmp_path):
    """Chi scrive solo cio' che dichiara non si segnala.

    Mutazione: in `_schema_scritture`, smettere di raccogliere `_RE_CREATE`
    (schema sempre vuoto) — ogni scrittura del prodotto diventerebbe un
    reperto, ed e' il modo piu' facile di rendere lo strumento non credibile.
    """
    _scrivi(tmp_path, "store.py", '''
db.execute("CREATE TABLE IF NOT EXISTS promesse (id INTEGER, stato TEXT)")
db.execute("INSERT INTO promesse (id) VALUES (1)")
db.execute("UPDATE promesse SET stato = 'fatta' WHERE id = 1")
db.execute("DELETE FROM promesse WHERE id = 1")
''')
    assert censimento.censisci_scritture([tmp_path / "store.py"]) == []


def test_una_query_spezzata_su_piu_righe_si_legge_ricomposta(tmp_path):
    """Il SQL si analizza sul letterale ricomposto, non riga per riga.

    Nessuna delle due righe di questa query, presa da sola, ha la forma di una
    scrittura: chi guardasse il sorgente riga per riga non vedrebbe niente.

    Mutazione: in `_letterali_codice`, tenere solo i letterali che stanno su
    una riga sola (`n.lineno == n.end_lineno`) — la concatenazione implicita
    sparisce e il reperto con lei.
    """
    _scrivi(tmp_path, "handler.py", '''
db.execute(
    "INSERT INTO "
    "cambi (id, valore) VALUES (?, ?)",
    (1, 2),
)
''')
    reperti = censimento.censisci_scritture([tmp_path / "handler.py"])
    assert [(r.categoria, r.nome) for r in reperti] == [
        ("scrittura-fuori-schema", "cambi")]


def test_lo_schema_citato_in_una_docstring_non_dichiara_niente(tmp_path):
    """Una docstring che CITA un CREATE TABLE non rende il file padrone.

    E' il caso vero di `mind/store.py`, che nel suo docstring spiega a parole
    che «`CREATE TABLE IF NOT EXISTS` non tocca una tabella che esiste gia'».
    Contarlo come schema non produce un falso positivo: ne ASSOLVE uno, e un
    controllo che tace sul file con sei tabelle e' peggio di uno rumoroso.

    Mutazione: in `_letterali_codice`, restituire tutti i letterali senza
    escludere le docstring — il file risulterebbe padrone di `promesse` e il
    reperto sparirebbe.
    """
    _scrivi(tmp_path, "handler.py", '''
"""Questo modulo NON possiede le promesse.

Chi le possiede fa CREATE TABLE promesse (id INTEGER); qui non si fa.
"""
db.execute("INSERT INTO promesse (id) VALUES (1)")
''')
    reperti = censimento.censisci_scritture([tmp_path / "handler.py"])
    assert [(r.categoria, r.nome) for r in reperti] == [
        ("scrittura-fuori-schema", "promesse")]


def test_una_scrittura_citata_in_una_docstring_non_e_una_scrittura(tmp_path):
    """Documentare una INSERT non e' eseguirla.

    Mutazione: la stessa di sopra (non escludere le docstring da
    `_letterali_codice`) — qui fa comparire un reperto che non esiste.
    """
    _scrivi(tmp_path, "lettore.py", '''
def leggi(db):
    """Il gemello di questa funzione fa INSERT INTO altrui (id) VALUES (1)."""
    return db.execute("SELECT id FROM altrui").fetchall()
''')
    assert censimento.censisci_scritture([tmp_path / "lettore.py"]) == []


def test_un_nome_di_tabella_composto_a_runtime_non_si_tace(tmp_path):
    """Cio' che il rilevatore non sa leggere si dichiara, non si salta.

    Mutazione: in `_schema_scritture`, restituire sempre `[]` al posto di
    `dinamiche` — la scrittura invisibile tornerebbe a sparire in silenzio,
    che e' il difetto peggiore di uno strumento di lettura.
    """
    _scrivi(tmp_path, "generico.py", '''
def salva(db, tabella, riga):
    db.execute(f"INSERT INTO {tabella} (id) VALUES (?)", (riga,))
''')
    reperti = censimento.censisci_scritture([tmp_path / "generico.py"])
    assert [r.categoria for r in reperti] == ["scrittura-non-concludibile"]
    assert censimento.COPERTURA_SCRITTURE["dinamiche"] == 1


def test_la_copertura_delle_scritture_viene_dichiarata(tmp_path):
    """Quante scritture sono state guardate, e in quanti file con uno schema.

    Senza questo numero «zero reperti» direbbe la stessa cosa se il rilevatore
    avesse esaminato diciannove scritture o nessuna.

    Mutazione: in `censisci_scritture`, non aggiornare `COPERTURA_SCRITTURE`
    (togliere la chiamata a `.update(...)`) — il rapporto perderebbe la riga e
    questa prova arrossisce sul KeyError.
    """
    _scrivi(tmp_path, "store.py", '''
db.execute("CREATE TABLE IF NOT EXISTS promesse (id INTEGER)")
db.execute("INSERT INTO promesse (id) VALUES (1)")
db.execute("DELETE FROM promesse WHERE id = 1")
''')
    _scrivi(tmp_path, "muto.py", "VALORE = 1\n")
    censimento.censisci_scritture([tmp_path / "store.py", tmp_path / "muto.py"])
    assert censimento.COPERTURA_SCRITTURE["schema_atteso"] == 1
    # UNA, non due: il conto e' per TABELLA per file, non per statement, e il
    # rapporto lo chiama «tabelle scritte» proprio per questo (correzione
    # della revisione indipendente, 12/09/2026 -- prima diceva «scritture SQL
    # esaminate», che e' un altro numero).
    assert censimento.COPERTURA_SCRITTURE["scritture"] == 1
    assert censimento.COPERTURA_SCRITTURE["illeggibili"] == 0


def test_un_file_non_parsabile_non_ferma_le_scritture_e_si_conta(tmp_path):
    """Un file illeggibile non e' un file pulito: i due esiti restano distinti.

    Mutazione: in `_schema_scritture`, far restituire `(set(), {}, [])` al
    posto di `None` quando `ast.parse` solleva — l'illeggibile si travestirebbe
    da file senza scritture e il conteggio resterebbe a zero.
    """
    _scrivi(tmp_path, "rotto.py", "def (:\n")
    _scrivi(tmp_path, "sano.py", '''
db.execute("CREATE TABLE IF NOT EXISTS coda (id INTEGER)")
db.execute("INSERT INTO coda (id) VALUES (1)")
''')
    reperti = censimento.censisci_scritture(
        [tmp_path / "rotto.py", tmp_path / "sano.py"])
    assert reperti == []
    assert censimento.COPERTURA_SCRITTURE["illeggibili"] == 1


# ── Il registro delle operazioni ────────────────────────────────────────────

#: Un registro finto con la stessa FORMA di quello vero: la chiave e' il
#: nome di dominio, e l'operazione porta l'esecutore in `run`. Prima del
#: 12/09/2026 i valori erano `None`, e con quelli il ramo che legge il nome
#: dell'esecutore non si esercitava affatto.
_REGISTRO_FINTO = '''
class _Finta:
    def __init__(self, esecutore):
        self.run = esecutore


def _sum_period(serie):
    return sum(serie)


def _count_events(serie):
    return len(serie)


REGISTRY = {"somma_periodo": _Finta(_sum_period),
            "conta_eventi": _Finta(_count_events)}
'''


def _registro(base: Path, testo: str = _REGISTRO_FINTO) -> Path:
    return _scrivi(base, "mind/operations.py", testo)


def test_una_operazione_reimplementata_fuori_dal_registro(tmp_path):
    """Una funzione omonima di un'operazione, in un altro modulo, e' un reperto.

    Mutazione: in `censisci_operazioni`, svuotare `cercati` subito prima del
    ciclo sui file (`cercati = {}`) — non troverebbe piu' niente, e il cancello
    tornerebbe a essere una buona intenzione.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "facts.py", '''
def somma_periodo(serie):
    return sum(serie)
''')
    reperti = censimento.censisci_operazioni([tmp_path / "facts.py"], reg)
    assert [(r.categoria, r.nome) for r in reperti] == [
        ("operazione-fuori-dal-registro", "somma_periodo")]


def test_anche_il_nome_INGLESE_dell_esecutore_e_un_doppione(tmp_path):
    """Un'operazione ha due nomi, e cercarne uno solo lascerebbe passare il
    doppione piu' probabile.

    Il nome di dominio e' italiano (`somma_periodo`, la chiave del registro:
    e' cosi' che il proprietario chiama quel conto); la funzione che lo esegue
    e' inglese come tutto il codice dell'ambito `mind` (`_sum_period`). Chi
    riscrive quel conto in un altro modulo **lo chiamera' in inglese**, come il
    resto del suo file -- e prima del 12/09/2026 il censimento non l'avrebbe
    visto, perche' guardava soltanto la chiave.

    Mutazione ESEGUITA: in `_nomi_registro`, togliere il giro che aggiunge
    `esecutore` — questa prova va rossa e le altre restano verdi, che e'
    esattamente il buco che aveva.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "facts.py", """
def sum_period(serie):
    return sum(serie)
""")
    reperti = censimento.censisci_operazioni([tmp_path / "facts.py"], reg)
    assert [(r.categoria, r.nome) for r in reperti] == [
        ("operazione-fuori-dal-registro", "sum_period")]


def test_le_operazioni_contate_sono_le_OPERAZIONI_non_i_nomi_cercabili(tmp_path):
    """Il rapporto dice quante operazioni ha il registro, e sono due qui.

    I nomi cercabili sono quattro (due di dominio piu' due esecutori): contarli
    direbbe un registro grande il doppio del vero -- un numero non misurato
    scritto come misurato, nel programma che esiste apposta per trovarne.

    Mutazione ESEGUITA: rimettere `len(nomi)` al posto di
    `len(set(nomi.values()))` — il conto sale a 4 e questa prova arrossisce.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "facts.py", "def niente():\n    return None\n")
    censimento.censisci_operazioni([tmp_path / "facts.py"], reg)
    assert censimento.COPERTURA_REGISTRO["operazioni"] == 2


def test_il_nome_preceduto_da_underscore_e_lo_stesso_doppione(tmp_path):
    """`_somma_periodo` e' la forma con cui il registro stesso implementa, e un
    doppione la copia: va vista come il nome nudo.

    Mutazione: in `censisci_operazioni`, togliere la riga
    `cercati[f"_{nome}"] = nome` — la forma privata smetterebbe di essere vista,
    ed e' proprio quella che un'estrazione mal fatta lascia indietro.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "facts.py", '''
def _somma_periodo(serie):
    return sum(serie)
''')
    reperti = censimento.censisci_operazioni([tmp_path / "facts.py"], reg)
    assert [r.nome for r in reperti] == ["_somma_periodo"]


def test_il_modulo_del_registro_non_denuncia_se_stesso(tmp_path):
    """L'implementazione vera sta nel registro: segnalarla sarebbe il rumore
    sano che seppellisce la rotta.

    Mutazione: in `censisci_operazioni`, togliere il `continue` che salta il
    file del registro — ogni operazione del prodotto diventerebbe un reperto.
    """
    reg = _registro(
        tmp_path,
        "def _somma_periodo(serie):\n    return sum(serie)\n\n\n" + _REGISTRO_FINTO,
    )
    assert censimento.censisci_operazioni([reg], reg) == []


def test_una_funzione_che_il_registro_non_conosce_non_e_un_reperto(tmp_path):
    """La regola e' sui nomi del registro, non su tutte le funzioni.

    Mutazione: in `censisci_operazioni`, sostituire `cercati.get(nome)` con
    `nome` (cioe' segnalare qualunque funzione) — ottocento reperti falsi.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "facts.py", "def media_periodo(serie):\n    return 0\n")
    assert censimento.censisci_operazioni([tmp_path / "facts.py"], reg) == []


def test_il_nome_dentro_una_stringa_non_e_una_definizione(tmp_path):
    r"""Si guardano le definizioni con l'AST, non con una regex sul testo.

    Questo file NON definisce `somma_periodo`: la nomina dentro un letterale,
    su una riga che comincia con `def`. Una regex `^\s*def (\w+)` in modalita'
    multilinea la prenderebbe per una definizione, e il rilevatore
    segnalerebbe la propria documentazione.

    Mutazione: in `_funzioni`, sostituire la visita dell'AST con
    `[(n, 1) for n in re.findall(r"^\s*(?:async\s+)?def\s+(\w+)", testo, re.M)]`
    — la prova arrossisce con un reperto inventato.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "documentazione.py", '''
ESEMPIO = """
def somma_periodo(serie):
    return sum(serie)
"""
''')
    assert censimento.censisci_operazioni([tmp_path / "documentazione.py"], reg) == []


def test_un_metodo_omonimo_dentro_una_classe_e_un_doppione(tmp_path):
    """Nascondere l'implementazione dentro una classe non la sposta nel registro.

    Mutazione: in `_funzioni`, passare da `ast.walk(albero)` a `albero.body` —
    si vedrebbero solo le funzioni di primo livello, e il modo piu' naturale di
    aggirare il cancello passerebbe inosservato.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "calcolatore.py", '''
class Calcolatore:
    def conta_eventi(self, serie):
        return len(serie)
''')
    reperti = censimento.censisci_operazioni([tmp_path / "calcolatore.py"], reg)
    assert [r.nome for r in reperti] == ["conta_eventi"]


def test_una_funzione_asincrona_omonima_e_un_doppione(tmp_path):
    """`async def` definisce quanto `def`.

    Mutazione: in `_funzioni`, togliere `ast.AsyncFunctionDef` dalla tupla
    dell'`isinstance` — meta' di questa codebase e' asincrona, e il cancello
    coprirebbe l'altra meta'.
    """
    reg = _registro(tmp_path)
    _scrivi(tmp_path, "handler.py", '''
async def conta_eventi(serie):
    return len(serie)
''')
    reperti = censimento.censisci_operazioni([tmp_path / "handler.py"], reg)
    assert [r.nome for r in reperti] == ["conta_eventi"]


def test_un_registro_vuoto_non_fa_fallire_e_lo_dichiara(tmp_path):
    """Il registro si sta costruendo: vuoto e' uno stato legittimo.

    Ma «zero reperti» con un registro vuoto e «zero reperti» con un registro
    pulito devono essere distinguibili, e a distinguerli e' il numero.

    Mutazione: in `censisci_operazioni`, togliere l'assegnazione di
    `COPERTURA_REGISTRO["operazioni"]` — il rapporto darebbe la stessa faccia
    ai due casi, ed e' il difetto che questo progetto insegue ovunque.
    """
    reg = _registro(tmp_path, "REGISTRY = {}\n")
    _scrivi(tmp_path, "facts.py", "def somma_periodo(serie):\n    return 0\n")
    assert censimento.censisci_operazioni([tmp_path / "facts.py"], reg) == []
    assert censimento.COPERTURA_REGISTRO["leggibile"] is True
    assert censimento.COPERTURA_REGISTRO["operazioni"] == 0


def test_un_registro_assente_si_distingue_da_un_registro_vuoto(tmp_path):
    """Non aver potuto leggere il registro non e' «il registro e' vuoto».

    Mutazione: in `_nomi_registro`, restituire `{}` invece di `None`
    quando il file non esiste — i due esiti collasserebbero in uno, e il
    rapporto direbbe «0 operazioni esaminate» di un registro mai aperto.
    """
    assente = tmp_path / "mind" / "operations.py"
    _scrivi(tmp_path, "facts.py", "def somma_periodo(serie):\n    return 0\n")
    assert censimento.censisci_operazioni([tmp_path / "facts.py"], assente) == []
    assert censimento.COPERTURA_REGISTRO["leggibile"] is False


def test_un_registro_che_esplode_non_ferma_il_censimento(tmp_path):
    """Caricare il registro lo ESEGUE: se scoppia, il censimento continua.

    Mutazione ESEGUITA: in `_nomi_registro`, restringere `except Exception`
    a `except ImportError` — il RuntimeError del registro in costruzione
    risale e il censimento intero muore, che e' esattamente il momento in cui
    dovrebbe reggere.
    """
    reg = _registro(tmp_path, 'raise RuntimeError("in costruzione")\n')
    _scrivi(tmp_path, "facts.py", "def somma_periodo(serie):\n    return 0\n")
    assert censimento.censisci_operazioni([tmp_path / "facts.py"], reg) == []
    assert censimento.COPERTURA_REGISTRO["leggibile"] is False


# ── `--cancello`: la disciplina diventa eseguita, non solo eseguibile ───────
#
# Rilievo dell'implementatore dei due controlli, 11/09/2026, e aveva ragione:
# la spec §15 chiede *«chi DIFENDE che il registro resti chiuso e che un modulo
# scriva solo le sue tabelle»*, e il piano cita la lezione del pin del
# Dockerfile -- *«una disciplina scritta non e' una disciplina eseguita»*. I due
# controlli rendevano la regola **misurabile**; questo la rende **imposta**.
#
# Allora il resto del censimento continuava a uscire 0: far fallire un rilascio
# per un simbolo senza chiamanti avrebbe fermato il progetto ogni settimana.
# Dal 02/10/2026 fermano anche il codice morto e le rotte senza chiamanti --
# vedi «Il cancello pieno» in fondo a questo file.


def test_il_cancello_esce_1_quando_una_regola_strutturale_e_rotta(monkeypatch):
    """Mutazione che la uccide: tornare sempre 0 anche in modalita' cancello.

    Mutazione ESEGUITA il 12/09/2026, vista rossa e ripristinata con
    l'editor: `return 1 if fermanti else 0` -> `return 0`.
    """
    import scripts.censimento as cens

    monkeypatch.setattr(cens, "censisci_scritture", lambda *a, **k: [
        cens.Reperto("scrittura-fuori-schema", "cambi",
                     "hiris/app/altro/modulo.py:12", "scrive in una tabella d'altri")])

    assert cens.run(cancello=True) == 1


def test_il_cancello_esce_0_quando_le_due_regole_sono_rispettate():
    """E' lo stato del repository oggi: zero reperti nelle due categorie
    strutturali. Se questa prova diventasse rossa, non sarebbe lei da
    aggiustare."""
    import scripts.censimento as cens

    assert cens.run(cancello=True) == 0


def test_senza_cancello_il_censimento_resta_uno_strumento_di_LETTURA(monkeypatch):
    """L'altra meta': i reperti che non sono violazioni strutturali -- un
    simbolo senza chiamanti, una rotta morta -- non devono fermare niente.
    Farli fermare trasformerebbe uno strumento che si consulta in uno che si
    aggira, e il progetto imparerebbe a passargli accanto.

    Mutazione che la uccide: far uscire 1 anche senza `cancello=True`.
    """
    import scripts.censimento as cens

    monkeypatch.setattr(cens, "censisci_scritture", lambda *a, **k: [
        cens.Reperto("scrittura-fuori-schema", "cambi",
                     "hiris/app/altro/modulo.py:12", "scrive in una tabella d'altri")])

    assert cens.run() == 0


# ── Il cancello pieno (Tappa 0, 02/10/2026) ─────────────────────────────────
#
# Fino a oggi fermavano solo due categorie strutturali; un simbolo orfano o una
# rotta senza chiamanti si leggevano e basta. Il blocco B della Tappa 0 ha
# portato quelle categorie a zero, salvo poche voci volute: adesso un orfano
# NUOVO ferma il push, e ogni voce voluta sta scritta con la sua ragione in
# `scripts/censimento_eccezioni.json`. L'elenco puo' solo accorciarsi:
# un'eccezione che non copre piu' niente ferma quanto un orfano.


def test_un_simbolo_orfano_nuovo_ferma_il_cancello():
    """Mutazione ESEGUITA: aggiunta in `hiris/app/config.py` la funzione
    `def _orfana_di_prova(): return 1` -- `python scripts/censimento.py
    --cancello` esce 1 e la nomina."""
    findings = [censimento.Reperto("simbolo-orfano", "_orfana", "hiris/app/x.py:1")]
    assert censimento.stopping(findings, exceptions={}) == findings


def test_una_variabile_d_ambiente_non_ferma():
    """Le variabili lette e mai esportate restano una lettura: una parte arriva
    da fuori (`SUPERVISOR_TOKEN`, `PATH`, `HOME`) e il rilevatore non le
    distingue dalle costanti travestite."""
    findings = [censimento.Reperto("envvar-mai-esportata", "PATH", "hiris/app/x.py:1")]
    assert censimento.stopping(findings, exceptions={}) == []


def test_un_eccezione_scritta_non_ferma_e_una_guarita_si():
    kept = censimento.Reperto("simbolo-solo-test", "actuator_round",
                              "hiris/app/server.py:2001")
    exceptions = {"simbolo-solo-test": {
        "actuator_round": "pausa voluta, decisione 10: lo riaccende lo strato 4"}}
    assert censimento.stopping([kept], exceptions=exceptions) == []
    assert censimento.stale_exceptions([kept], exceptions=exceptions) == []
    assert censimento.stale_exceptions([], exceptions=exceptions) == [
        ("simbolo-solo-test", "actuator_round")]


def test_un_eccezione_vale_solo_per_la_sua_categoria():
    """Un nome eccettuato come «usato solo dai test» non copre lo stesso nome
    il giorno in cui resta senza nessun chiamante: e' un fatto diverso, e
    vuole una ragione sua."""
    orphan = censimento.Reperto("simbolo-orfano", "actuator_round", "hiris/app/server.py:1")
    exceptions = {"simbolo-solo-test": {"actuator_round": "pausa voluta, decisione 10"}}
    assert censimento.stopping([orphan], exceptions=exceptions) == [orphan]


def test_un_eccezione_senza_ragione_non_si_legge(tmp_path):
    """Un'eccezione muta e' un permesso che nessuno puo' rivedere."""
    import json

    import pytest

    path = tmp_path / "eccezioni.json"
    path.write_text(json.dumps({"simbolo-orfano": {"_x": "si'"}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="_x"):
        censimento.read_exceptions(path)
    path.write_text(json.dumps({"categoria-inventata": {"_x": "una ragione abbastanza lunga"}}),
                    encoding="utf-8")
    with pytest.raises(SystemExit, match="categoria-inventata"):
        censimento.read_exceptions(path)


def test_le_eccezioni_versionate_coprono_esattamente_i_reperti_di_oggi():
    """Lo stato del repository: il cancello pieno passa, e nessuna eccezione e'
    rimasta a coprire qualcosa che non c'e' piu'. Se questa prova arrossisce
    per un reperto nuovo, non e' lei da aggiustare; se arrossisce per
    un'eccezione guarita, si toglie la riga dal file."""
    import scripts.censimento as cens

    assert cens.run(cancello=True) == 0


# ── Il cancello guarda TUTTI i file (revisione indipendente del 02/10/2026) ──


def test_una_funzione_col_solo_docstring_resta_leggibile_senza_il_docstring():
    """Tolto il docstring, una funzione il cui corpo era SOLO docstring restava
    senza corpo: il testo non si parsava piu', e l'intero file usciva dal
    censimento dei simboli senza che niente lo dicesse. Misurato dal revisore
    il 02/10/2026: quattro file, 121 definizioni fuori dal cancello, e due
    orfani veri nascosti li' dentro.

    Mutazione ESEGUITA: tolto il ramo che lascia `...` al posto del docstring
    -- rossa (`SyntaxError` sul testo ripulito)."""
    import ast

    source = ('class A:\n    def close(self):\n        """Niente da chiudere."""\n\n'
              'def f():\n    "una riga"\n\n'
              'def g():\n    """Con un corpo."""\n    return 1\n')
    clean = censimento._senza_docstring(source)
    ast.parse(clean)
    assert "Niente da chiudere" not in clean and "una riga" not in clean
    assert clean.count("\n") == source.count("\n"), "i numeri di riga non devono cambiare"


def test_nessun_file_del_prodotto_esce_dal_censimento_dei_simboli():
    """La derivazione non si e' rotta: un file che il rilevatore non sa
    leggere e' un file su cui il cancello non guarda niente, e resta verde."""
    import scripts.censimento as cens

    cens.run()
    assert cens.COPERTURA_SIMBOLI["illeggibili"] == 0, (
        f"{cens.COPERTURA_SIMBOLI['illeggibili']} file del prodotto non si leggono: "
        "le loro definizioni sono fuori dal cancello")
    assert cens.COPERTURA_SCRITTURE["illeggibili"] == 0, (
        f"{cens.COPERTURA_SCRITTURE['illeggibili']} file del prodotto non si leggono: "
        "le loro scritture sono fuori dal cancello")


# ── Le eccezioni non crescono da sole (revisione indipendente del 02/10/2026) ─

#: Le eccezioni AMMESSE, per nome, ognuna con la voce del registro che la
#: giustifica. L'unico errore del rilevatore (`get_config`, chiamato via
#: `getattr`) e' uscito il 06/10/2026: dal riallineamento il client manda
#: `get_config` anche sul websocket di lunga vita, e il rilevatore lo vede.
#: E' una lista di ammissione: non
#: ricopia il file delle eccezioni, enuncia il cancello. Chiude per difetto:
#: un'eccezione nuova, o una che cambia voce, si decide QUI, davanti a tutti.
#:
#: Prima c'erano un tetto e un prefisso libero («Falso positivo»), e bastava
#: scrivere quelle due parole -- o citare una voce aperta qualunque -- per
#: passare (eseguito dal revisore il 02/10/2026).
ADMITTED_EXCEPTIONS = {
    ("simbolo-solo-test", "actuator_round"): "M-20",
    ("simbolo-solo-test", "operable_domains"): "M-61",
    ("rotta-solo-test", "/api/misure"): "M-22",
}


def _written_exceptions():
    import scripts.censimento as cens

    raw = cens.read_exceptions(cens.ECCEZIONI)
    return [(category, name, reason)
            for category, names in raw.items() for name, reason in names.items()]


def test_le_eccezioni_del_censimento_hanno_un_tetto():
    """«L'elenco puo' solo accorciarsi» era prosa: una riga nuova con una
    ragione qualunque faceva passare il cancello e questa suite insieme
    (eseguito dal revisore il 02/10/2026). Adesso una riga in piu' arrossisce
    qui, e una in meno obbliga ad abbassare il tetto.

    Mutazione ESEGUITA: aggiunta a `censimento_eccezioni.json` l'eccezione
    «_orfana»: «serve, fidati di me.» -- rossa, col nome."""
    written = {(category, name) for category, name, _ in _written_exceptions()}
    assert written == set(ADMITTED_EXCEPTIONS), (
        "le eccezioni scritte non sono quelle ammesse -- in piu': "
        f"{sorted(written - set(ADMITTED_EXCEPTIONS))}; guarite, da togliere "
        f"dall'ammissione: {sorted(set(ADMITTED_EXCEPTIONS) - written)}")


def test_ogni_eccezione_cita_una_voce_aperta_del_registro_o_si_dichiara_falso_positivo():
    """Un'eccezione e' un debito: o e' scritta nel registro dei doppioni, come
    voce APERTA, o e' un errore del rilevatore e lo dice. Stessa forma di
    `test_fonte_unica.py`.

    Mutazioni ESEGUITE, tutte rosse col nome dell'eccezione: tolta «Voce
    M-61» dalla ragione di `operable_domains`; la stessa ragione riscritta
    «Serve. Voce X-12 del registro.» (aperta, ma un'altra); la ragione di
    `actuator_round` riscritta «Falso positivo: fidati di me, serve.»."""
    import re

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import registro

    still_open = {entry.id for entry in registro.read_entries(registro.REGISTER)
                  if not entry.closed}
    assert still_open, "il registro non ha voci aperte: la prova non guarda niente"
    loose = []
    for category, name, reason in _written_exceptions():
        expected = ADMITTED_EXCEPTIONS.get((category, name))
        cited = set(re.findall(r"\b[A-Z]-\d{2}\b", reason))
        if expected is None:
            if cited:
                loose.append(f"{category}/{name} (falso positivo che cita {sorted(cited)})")
        elif cited != {expected} or expected not in still_open:
            loose.append(f"{category}/{name} (cita: {sorted(cited) or 'niente'}, "
                         f"ammessa per {expected})")
    assert not loose, (
        "eccezioni che non citano una voce APERTA del registro e non si "
        "dichiarano falso positivo: " + "; ".join(loose))
