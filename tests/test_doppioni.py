"""Lo strumento che caccia i doppioni deve saper trovarne uno, e saper tacere.

Un rilevatore che non trova niente passa tutti i giri ed e' inutile; uno che
trova tutto diventa rumore e viene ignorato. Queste prove verificano
ENTRAMBI i versi su casi costruiti a mano: si pianta il difetto e si controlla
che lo veda, si dichiara e si controlla che taccia.

E' la stessa disciplina che lo strumento chiede al codice che ispeziona.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from doppioni import (cerca_funzioni_gemelle, cerca_predefiniti,  # noqa: E402
                      cerca_regex, cerca_vocabolari_paralleli)


def _scrivi(cartella: Path, nome: str, testo: str) -> Path:
    p = cartella / nome
    p.write_text(testo, encoding="utf-8")
    return p


# --- le regex ------------------------------------------------------------

def test_trova_la_stessa_regex_in_due_file(tmp_path):
    a = _scrivi(tmp_path, "a.py", 'import re\nX = re.compile(r"^[a-z]+\\.[a-z]+$")\n')
    b = _scrivi(tmp_path, "b.py", 'import re\nY = re.compile(r"^[a-z]+\\.[a-z]+$")\n')
    reperti = cerca_regex([a, b])
    assert len(reperti) == 1
    assert len(reperti[0].dove) == 2


def test_la_stessa_regex_due_volte_nello_stesso_file_non_e_un_reperto(tmp_path):
    """Due usi nello stesso modulo si vedono leggendolo, e non possono
    divergere senza che chi tocca l'uno abbia l'altro sotto gli occhi. Il
    difetto e' la distanza."""
    a = _scrivi(tmp_path, "a.py",
                'import re\nX = re.compile(r"^ab+$")\nY = re.compile(r"^ab+$")\n')
    assert cerca_regex([a]) == []


def test_una_regex_dichiarata_non_si_segnala(tmp_path):
    """Il marcatore, e la ragione per cui esiste: senza, lo strumento
    ristamperebbe a ogni giro i doppioni voluti e diventerebbe la lista che
    dice sempre qualcosa -- il difetto n.1 del progetto, incarnato dallo
    strumento nato per cacciarlo."""
    a = _scrivi(tmp_path, "a.py",
                'import re\n# DOPPIONE DICHIARATO: guardia stretta, non una copia\n'
                'X = re.compile(r"^ab+$")\n')
    b = _scrivi(tmp_path, "b.py", 'import re\nY = re.compile(r"^ab+$")\n')
    assert cerca_regex([a, b]) == []


def test_il_marcatore_non_copre_tutto_il_file(tmp_path):
    """Un marcatore in cima non deve zittire un doppione trenta righe sotto:
    sarebbe un modo di spegnere lo strumento credendo di dichiarare una cosa
    sola."""
    lontano = ('# DOPPIONE DICHIARATO: qualcosa, in cima\n' + 'x = 1\n' * 30
               + 'import re\nX = re.compile(r"^ab+$")\n')
    a = _scrivi(tmp_path, "a.py", lontano)
    b = _scrivi(tmp_path, "b.py", 'import re\nY = re.compile(r"^ab+$")\n')
    assert len(cerca_regex([a, b])) == 1


# --- le funzioni gemelle -------------------------------------------------

_CORPO = '''def {nome}(x):
    y = x.strip().lower()
    if not y:
        return None
    return y
'''


def test_trova_due_funzioni_con_lo_stesso_corpo_e_nomi_diversi(tmp_path):
    """Il caso vero: `_dominio`, `_domain` e `_dominio_entita` erano tre nomi
    per una lettura sola."""
    a = _scrivi(tmp_path, "a.py", _CORPO.format(nome="pulisci"))
    b = _scrivi(tmp_path, "b.py", _CORPO.format(nome="normalizza"))
    reperti = cerca_funzioni_gemelle([a, b])
    assert len(reperti) == 1
    assert "pulisci" in reperti[0].nome and "normalizza" in reperti[0].nome


def test_due_funzioni_che_fanno_cose_diverse_non_sono_gemelle(tmp_path):
    """Il contrario, e serve quanto l'altra: senza, un rilevatore che
    accoppiasse tutto passerebbe la prova di sopra per il motivo sbagliato."""
    a = _scrivi(tmp_path, "a.py", _CORPO.format(nome="pulisci"))
    b = _scrivi(tmp_path, "b.py",
                'def somma(x):\n    y = x + 1\n    if y > 3:\n        return 0\n    return y\n')
    assert cerca_funzioni_gemelle([a, b]) == []


def test_una_funzione_di_una_riga_non_si_accoppia(tmp_path):
    """`return x` e `return y` sono la stessa forma per costruzione: sotto le
    due istruzioni si accoppierebbe mezza codebase. E' un limite VOLUTO, ed e'
    dichiarato in coda al rapporto."""
    a = _scrivi(tmp_path, "a.py", 'def uno(x):\n    return x.upper()\n')
    b = _scrivi(tmp_path, "b.py", 'def due(y):\n    return y.upper()\n')
    assert cerca_funzioni_gemelle([a, b]) == []


def test_la_docstring_non_conta(tmp_path):
    """Due funzioni gemelle con docstring diverse restano gemelle: la prosa e'
    preziosa e non e' il corpo."""
    a = _scrivi(tmp_path, "a.py",
                'def uno(x):\n    """Una cosa."""\n    y = x + 1\n    return y\n')
    b = _scrivi(tmp_path, "b.py",
                'def due(z):\n    """Tutta un\'altra spiegazione, lunga."""\n'
                '    w = z + 1\n    return w\n')
    assert len(cerca_funzioni_gemelle([a, b])) == 1


# --- i vocabolari paralleli ----------------------------------------------

def test_trova_un_vocabolario_che_vive_anche_nel_javascript(tmp_path):
    """Il difetto peggiore della review: le quattro forze di un ricordo
    vivevano in Python e -- due volte -- in JavaScript, senza niente che le
    legasse. Una quinta forza faceva CANCELLARE la forza del ricordo."""
    py = _scrivi(tmp_path, "a.py",
                 'VOCI = frozenset({"preferenza", "divieto", "fatto", "regola"})\n')
    js = _scrivi(tmp_path, "p.js",
                 "var L = {preferenza: 'P', divieto: 'D', fatto: 'F', regola: 'R'};\n")
    reperti = cerca_vocabolari_paralleli([py], [js], [])
    assert len(reperti) == 1
    assert "preferenza" in reperti[0].nome


def test_un_vocabolario_a_meta_nel_javascript_non_e_un_parallelo(tmp_path):
    """Due o tre parole in comune capitano per caso; l'insieme intero no. Senza
    questa soglia il rapporto si riempirebbe di coincidenze."""
    py = _scrivi(tmp_path, "a.py", 'VOCI = ("alfa", "beta", "gamma", "delta")\n')
    js = _scrivi(tmp_path, "p.js", "var L = ['alfa', 'beta'];\n")
    assert cerca_vocabolari_paralleli([py], [js], []) == []


def test_un_vocabolario_gia_legato_da_una_prova_non_si_segnala(tmp_path):
    """La raffinatura che conta: un duplicato non e' un difetto se qualcosa si
    rompe quando i due divergono. Il difetto e' la divergenza SILENZIOSA --
    `ORDINE_FISSO` e' duplicato da sempre ed e' in regola, perche' una prova lo
    confronta col JavaScript."""
    py = _scrivi(tmp_path, "a.py", 'VOCI = ("alfa", "beta", "gamma")\n')
    js = _scrivi(tmp_path, "p.js", "var L = ['alfa', 'beta', 'gamma'];\n")
    prova = _scrivi(tmp_path, "test_x.py",
                    'from a import VOCI\n\n\ndef test_legate():\n'
                    '    js = open("p.js").read()\n'
                    '    for v in VOCI:\n        assert v in js\n')
    assert cerca_vocabolari_paralleli([py], [js], [prova]) == []


def test_una_prova_che_NON_legge_il_javascript_non_basta(tmp_path):
    """`test_memoria_interpretazione.py` nominava gia' `VOCABOLARIO` e pinnava
    la sola versione Python: non avrebbe visto nessuna divergenza. Serve che la
    prova legga entrambi i lati, o non e' un legame."""
    py = _scrivi(tmp_path, "a.py", 'VOCI = ("alfa", "beta", "gamma")\n')
    js = _scrivi(tmp_path, "p.js", "var L = ['alfa', 'beta', 'gamma'];\n")
    prova = _scrivi(tmp_path, "test_x.py",
                    'from a import VOCI\n\n\ndef test_solo_python():\n'
                    '    assert "alfa" in VOCI\n')
    assert len(cerca_vocabolari_paralleli([py], [js], [prova])) == 1


# --- i predefiniti --------------------------------------------------------

def test_trova_lo_stesso_predefinito_in_due_file(tmp_path):
    """La forma del «debito F»: `scadenza_min` valeva 5 in quattro punti, e il
    giorno in cui uno fosse cambiato gli altri tre avrebbero continuato a
    tagliare i turni a una soglia che la pagina non mostra piu'."""
    a = _scrivi(tmp_path, "a.py", 'v = cfg.get("tetto_giornaliero", 50)\n')
    b = _scrivi(tmp_path, "b.py", 'w = altro.get("tetto_giornaliero", 50)\n')
    reperti = cerca_predefiniti([a, b])
    assert len(reperti) == 1
    assert "tetto_giornaliero" in reperti[0].nome


def test_due_predefiniti_diversi_per_la_stessa_chiave_non_si_accoppiano(tmp_path):
    """Sono gia' divergenti, ed e' un altro difetto -- ma questo controllo
    cerca le copie ALLINEATE, quelle che divergeranno. Segnalarle qui
    confonderebbe due cose diverse in una riga sola."""
    a = _scrivi(tmp_path, "a.py", 'v = cfg.get("soglia", 50)\n')
    b = _scrivi(tmp_path, "b.py", 'w = altro.get("soglia", 80)\n')
    assert cerca_predefiniti([a, b]) == []


@pytest.mark.parametrize("vuoto", ['""', "0", "False"])
def test_un_predefinito_vuoto_non_si_segnala(tmp_path, vuoto):
    """`""`, `0` e `False` sono il «niente», e capitano ovunque per ragioni
    scollegate fra loro: accoppiarli riempirebbe il rapporto di righe che non
    dicono niente."""
    a = _scrivi(tmp_path, "a.py", f'v = cfg.get("x", {vuoto})\n')
    b = _scrivi(tmp_path, "b.py", f'w = altro.get("x", {vuoto})\n')
    assert cerca_predefiniti([a, b]) == []


# --- lo strumento sul progetto vero --------------------------------------

def test_lo_strumento_gira_sul_progetto_e_non_solleva():
    """Non si asserisce QUANTI reperti trova -- quel numero cambia a ogni
    correzione, e una prova che lo pinna diventerebbe una manutenzione senza
    valore. Si asserisce che gira: un rilevatore che scoppia su un file vero
    non protegge niente."""
    from doppioni import run
    assert run(cancello=False) == 0


def test_scende_dentro_un_dizionario_di_insiemi(tmp_path):
    """Il caso VERO, non una sua semplificazione: le quattro forze di un
    ricordo non erano una costante a se', erano `VOCABOLARIO["forza"]` --
    un insieme dentro un dizionario di insiemi.

    Leggendo solo il primo livello il rilevatore vedeva `{"forza",
    "condizioni", "ancore"}` e mancava esattamente cio' per cui era nato: e'
    successo davvero, alla prima stesura, e questa prova esiste perche' non
    succeda di nuovo.
    """
    py = _scrivi(tmp_path, "a.py",
                 'V = {\n'
                 '    "forza": frozenset({"preferenza", "divieto", "fatto", "regola"}),\n'
                 '    "altro": frozenset({"x"}),\n'
                 '}\n')
    js = _scrivi(tmp_path, "p.js",
                 "var L = { preferenza: 'P', divieto: 'D', fatto: 'F', regola: 'R' };\n")
    reperti = cerca_vocabolari_paralleli([py], [js], [])
    assert len(reperti) == 1
    assert "preferenza" in reperti[0].nome


def test_una_costante_solo_NOMINATA_in_una_docstring_non_e_un_legame(tmp_path):
    """Ci sono cascato subito: le prove di questo stesso strumento citano
    `VOCABOLARIO` a parole, e tanto bastava a farlo passare per legato -- cioe'
    a spegnere il rilevatore proprio sul difetto per cui e' nato. I nomi si
    leggono dal CODICE."""
    py = _scrivi(tmp_path, "a.py", 'VOCI = ("alfa", "beta", "gamma")\n')
    js = _scrivi(tmp_path, "p.js", "var L = ['alfa', 'beta', 'gamma'];\n")
    prova = _scrivi(tmp_path, "test_x.py",
                    '"""Una prova che PARLA di VOCI e di p.js senza toccarli."""\n\n\n'
                    'def test_niente():\n    assert True\n')
    assert len(cerca_vocabolari_paralleli([py], [js], [prova])) == 1
