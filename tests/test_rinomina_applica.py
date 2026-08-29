"""L'applicazione ai file: cosa si tocca, cosa no, e le guardie."""
import io
import sys
import tokenize
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rinomina


@pytest.fixture(scope="module")
def g():
    return rinomina.leggi_glossario()


def test_rinomina_un_identificatore(g):
    fuori, _ = rinomina.riscrivi("archivio = 1\n", g, "memoria")
    assert fuori == "store = 1\n"


def test_NON_tocca_i_commenti(g):
    """IL CONFINE DEL MANDATO. «Solo ed esclusivamente cio' che e' codice»:
    il commento resta identico, parola per parola."""
    dentro = "# l'archivio dei ricordi\narchivio = 1\n"
    fuori, _ = rinomina.riscrivi(dentro, g, "memoria")
    assert fuori == "# l'archivio dei ricordi\nstore = 1\n"


def test_NON_tocca_le_stringhe(g):
    """Le frasi che HIRIS dice al proprietario sono italiane e restano tali.
    E la stessa guardia protegge le query SQL: i nomi delle tabelle sono in
    stringhe, e il database e' fuori perimetro."""
    dentro = 'msg = "l\'archivio e\' pieno"\narchivio = 1\n'
    fuori, _ = rinomina.riscrivi(dentro, g, "memoria")
    assert '"l\'archivio e\' pieno"' in fuori
    assert "store = 1" in fuori


def test_NON_tocca_le_query_sql(g):
    """La tabella `ricordi` non si tocca: il database e' fuori perimetro, e
    lo e' per costruzione perche' le query sono stringhe."""
    dentro = 'q = "SELECT * FROM ricordi"\nricordo = 1\n'
    fuori, _ = rinomina.riscrivi(dentro, g, "memoria")
    assert 'FROM ricordi' in fuori


def test_i_composti_escono_come_proposte_e_il_file_NON_cambia(g):
    dentro = "archivio_casa = 1\n"
    fuori, proposte = rinomina.riscrivi(dentro, g, "casa")
    assert fuori == dentro, "un composto non si applica da solo"
    assert [p.nome for p in proposte] == ["archivio_casa"]


def test_e_idempotente(g):
    """Rigirarlo non cambia nulla. Senza questa proprieta' non si potrebbe
    ri-applicare dopo una correzione senza rileggere tutto da capo."""
    uno, _ = rinomina.riscrivi("archivio = 1\n", g, "memoria")
    due, _ = rinomina.riscrivi(uno, g, "memoria")
    assert uno == due


def test_l_omonimo_segue_il_sottosistema(g):
    assert rinomina.riscrivi("ancora = 1\n", g, "memoria")[0] == "tether = 1\n"
    assert rinomina.riscrivi("ancora = 1\n", g, "consumi")[0] == "anchor = 1\n"


def test_una_collisione_non_si_applica_e_si_segnala():
    """Se due nomi ORIGINALI diversi finirebbero sullo stesso inglese nello
    stesso file, nessuno dei due si applica: fonderli sarebbe peggio di non
    rinominare -- un'identita' scambiata per un'altra senza che nessuno lo
    sappia. Come un composto, si segnala e si chiede, non si indovina.

    Sul glossario vero, DOPO la correzione del trattino basso qui sopra,
    `_fuso`/`fuso` non collidono piu' (diventano `_timezone`/`timezone`,
    distinti -- verificato a mano prima di scrivere questo test). La
    collisione qui e' quindi fabbricata apposta -- due parole diverse fatte
    puntare allo stesso inglese in un glossario finto -- per provare la
    guardia in isolamento da una coppia del glossario vero che potrebbe
    smettere di collidere (o iniziare a farlo) per motivi indipendenti da
    questa guardia."""
    gf = rinomina.Glossario(mappa={"alfa": "stesso", "beta": "stesso", "gamma": "diverso"})
    dentro = "alfa = 1\nbeta = 2\ngamma = 3\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")

    assert fuori == "alfa = 1\nbeta = 2\ndiverso = 3\n", (
        "gamma non collide e si applica; alfa/beta collidono e restano intatte")
    collisioni = [p for p in proposte if isinstance(p, rinomina.Collisione)]
    assert len(collisioni) == 1
    assert collisioni[0].nomi == ["alfa", "beta"]
    assert collisioni[0].suggerito == "stesso"


def test_un_file_che_non_si_puo_leggere_non_ferma_il_giro(g, tmp_path):
    """Un file rotto e' un fatto da riportare, non un motivo per lasciare il
    sottosistema a meta'."""
    (tmp_path / "rotto.py").write_text("def (\n", encoding="utf-8")
    (tmp_path / "sano.py").write_text("archivio = 1\n", encoding="utf-8")
    rinomina.applica(tmp_path, "memoria")
    assert (tmp_path / "sano.py").read_text(encoding="utf-8") == "store = 1\n"
    assert (tmp_path / "rotto.py").read_text(encoding="utf-8") == "def (\n"


@pytest.mark.parametrize(("prefisso", "tipo_atteso"), [
    ("f", "FSTRING_MIDDLE"),
    ("t", "TSTRING_MIDDLE"),
])
def test_la_guardia_e_un_allowlist_non_una_blocklist(g, prefisso, tipo_atteso):
    """`if t.type != tokenize.NAME: continue` e' un ALLOWLIST assoluto --
    passa solo NAME -- non un elenco di tipi «pericolosi» da riconoscere ed
    escludere uno per uno. La differenza conta: un elenco andrebbe
    aggiornato a ogni versione di Python che introduce un nuovo tipo di
    token; un allowlist copre anche i tipi che non esistono ancora, per
    costruzione.

    Il test prova quindi la PROPRIETA', non l'elenco: un token diverso da
    NAME che porta il testo letterale di una parola del glossario SENZA
    delimitatori intorno resta intatto. COMMENT e STRING non sono casi
    utili qui: portano sempre il loro delimitatore (`#`, le virgolette)
    dentro `t.string`, e restano immuni anche senza la guardia (verificato
    per mutazione altrove: allargare il filtro a COMMENT non fa fallire
    `test_NON_tocca_i_commenti` ne' `test_NON_tocca_le_stringhe`). I due
    casi che oggi hanno davvero testo nudo sono FSTRING_MIDDLE (f-string,
    PEP 701, Python 3.12+) e TSTRING_MIDDLE (t-string, PEP 750,
    Python 3.14+); il test verifica anche che l'interprete generi
    davvero quel token, cosi' la parametrizzazione non resta silenziosamente
    inerte se un giorno smettesse di generarlo."""
    dentro = f'msg = {prefisso}"archivio{{x}}"\n'
    generati = {t.type for t in tokenize.generate_tokens(io.StringIO(dentro).readline)}
    assert getattr(tokenize, tipo_atteso) in generati, (
        f"il caso di prova non genera {tipo_atteso}: la proprieta' non e' verificata"
    )
    fuori, _ = rinomina.riscrivi(dentro, g, "memoria")
    assert fuori == dentro


def test_NON_cambia_i_fine_riga_LF(g, tmp_path):
    """Il giro non deve toccare i fine-riga esistenti -- di NESSUNA riga,
    non solo di quella con l'identificatore rinominato.

    Misurato: leggere e scrivere in universal newlines implicito (senza
    fissare `newline`) fa si' che su Windows la scrittura traduca ogni LF
    in CRLF, anche per le righe che il giro non doveva toccare -- un file
    LF diventerebbe interamente CRLF, il contrario della prima guardia (un
    diff che contiene una cosa sola). Il test legge e scrive BYTE GREZZI di
    proposito: `read_text()`/`write_text()` senza `newline` rinormalizzano
    in lettura e traducono in scrittura in modo simmetrico, e
    maschererebbero esattamente il difetto che questo test deve
    cogliere."""
    f = tmp_path / "lf.py"
    f.write_bytes(b"archivio = 1\nx = 2\n")
    rinomina.applica(tmp_path, "memoria")
    dopo = f.read_bytes()
    assert b"\r\n" not in dopo
    assert dopo == b"store = 1\nx = 2\n"


def test_NON_cambia_i_fine_riga_CRLF(g, tmp_path):
    """Il gemello del test sopra, nella direzione opposta.

    Misurato: fissare `newline=""` solo in SCRITTURA non basta -- serve
    anche in LETTURA. Senza, la lettura normalizza CRLF a LF in memoria (e'
    la meta' «universal» dello universal newlines), e la scrittura
    successiva (anche con `newline=""` fissato) riscrive fedelmente quell'LF
    normalizzato: un file CRLF verrebbe declassato a LF su OGNI riga, la
    stessa violazione della guardia vista sopra ma nella direzione
    contraria. Provato per mutazione: togliere `newline=""` dalla sola
    lettura di `_leggi_grezzo` non fa fallire il test gemello LF (il file
    LF non ha nulla da normalizzare in lettura), ma fa fallire questo."""
    f = tmp_path / "crlf.py"
    f.write_bytes(b"archivio = 1\r\nx = 2\r\n")
    rinomina.applica(tmp_path, "memoria")
    dopo = f.read_bytes()
    assert dopo == b"store = 1\r\nx = 2\r\n"


def test_applica_su_un_file_singolo(g, tmp_path):
    """`applica()` prende anche un percorso-file, non solo una cartella.

    Misurato: `file_py()` usa `rglob`, che su un percorso-file non trova
    nulla -- con quello soltanto, questo test resta rosso: zero file
    elaborati, nessun errore, nessuna modifica. L'aspetto esatto di un
    successo, sul difetto peggiore che lo strumento possa avere."""
    f = tmp_path / "solo.py"
    f.write_text("archivio = 1\n", encoding="utf-8")
    rinomina.applica(f, "memoria")
    assert f.read_text(encoding="utf-8") == "store = 1\n"


def test_un_percorso_di_import_non_si_tocca_anche_se_la_parola_e_decisa():
    """`from ..casa.archivio import X`: `casa` e `archivio` sono un
    indirizzo verso un altro modulo, non identificatori del proprio
    ambito -- anche quando entrambi hanno una riga nel glossario finto.
    Misurato dal vivo (review del Task 5): senza questa guardia lo
    strumento riscriveva `from ..casa.anagrafe import ...` in
    `from ..home_space.topology import ...`, un `ModuleNotFoundError`
    certo perche' `casa/` non viene rinominata da questo task."""
    gf = rinomina.Glossario(mappa={"casa": "home_space", "archivio": "store"})
    dentro = "from ..casa.archivio import ArchivioCasa\narchivio = 1\n"
    fuori, _ = rinomina.riscrivi(dentro, gf, "qualunque")
    assert "from ..casa.archivio import ArchivioCasa" in fuori, (
        "il percorso dell'import non deve cambiare")
    assert "store = 1" in fuori, (
        "un identificatore VERO, fuori dall'import, deve continuare a tradursi")


def test_un_percorso_di_import_semplice_senza_from_non_si_tocca():
    """`import casa.archivio`: stessa guardia, forma senza `from`."""
    gf = rinomina.Glossario(mappa={"casa": "home_space", "archivio": "store"})
    dentro = "import casa.archivio\n"
    fuori, _ = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro


def test_un_percorso_che_punta_al_proprio_ambito_non_si_tocca():
    """Vale anche per un import RELATIVO che punta al proprio stesso
    sottosistema: il file, se deciso, si rinomina con `git mv`, mai
    riscrivendo la stringa dell'import (misurato: `from .archivio import
    X` non deve diventare `from .store import X` solo perche' `archivio`
    e' deciso -- quella e' una scelta a parte, con le sue conseguenze su
    ogni altro chiamante)."""
    gf = rinomina.Glossario(mappa={"archivio": "store"})
    dentro = "from .archivio import ArchivioMemoria\n"
    fuori, _ = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro


def test_l_alias_di_un_import_semplice_resta_un_identificatore_vero():
    """Dopo `as`, il nome e' un legame locale scelto da chi scrive il
    codice -- non un segmento di percorso -- e resta soggetto alla
    classificazione normale."""
    gf = rinomina.Glossario(mappa={"casa": "home_space", "archivio": "store"})
    dentro = "import casa.archivio as archivio\n"
    fuori, _ = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "import casa.archivio as store\n"


def test_una_parola_chiave_in_una_chiamata_non_si_applica_da_sola():
    """`f(origine=\"x\")`: una parola chiave in una chiamata potrebbe
    puntare a una funzione di un ambito non ancora convertito -- lo
    strumento non puo' saperlo, quindi non indovina: propone e si ferma,
    come un composto. Misurato dal vivo (review del Task 5): senza questa
    guardia, `origine=\"schedulatore\"` (verso
    `azione/porta.py::esegui(*, origine)`, non convertito) diventava
    `actor=\"schedulatore\"` e rompeva la chiamata."""
    gf = rinomina.Glossario(mappa={"origine": "actor"})
    dentro = 'esito = f(chiamata, origine="x")\n'
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, "la parola chiave non si applica da sola"
    assert [p.nome for p in proposte] == ["origine"]
    assert proposte[0].suggerito == "actor"


def test_un_parametro_di_default_in_una_funzione_si_applica_ancora():
    """La stessa parola, ma come PARAMETRO di una `def` (non una chiamata),
    e' la propria firma: si applica come sempre. La guardia distingue una
    definizione da una chiamata guardando se il NAME che precede la
    parentesi e' preceduto da `def`."""
    gf = rinomina.Glossario(mappa={"origine": "actor"})
    dentro = "def f(origine=None):\n    return origine\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "def f(actor=None):\n    return actor\n"
    assert proposte == []


def test_una_parola_chiave_ripetuta_produce_una_sola_proposta():
    gf = rinomina.Glossario(mappa={"origine": "actor"})
    dentro = 'f(a, origine="x")\ng(b, origine="y")\n'
    _, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert len(proposte) == 1


def test_l_idempotenza_si_misura_riapplicando_ad_albero_gia_convertito(tmp_path):
    """L'idempotenza non si dichiara, si misura: si applica lo strumento a
    una COPIA di un sottosistema gia' convertito e si controlla che non
    cambi un solo byte. Qui sui due sottosistemi veri del Task 5, cosi'
    che una regressione futura (in questo script o nel glossario) si veda
    subito, invece di scoprirsi al prossimo ambito."""
    import shutil

    from _comune import ROOT
    for cartella, ambito in (("schedulatore", "schedulatore"), ("memoria", "memoria")):
        origine = ROOT / "hiris" / "app" / cartella
        copia = tmp_path / cartella
        shutil.copytree(origine, copia, ignore=shutil.ignore_patterns("__pycache__"))
        prima = {f.relative_to(copia): f.read_bytes()
                for f in copia.rglob("*.py")}
        rinomina.applica(copia, ambito, scrivi=True)
        dopo = {f.relative_to(copia): f.read_bytes()
               for f in copia.rglob("*.py")}
        assert dopo == prima, (
            f"riapplicare lo strumento a {cartella}/ (gia' convertito) ha "
            "cambiato qualcosa: non e' idempotente")
