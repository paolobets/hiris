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


_VERSIONE_MINIMA = {
    "FSTRING_MIDDLE": "3.12",  # f-string, PEP 701
    "TSTRING_MIDDLE": "3.14",  # t-string, PEP 750
}


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
    inerte se un giorno smettesse di generarlo.

    Ogni caso si salta da solo -- con una ragione leggibile -- quando
    l'interprete che sta eseguendo il test e' troppo vecchio per generare
    quel tipo di token: il salto e' per singolo caso (deciso da `hasattr`,
    non da un `skipif` che spegnerebbe l'intera parametrizzazione), quindi
    su Python 3.12 e 3.13 il caso `f` (FSTRING_MIDDLE) gira comunque per
    davvero anche se il caso `t` (TSTRING_MIDDLE, 3.14+) si salta. Su
    Python 3.11, dove nessuno dei due token esiste ancora, la proprieta'
    non e' dimostrabile con questo test: entrambi i casi si saltano, ed e'
    onesto cosi' -- non c'e' un terzo tipo di token, in 3.11, che porti
    testo nudo senza delimitatori oltre a NAME."""
    if not hasattr(tokenize, tipo_atteso):
        pytest.skip(
            f"{tipo_atteso} esiste da Python {_VERSIONE_MINIMA[tipo_atteso]}, "
            f"assente in questo interprete ({sys.version_info.major}.{sys.version_info.minor})"
        )
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


def test_un_metodo_di_haclient_non_si_applica_da_solo():
    """`ha.statistiche(...)`: `statistiche` e' una parola gia' decisa nel
    glossario, ma l'oggetto e' `HAClient` (`proxy/`, un ambito che questa
    fetta non converte affatto) -- lo strumento non puo' sapere se quel
    preciso attributo appartiene a un ambito gia' convertito o no. Misurato
    dal vivo (review Task 8): senza questa guardia, `ha.statistiche(...)`
    dentro `casa/tempo.py::trend` diventava `ha.statistics(...)`, un
    `AttributeError` in produzione perche' `HAClient.statistiche` resta
    cosi' finche' `proxy/` non e' convertito."""
    gf = rinomina.Glossario(mappa={"statistiche": "statistics"})
    dentro = 'esito = await ha.statistiche([entita], "hour", 3)\n'
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, "il metodo di HAClient non si applica da solo"
    assert [p.nome for p in proposte] == ["statistiche"]
    assert proposte[0].suggerito == "statistics"


def test_un_metodo_che_non_e_di_haclient_si_applica_normalmente():
    """La guardia e' un allowlist su `_METODI_HA_CLIENT`, non un blocco
    generico su ogni chiamata per attributo: un metodo mio (qui,
    `comportamento`, non nell'elenco) continua ad applicarsi come sempre,
    altrimenti la guardia diventerebbe il difetto opposto -- bloccare
    anche cio' che lo strumento puo' verificare."""
    gf = rinomina.Glossario(mappa={"comportamento": "behavior"})
    dentro = "voci = self._casa.comportamento()\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "voci = self._casa.behavior()\n"
    assert proposte == []


def _verifica_idempotenza(base: Path, ambito: str, copia: Path,
                          residui_noti: frozenset = frozenset()) -> None:
    """Applica lo strumento a una COPIA di `base` (un file o una cartella)
    e controlla che il risultato sia identico bit per bit -- l'idempotenza
    non si dichiara, si misura.

    `residui_noti` e' l'elenco esplicito dei file per cui una divergenza e'
    GIA' NOTA e tracciata altrove (un drift pre-esistente non ancora
    chiuso, non un difetto di questo controllo): l'uguaglianza e' ESATTA
    in entrambe le direzioni, quindi un residuo che smette di divergere
    (perche' qualcuno l'ha corretto altrove, senza aggiornare questa riga)
    fa fallire la prova esattamente come una regressione vera -- un
    eccezione dimenticata sarebbe silenziosa quanto il difetto che
    l'eccezione doveva coprire."""
    import shutil
    if base.is_dir():
        shutil.copytree(base, copia, ignore=shutil.ignore_patterns("__pycache__"))
        prima = {f.relative_to(copia): f.read_bytes() for f in copia.rglob("*.py")}
        rinomina.applica(copia, ambito, scrivi=True)
        dopo = {f.relative_to(copia): f.read_bytes() for f in copia.rglob("*.py")}
    else:
        shutil.copy(base, copia)
        chiave = Path(base.name)
        prima = {chiave: copia.read_bytes()}
        rinomina.applica(copia, ambito, scrivi=True)
        dopo = {chiave: copia.read_bytes()}
    cambiati = frozenset(k for k in prima if prima[k] != dopo[k])
    assert cambiati == residui_noti, (
        f"{base}: file cambiati={sorted(map(str, cambiati))}, "
        f"attesi={sorted(map(str, residui_noti))} -- se e' comparso un file "
        "nuovo e' una regressione; se un residuo noto non compare piu' "
        "e' stato corretto altrove e questa riga va tolta")


def _sostituzioni_di_identificatori(prima: str, dopo: str) -> set[tuple[str, str]]:
    """L'insieme delle coppie (nome vecchio, nome nuovo) fra due sorgenti che
    differiscono SOLO per rinomina di identificatori -- mai per l'aggiunta o
    la rimozione di un token: una rinomina non cambia la struttura del
    programma, quindi i due flussi di token hanno la STESSA lunghezza, e
    confrontarli posizione per posizione basta.

    Serve a rendere fine un residuo noto a grana di file (`_SORVEGLIATI`,
    `_verifica_idempotenza`): quel controllo dice CHE un file diverge, non
    COSA -- e un'eccezione a grana di file puo' nascondere un secondo
    debito nato dopo, nello stesso file, per una ragione diversa (misurato
    dal vivo: `memoria/resolver.py::_compila` aveva sia `inizio` (residuo
    dichiarato) sia `prefisso`/`suffisso` -- una meta' di quella seconda
    coppia era stata decisa nel glossario da questo stesso lotto per
    `casa/strumenti.py`, e la guardia a grana di file non l'avrebbe vista
    finche' qualcuno non fosse arrivato a leggere `resolver.py` di
    persona)."""
    toks_prima = [t for t in tokenize.generate_tokens(io.StringIO(prima).readline)
                  if t.type == tokenize.NAME]
    toks_dopo = [t for t in tokenize.generate_tokens(io.StringIO(dopo).readline)
                 if t.type == tokenize.NAME]
    assert len(toks_prima) == len(toks_dopo), (
        "i due sorgenti non hanno lo stesso numero di identificatori: "
        "questa funzione confronta solo rinomine, non altre modifiche")
    return {(a.string, b.string) for a, b in zip(toks_prima, toks_dopo)
            if a.string != b.string}


# **L'elenco esplicito e leggibile degli ambiti SORVEGLIATI.** Corretto dopo
# il rilievo del coordinatore: il vecchio controllo guardava solo due
# sottosistemi su sei (schedulatore, memoria) -- un residuo trovato durante
# il lotto 5 viveva in un ambito COPERTO ma non riverificato dopo
# l'aggiunta di parole nuove al glossario; un secondo, in
# `azione/costruzione/composer.py`, vive invece in un ambito che questo
# test non guardava affatto. Allargato a tutti e sei.
#
# `casa/` non e' ancora finito (`domande.py` e `nucleo.py` restano in
# parte italiani, `strumenti.py` per intero): elencare la cartella intera
# pretenderebbe zero anche li', cosa falsa per costruzione. Si elencano
# invece i singoli file gia' chiusi, uno per lotto -- un dato esplicito
# che chi legge puo' contare, non un'assenza silenziosa. Quando l'ultimo
# lotto di `casa/` chiude, le cinque righe si possono sostituire con
# `("casa", "casa", frozenset())`.
#
# `residui_noti` per `memoria`: `resolver.py::Lookup.find` ha `inizio`
# ancora italiano -- **deliberatamente**, review del lotto 5: tradurlo da
# solo (`inizio -> start`) senza il suo gemello nella stessa espressione
# (`fine`, mai deciso nel glossario) avrebbe lasciato una coppia a meta'
# tradotta (`start, fine = m.span()`), la STESSA asimmetria che ha
# motivato la qualificazione `dopo (casa)` invece di lasciarlo nudo. La
# correzione tocca solo file gia' miei (`domande.py`), non `resolver.py`
# per intero (~30 identificatori italiani restano li', fuori dal
# perimetro): chiudere le coppie (`fine -> end`,
# `inizio_originale`/`fine_originale`, `candidati`) e' un giro a se',
# rimandato al lotto che convertira' `memoria/` per intero -- e servirebbe
# comunque a poco: due nomi corretti non avvicinano il file a
# "convertito".
#
# `residui_noti` per `azione`: `costruzione/composer.py` ha ancora
# `candidato` (due funzioni private) e il parametro PUBBLICO keyword-only
# `modo` di `compose_automation`/`compose_script` in italiano -- entrambi
# parole gia' decise. **Corretto durante la review del lotto 5**: `modo`
# non ha ZERO chiamanti che lo passano per keyword in tutto il repo
# (verificato con un grep, non presunto) -- il rinvio non e' perche'
# cercarli costerebbe caro, e' semplicemente che `azione/` non e' un file
# di questo lotto: rinominare un parametro pubblico, anche a costo zero,
# resta un giro a se', rimandato al lotto che convertira' `azione/`.
_SORVEGLIATI: tuple[tuple[str, str, frozenset], ...] = (
    ("schedulatore", "schedulatore", frozenset()),
    ("memoria", "memoria", frozenset({Path("resolver.py")})),
    ("consumi", "consumi", frozenset()),
    ("cervello", "cervello", frozenset()),
    ("azione", "azione", frozenset({Path("costruzione/composer.py")})),
    ("casa/lettura_yaml.py", "casa", frozenset()),
    ("casa/comportamento.py", "casa", frozenset()),
    ("casa/archivio.py", "casa", frozenset()),
    ("casa/tempo.py", "casa", frozenset()),
    ("casa/anagrafe.py", "casa", frozenset()),
    ("casa/domande.py", "casa", frozenset()),
    ("casa/nucleo.py", "casa", frozenset()),
    # `strumenti.py` importa il proprio vicino con `from . import tempo`: la
    # protezione dei percorsi di import (`_righe_di_percorso_e_parola_chiave`)
    # segue il proprio `modo` di stato PAROLA PER PAROLA e lo azzera appena
    # incontra "import" -- corretto per `from .X import Y` (il nome
    # importato arriva DOPO l'azzeramento, ma "X" e' gia' protetto perche'
    # letto PRIMA), ma non per `from . import X` (qui "X" e' l'unico token
    # dopo "import", quindi arriva DOPO l'azzeramento e resta un NAME
    # qualunque). "tempo" e' un concetto gia' deciso (`tempo -> historian`,
    # "I concetti"): senza questa eccezione lo strumento riscriverebbe
    # l'import in `from . import historian`, un `ModuleNotFoundError` --
    # `casa/tempo.py` non e' stato rinominato (i nomi dei file sono un passo
    # a parte, mai una riscrittura di stringa). Misurato dal vivo (lotto 7):
    # la stessa importazione dentro `casa/nucleo.py` non ha questo problema
    # perche' usa la forma `from .anagrafe import (...)`, dove il nome del
    # modulo vive PRIMA di "import" ed e' quindi gia' protetto.
    ("casa/strumenti.py", "casa", frozenset({Path("strumenti.py")})),
)


def test_gli_ambiti_chiusi_restano_idempotenti(tmp_path):
    """La guardia sui sei ambiti (cinque interi piu' i file gia' chiusi di
    `casa/`, vedi `_SORVEGLIATI` sopra): una regressione futura (in questo
    script o nel glossario) si vede qui, sull'ambito dove e' successa,
    invece di scoprirsi per caso al prossimo lotto che tocca quell'ambito."""
    from _comune import ROOT
    for percorso, ambito, residui_noti in _SORVEGLIATI:
        etichetta = percorso.replace("/", "_")
        _verifica_idempotenza(ROOT / "hiris" / "app" / percorso, ambito,
                              tmp_path / etichetta, residui_noti)


def test_il_residuo_di_memoria_resolver_e_solo_inizio_start(tmp_path):
    """La grana FINE del residuo noto di `memoria/resolver.py` (sopra, in
    `_SORVEGLIATI`): non basta sapere che il file diverge, serve sapere
    COSA cambia -- l'eccezione a grana di file l'ha gia' nascosto una volta
    (vedi `_sostituzioni_di_identificatori`). Se domani un'altra parola di
    `resolver.py` entra nel glossario per un altro lotto, questa prova
    arrossisce ANCHE SE il file resta nell'elenco dei cambiati sopra."""
    import shutil

    from _comune import ROOT
    base = ROOT / "hiris" / "app" / "memoria" / "resolver.py"
    copia = tmp_path / "resolver.py"
    shutil.copy(base, copia)
    prima = copia.read_text(encoding="utf-8")
    rinomina.applica(copia, "memoria", scrivi=True)
    dopo = copia.read_text(encoding="utf-8")
    sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
    assert sostituzioni == {("inizio", "start")}, (
        f"memoria/resolver.py diverge su {sostituzioni}, atteso solo "
        "{('inizio', 'start')} -- un nuovo nome e' comparso: decidilo "
        "davvero (applicalo, o traccialo qui) invece di lasciarlo dentro "
        "un'eccezione a grana di file")


def test_la_verifica_di_idempotenza_arrossisce_se_qualcosa_cambia(tmp_path):
    """Prova per mutazione, isolata dal vero `hiris/app/` (cosi' non dipende
    da trovare per caso un identificatore reale non ancora applicato): un
    file sintetico con `archivio`, gia' deciso -> `store` per l'ambito
    `memoria`, deve far fallire `_verifica_idempotenza` -- e' esattamente
    la forma del difetto che il test sopra sorveglia."""
    modulo = tmp_path / "sorgente.py"
    modulo.write_text("archivio = 1\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        _verifica_idempotenza(modulo, "memoria", tmp_path / "copia.py")


def test_un_residuo_noto_dimenticato_arrossisce_anche_lui(tmp_path):
    """Il gemello nella direzione opposta: se un `residuo_noto` smette di
    divergere davvero (qualcuno l'ha corretto altrove) e nessuno toglie la
    riga da `_SORVEGLIATI`, la lista mentirebbe silenziosamente -- questa
    prova dimostra che l'uguaglianza `cambiati == residui_noti` e' ESATTA,
    non un `>=`, quindi un'eccezione dimenticata si vede."""
    modulo = tmp_path / "sorgente.py"
    modulo.write_text("x = 1\n", encoding="utf-8")  # niente da rinominare
    with pytest.raises(AssertionError):
        _verifica_idempotenza(modulo, "memoria", tmp_path / "copia.py",
                              residui_noti=frozenset({Path("sorgente.py")}))



def test_un_import_nudo_non_azzera_il_riconoscimento_del_resto_del_file():
    """Difetto trovato durante lo sviluppo del fix sopra (il test di
    idempotenza, su un albero GIA' convertito, non lo fa mordere: li' "salta
    tutto" e "non cambia niente" producono lo stesso risultato atteso, sono
    indistinguibili -- serve un sorgente NON convertito). Un `import` nudo
    (senza `from`, senza `as`) lasciava `modo` bloccato su
    "percorso_import" per il resto del file, perche' nessun token lo
    richiudeva da solo (a differenza di `from ... import`, che si chiude
    incontrando il proprio `import`): ogni identificatore successivo veniva
    scambiato per un segmento di percorso e saltato in silenzio -- zero
    cambi, zero proposte, nessun errore. Riprodotto dal vivo durante la
    review: `resolver.py`, che ha `import re` in cima, smetteva di essere
    visto per intero."""
    gf = rinomina.Glossario(mappa={"origine": "actor"})
    dentro = "import re\n\norigine = 1\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "import re\n\nactor = 1\n", (
        "un import nudo non deve spegnere il riconoscimento del resto del file")
    assert proposte == []
