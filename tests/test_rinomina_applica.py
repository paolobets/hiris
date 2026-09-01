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
    """Un attributo che appartiene a `HAClient` non si applica da solo: lo
    strumento non puo' sapere se quel preciso attributo sia di un ambito gia'
    convertito o no.

    **Il caso misurato dal vivo era `ha.statistiche(...)`** (review Task 8):
    senza questa guardia diventava `ha.statistics(...)` dentro
    `casa/tempo.py::trend`, un `AttributeError` in produzione perche'
    `HAClient.statistiche` restava italiano. **Quel caso oggi non esiste
    piu'**: dal lotto 19 `proxy/` e' convertito e quel metodo si chiama
    `statistics` per davvero. La guardia serve identica nel verso opposto --
    il giorno in cui una parola inglese di `HAClient` entrasse nel glossario
    come traduzione di qualcos'altro -- e il glossario di questa prova e'
    sintetico apposta, cosi' misura il MECCANISMO e non lo stato di
    conversione di `proxy/`."""
    gf = rinomina.Glossario(mappa={"related": "linked"})
    dentro = 'esito = await ha.related("area", identifier)\n'
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, "il metodo di HAClient non si applica da solo"
    assert [p.nome for p in proposte] == ["related"]
    assert proposte[0].suggerito == "linked"


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


def test_un_metodo_di_usagestore_non_si_applica_da_solo():
    """La stessa guardia, per `UsageStore` (Task 9): `sezioni`/`totali`/
    `storia` sono metodi PUBBLICI di un ambito gia' chiuso (`consumi/`)
    ma mai decisi -- se una parola omonima venisse decisa domani per
    un'altra ragione (`sezione -> section`), applicarla alla cieca
    romperebbe `archivio.sezioni(...)` in `archivio.section(...)`, lo
    stesso guasto di `ha.statistiche()`. Misurato PRIMA di commetterlo
    (dry-run su `api/handlers_usage.py`), non dopo -- la lezione esplicita
    di questo Task."""
    gf = rinomina.Glossario(mappa={"sezioni": "section"})
    dentro = "corpo = archivio.sezioni(da_anchor=True)\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, "il metodo di UsageStore non si applica da solo"
    assert [p.nome for p in proposte] == ["sezioni"]
    assert proposte[0].suggerito == "section"


def test_un_metodo_che_non_e_di_usagestore_si_applica_normalmente():
    """La guardia su `UsageStore` e' un allowlist quanto quella su
    `HAClient`, non un blocco generico: un metodo mio (qui,
    `comportamento`, non in nessuno dei due elenchi) continua ad
    applicarsi come sempre."""
    gf = rinomina.Glossario(mappa={"comportamento": "behavior"})
    dentro = "voci = self._consumi.comportamento()\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "voci = self._consumi.behavior()\n"
    assert proposte == []


def test_una_firma_rinominata_con_un_chiamante_rimasto_indietro_si_dichiara():
    """Il controllo di chiusura, primo strato: dentro lo stesso file.

    E' il caso `stato` misurato dal vivo (Task 9, lotto 10): lo strumento
    rinomina il parametro nella `def` (`stato -> state`) e lascia intatto il
    `stato=400` del chiamante, perche' una parola chiave in una chiamata e'
    protetta di proposito -- non sa a quale firma risolva. La regola resta
    buona; cio' che mancava era DIRE che la firma e la chiamata hanno smesso
    di parlarsi. I due fatti erano gia' dentro `riscrivi`: mancava solo
    l'intersezione."""
    gf = rinomina.Glossario(mappa={"stato": "state"})
    dentro = ("def _errore(codice, *, stato: int = 200):\n"
              "    return risposta(x, status=stato)\n"
              "\n"
              "def chiama():\n"
              "    return _errore(1, stato=400)\n")
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert "*, state: int = 200" in fuori, "la def si rinomina come sempre"
    assert "stato=400" in fuori, "la parola chiave del chiamante NON si tocca"
    scollegate = [p for p in proposte if isinstance(p, rinomina.FirmaScollegata)]
    assert len(scollegate) == 1, f"attesa una firma scollegata, trovate {scollegate}"
    assert scollegate[0].vecchio == "stato"
    assert scollegate[0].nuovo == "state"
    assert scollegate[0].righe == [5], "la riga del chiamante rimasto indietro"


def test_una_firma_rinominata_senza_chiamanti_indietro_non_dichiara_niente():
    """La controprova: il controllo parla solo quando c'e' davvero una
    divergenza. Un parametro rinominato i cui chiamanti passano per POSIZIONE
    non ha nessun `vecchio=` da segnalare, e il rumore di un avviso che non
    corrisponde a niente farebbe smettere di leggerli tutti."""
    gf = rinomina.Glossario(mappa={"stato": "state"})
    dentro = ("def _errore(codice, stato=200):\n"
              "    return risposta(codice, stato)\n"
              "\n"
              "def chiama():\n"
              "    return _errore(1, 400)\n")
    _, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert [p for p in proposte if isinstance(p, rinomina.FirmaScollegata)] == []


def test_i_parametri_di_una_def_si_distinguono_dalle_annotazioni_e_dai_default():
    """`_posizioni_parametri_def` riconosce il NOME del parametro, non tutto
    cio' che sta dentro le parentesi di una `def`: un'annotazione
    (`dict[str, int]`) porta una virgola che NON apre un parametro nuovo, e un
    valore predefinito (`= _MAX`) e' un nome che non va rinominato come se
    fosse la firma. Senza questa distinzione il controllo di chiusura
    segnalerebbe firme che nessuno ha toccato."""
    dentro = "def f(primo: dict[str, int], *args, secondo=_MAX, **kw) -> None:\n    pass\n"
    tokens = list(tokenize.generate_tokens(io.StringIO(dentro).readline))
    nomi = {tokens[i].string for i in rinomina._posizioni_parametri_def(tokens)}
    assert nomi == {"primo", "args", "secondo", "kw"}, nomi


def test_il_controllo_di_chiusura_trova_un_chiamante_orfano_in_UN_ALTRO_file(tmp_path):
    """Il secondo strato, e la ragione per cui esiste: il chiamante rimasto
    indietro puo' vivere in un file che il lotto in corso non guarda affatto.

    Misurato dal vivo (Task 9, lotto 12): rinominato `turno -> exchange` nella
    `def` di `api/handlers_chat.py`, uno dei tre chiamanti era in
    `api/handlers_mcp.py:438` -- un file di un lotto PRECEDENTE, gia' chiuso e
    gia' verde. Cercare solo dentro il `--percorso` corrente lo avrebbe
    lasciato dov'era."""
    (tmp_path / "firma.py").write_text(
        "def costruisci(app, turno=None):\n    return (app, turno)\n".replace("\n", "\n"),
        encoding="utf-8")
    (tmp_path / "altro_file.py").write_text(
        "from firma import costruisci\n\nd = costruisci(app, turno=x)\n",
        encoding="utf-8")
    trovati = rinomina.chiamanti_orfani({"turno": "exchange"}, radice=tmp_path)
    nomi = {(f.name, riga, vecchio, nuovo, chiamato)
            for f, riga, vecchio, nuovo, chiamato in trovati}
    assert ("altro_file.py", 3, "turno", "exchange", "costruisci") in nomi, nomi


def test_il_controllo_di_chiusura_non_segnala_una_parola_chiave_mai_rinominata(tmp_path):
    """La controprova del secondo strato: si cercano SOLO le parole chiave
    che corrispondono a un parametro davvero rinominato. Ogni altro `foo=` del
    repo -- e sono migliaia -- non e' affar suo."""
    (tmp_path / "altro_file.py").write_text(
        "d = costruisci(app, origine=x)\n", encoding="utf-8")
    assert rinomina.chiamanti_orfani({"turno": "exchange"}, radice=tmp_path) == []
    assert rinomina.chiamanti_orfani({}, radice=tmp_path) == []


def test_il_filtro_separa_i_chiamanti_orfani_certi_dagli_ambigui(tmp_path):
    """`parametri_dichiarati` e' cio' che rende leggibile l'elenco del secondo
    strato: sulla fetta intera ha portato 555 occorrenze a 24 da guardare.

    Un `vecchio=` il cui nome NESSUNA `def` del repo dichiara piu' e' certo;
    se invece una firma qualunque lo porta ancora, la chiamata puo' puntare a
    quella ed e' ambigua. Senza questa distinzione l'elenco e' rumore, e un
    controllo che nessuno legge non protegge niente."""
    (tmp_path / "firme.py").write_text(
        "def altra_funzione(app, motivo=None):\n    return motivo\n", encoding="utf-8")
    (tmp_path / "chiamate.py").write_text(
        "a = f(motivo=1)\nb = g(gesto=2)\n", encoding="utf-8")
    dichiarati = rinomina.parametri_dichiarati(tmp_path)
    assert "motivo" in dichiarati, "una def del repo lo dichiara ancora"
    assert "gesto" not in dichiarati, "nessuna def lo dichiara: orfano certo"
    orfani = rinomina.chiamanti_orfani(
        {"motivo": "reason", "gesto": "operation"}, radice=tmp_path)
    certi = {v for _, _, v, _, _ in orfani if v not in dichiarati}
    assert certi == {"gesto"}, certi


def test_un_metodo_di_registroesiti_non_si_applica_da_solo():
    """Quarta voce della guardia (Task 9, `api/handlers_chat.py`), e la sola
    delle quattro che previene un difetto ATTIVO invece che futuro:
    `esito -> occurrence` e' deciso da sempre, e `handlers_chat.py:303` legge
    `registro.esito(...)` su un `RegistroEsiti` (`esiti_provider.py`, file di
    RADICE mai convertito). Senza questa voce il join produce
    `registry.occurrence(...)`, cioe' un `AttributeError` alla prima chat che
    ripiega dal piano alla catena -- e nessun cancello lo vede, perche' il
    finto che imita il registro nei test verrebbe rinominato insieme al
    chiamante."""
    gf = rinomina.Glossario(mappa={"esito": "occurrence"})
    dentro = "esito = registro.esito(nome_backend)\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "occurrence = registro.esito(nome_backend)\n", (
        "l'attributo di RegistroEsiti non si applica da solo; la variabile "
        "locale si'")
    assert [p.nome for p in proposte] == ["esito"]


def test_un_attributo_che_non_e_di_registroesiti_si_applica_normalmente():
    """La controprova, come per le altre tre voci: la guardia e' un elenco di
    nomi, non un blocco generico su ogni attributo dopo un punto."""
    gf = rinomina.Glossario(mappa={"esitante": "hesitant"})
    dentro = "x = registro.esitante()\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "x = registro.hesitant()\n"
    assert proposte == []


def test_un_campo_di_impostazionichat_non_si_applica_da_solo():
    """Terza voce della stessa guardia (Task 9, `api/handlers_impostazioni.py`):
    `ImpostazioniChat` e' un dataclass, non una classe di servizio -- il
    rischio e' un CAMPO letto per attributo, non un metodo. `nome` e' una
    parola ordinaria gia' decisa (`-> name`); l'attributo vero del dataclass
    resta `nome` (`impostazioni_chat.py`, un file di radice, mai deciso).
    Misurato PRIMA di romperlo: senza questa guardia `corrente.nome`
    diventava `corrente.name` in una prova isolata su questo stesso
    snippet."""
    gf = rinomina.Glossario(mappa={"nome": "name"})
    dentro = "etichetta = corrente.nome\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, "il campo di ImpostazioniChat non si applica da solo"
    assert [p.nome for p in proposte] == ["nome"]
    assert proposte[0].suggerito == "name"


def test_un_campo_che_non_e_di_impostazionichat_si_applica_normalmente():
    """La guardia su `ImpostazioniChat` e' un allowlist quanto le altre due:
    un attributo mio (qui, `comportamento`, non in nessuno dei tre elenchi)
    continua ad applicarsi come sempre."""
    gf = rinomina.Glossario(mappa={"comportamento": "behavior"})
    dentro = "voci = self._chat.comportamento()\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "voci = self._chat.behavior()\n"
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
#
# `schedulatore` mostra `frozenset()` (nessun residuo) qui sotto, ed e'
# VERO -- lo strumento non cambia nulla su quell'ambito -- ma non e'
# COMPLETO: `AgendaStore.list::solo_in_sospeso` (`archivio.py:213`) e'
# ancora italiano, invisibile perche' nessuno dei suoi tre pezzi (`solo`,
# `in`, `sospeso`) e' mai stato deciso -- non una parola gia' decisa
# rimandata (come `modo` sopra), una parola MAI vista dal glossario.
# Questa guardia misura stabilita', non completezza (Task 9, scoperto
# convertendo `api/handlers_promesse.py`, che chiama gia' questo
# parametro per keyword e lo lascia intatto): tracciato a grana di parola
# in `test_il_residuo_di_schedulatore_archivio_e_solo_solo_in_sospeso`,
# non qui, perche' non c'e' nessun `prima`/`dopo` da confrontare quando
# lo strumento non tocca nulla.
_SORVEGLIATI: tuple[tuple[str, str, frozenset], ...] = (
    ("schedulatore", "schedulatore", frozenset()),
    # `proxy` entra il 01/09 col lotto 19c, e **senza residui**: zero
    # composti da decidere e zero applicazioni su tutti e quattro i suoi
    # file, misurato prima di scrivere questa riga. E' il primo
    # sottosistema che entra qui completo alla prima -- gli altri sei ci
    # sono arrivati con un residuo dichiarato o dopo una correzione.
    ("proxy", "proxy", frozenset()),
    # `reasoning` entra il 01/09, senza residui. E' il sottosistema che ne
    # la specifica ne' il piano avevano mai nominato -- scoperto a meta'
    # fetta -- ed e' il primo aperto con tutte e quattro le reti in piedi.
    ("reasoning", "reasoning", frozenset()),
    # `backends` entra il 01/09 con UN residuo dichiarato, e la ragione non e'
    # lavoro rimandato: `openai_compat_runner.py` condivide con
    # `claude_runner.py` (modulo di RADICE, non ancora convertito)
    # un'interfaccia duck-typed -- `chat(..., strumenti=..., dispatcher=...)`
    # e i kwarg `leggi_modello=`/`registra_consumo=` del costruttore, piu' i
    # quattro aiutanti privati paralleli (`_leggi_modello`, `_registra_consumo`,
    # `_modello_scelto`, `_scrivi_rifiuto`). **Tradurne meta' e' il difetto che
    # questa fetta ha gia' pagato**: il router sceglie fra i due runner per
    # duck-typing, e nessun cancello confronta le loro firme fra loro.
    # Escono insieme, col lotto che convertira' i moduli di radice.
    ("backends", "backends", frozenset({Path("openai_compat_runner.py")})),
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


def test_il_residuo_di_casa_strumenti_e_solo_tempo_historian(tmp_path):
    """Il gemello di `test_il_residuo_di_memoria_resolver_e_solo_inizio_start`,
    per il residuo di `casa/strumenti.py` in `_SORVEGLIATI`: la stessa cecita'
    a grana di file (un secondo debito italiano nello stesso file non
    l'avrebbe fatta arrossire) e' stata trovata dal vivo dal revisore --
    la lezione del gemello di `memoria/` non era stata replicata qui."""
    import shutil

    from _comune import ROOT
    base = ROOT / "hiris" / "app" / "casa" / "strumenti.py"
    copia = tmp_path / "strumenti.py"
    shutil.copy(base, copia)
    prima = copia.read_text(encoding="utf-8")
    rinomina.applica(copia, "casa", scrivi=True)
    dopo = copia.read_text(encoding="utf-8")
    sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
    assert sostituzioni == {("tempo", "historian")}, (
        f"casa/strumenti.py diverge su {sostituzioni}, atteso solo "
        "{('tempo', 'historian')} -- un nuovo nome e' comparso: decidilo "
        "davvero (applicalo, o traccialo qui) invece di lasciarlo dentro "
        "un'eccezione a grana di file")


def test_il_residuo_di_azione_composer_e_solo_candidato_e_modo(tmp_path):
    """Il terzo gemello: `azione/costruzione/composer.py` in `_SORVEGLIATI`
    porta DUE parole (`candidato`, `modo`), non una -- l'insieme atteso ha
    due elementi, non uno, ed e' comunque ESATTO: un terzo nome che comparisse
    domani deve far arrossire questa prova, non allargarla in silenzio."""
    import shutil

    from _comune import ROOT
    base = ROOT / "hiris" / "app" / "azione" / "costruzione" / "composer.py"
    copia = tmp_path / "composer.py"
    shutil.copy(base, copia)
    prima = copia.read_text(encoding="utf-8")
    rinomina.applica(copia, "azione", scrivi=True)
    dopo = copia.read_text(encoding="utf-8")
    sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
    assert sostituzioni == {("candidato", "candidate"), ("modo", "mode")}, (
        f"azione/costruzione/composer.py diverge su {sostituzioni}, atteso "
        "solo {('candidato', 'candidate'), ('modo', 'mode')} -- un nuovo "
        "nome e' comparso: decidilo davvero (applicalo, o traccialo qui) "
        "invece di lasciarlo dentro un'eccezione a grana di file")


def test_il_residuo_di_schedulatore_archivio_e_solo_solo_in_sospeso():
    """Un quarto residuo, di una specie diversa dai tre sopra: qui lo
    strumento non ha NIENTE da applicare, quindi non c'e' un `prima`/`dopo`
    da confrontare con `_sostituzioni_di_identificatori`.

    `AgendaStore.list` (`schedulatore/archivio.py:213`) ha ancora il
    parametro keyword-only `solo_in_sospeso: bool = False`, mai deciso: i
    suoi tre pezzi (`solo`, `in`, `sospeso`) sono tutti fuori dal
    glossario, quindi `classifica()` torna `None` per ciascuno e la parola
    e' invisibile al dry-run come al join meccanico -- verificato
    eseguendo `python scripts/rinomina.py --percorso hiris/app/schedulatore
    --ambito schedulatore --dry-run`: non compare ne' fra i composti ne'
    applicata. Per questo `_SORVEGLIATI` dichiara `schedulatore` con
    residuo `frozenset()` (vuoto): la guardia di idempotenza e' vera --
    lo strumento non cambia nulla, quindi e' stabile -- ma stabile non
    e' completo. La firma vera e' un canarino diretto sul parametro,
    non un confronto testuale: se domani qualcuno rinomina
    `solo_in_sospeso` (decidendo le sue tre parole nel glossario e
    applicandole, il modo per farlo SPARIRE invece di restare tracciato),
    questo test si rompe con un messaggio che spiega perche', invece di
    restare silenziosamente disallineato.

    Due chiamanti pubblici usano gia' questo nome esatto per keyword, ed
    e' per questo che nessuno dei due lo tocca: `api/handlers_promesse.py`
    (`store.list(solo_in_sospeso=not show_all, ...)`, Task 9 di questa
    fetta) e `casa/strumenti.py:1630` (gia' chiuso). Se le tre parole
    vengono decise un domani, tutti e due i chiamanti vanno aggiornati
    nello stesso commit del parametro, non lasciati indietro."""
    import inspect

    from hiris.app.schedulatore.archivio import AgendaStore

    parametri = inspect.signature(AgendaStore.list).parameters
    assert "solo_in_sospeso" in parametri, (
        "il residuo tracciato qui e' sparito: se e' stato deciso e "
        "applicato per davvero (schedulatore/archivio.py, "
        "api/handlers_promesse.py, casa/strumenti.py, i due test dedicati), "
        "questo test va tolto, non solo aggiornato")
    assert parametri["solo_in_sospeso"].kind == inspect.Parameter.KEYWORD_ONLY


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


def test_la_def_di_un_metodo_protetto_si_rinomina_ma_si_DICHIARA():
    """Il buco che `_METODI_ESTERNI_PROTETTI` non copriva, e la sua cura.

    La guardia riconosce un metodo protetto per STRUTTURA -- un NAME preceduto
    da un punto -- e **una `def` non ha un punto davanti**. Misurato dal vivo
    (fetta «la rinomina», lotto 17 di `proxy/`): puntando lo strumento su
    `proxy/ha_client.py`, `async def statistiche` e' stato rinominato in
    silenzio mentre ogni `ha.statistiche(...)` dei sei ambiti restava intatto.

    La cura NON e' proteggere anche la `def`: renderebbe lo strumento incapace
    di convertire il file che definisce la classe, cioe' l'unico lavoro per cui
    serve. Quindi si applica e si dichiara, come il controllo di chiusura.

    Il nome protetto di questa prova e' `related`, non `statistiche`: dal lotto
    19 quel metodo si chiama `statistics` per davvero, e il caso storico non si
    puo' piu' costruire. Il meccanismo e' lo stesso.

    Provato per mutazione: tolto il blocco che emette `DefinizioneProtetta` da
    `riscrivi`, questo test va rosso mentre TUTTI gli altri restano verdi --
    cioe' nessun cancello esistente vedeva il difetto.
    """
    gf = rinomina.Glossario(mappa={"related": "linked"})
    dentro = ("class HAClient:\n"
              "    async def related(self, item_type, identifier):\n"
              "        return item_type\n")
    fuori, proposte = rinomina.riscrivi(dentro, gf, "proxy")
    assert "async def linked(self, item_type, identifier):" in fuori, (
        "la `def` si rinomina davvero: il lotto che possiede la classe deve "
        "poterlo fare")
    dichiarate = [p for p in proposte if isinstance(p, rinomina.DefinizioneProtetta)]
    assert len(dichiarate) == 1, proposte
    assert (dichiarate[0].nome, dichiarate[0].nuovo, dichiarate[0].riga) == (
        "related", "linked", 2)


def test_una_def_che_non_e_un_metodo_protetto_non_dichiara_niente():
    """La controprova. Un controllo che parla dove non c'e' niente si smette di
    leggere: `statistiche` sta in `_METODI_ESTERNI_PROTETTI`, `statistica` no,
    e la seconda si rinomina in silenzio come qualunque altro nome."""
    gf = rinomina.Glossario(mappa={"statistica": "statistic"})
    dentro = "def statistica(x):\n    return x\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "proxy")
    assert fuori.startswith("def statistic(x):")
    assert [p for p in proposte if isinstance(p, rinomina.DefinizioneProtetta)] == []


def test_il_nome_di_una_def_non_si_confonde_coi_suoi_parametri():
    """`_posizioni_nomi_def` e `_posizioni_parametri_def` rispondono a due
    domande diverse sullo stesso flusso, e la prima non deve rispondere alla
    seconda: senza la distinzione, un parametro chiamato come un metodo
    protetto (`def f(self, storico)`) verrebbe dichiarato come se fosse una
    definizione."""
    dentro = "async def diario(self, storico, ore):\n    return ore\n"
    tokens = list(tokenize.generate_tokens(io.StringIO(dentro).readline))
    nomi = {tokens[i].string for i in rinomina._posizioni_nomi_def(tokens)}
    parametri = {tokens[i].string for i in rinomina._posizioni_parametri_def(tokens)}
    assert nomi == {"diario"}, nomi
    assert parametri == {"self", "storico", "ore"}, parametri


def test_il_controllo_di_chiusura_dice_QUALE_firma_e_stata_chiamata(tmp_path):
    """Il secondo asse, e la ragione per cui il primo non bastava.

    `parametri_dichiarati` chiede «QUALCHE `def` del repo dichiara ancora
    questo nome?»: e' un rilevatore della RARITA' della parola. Misurato dal
    vivo (lotto 16 di `proxy/`): su `nome`/`chiave`/`dominio`/`entita`, che
    decine di firme non convertite dichiarano, ha marcato **zero segnalazioni
    su 120 come certe mentre le sponde vere erano quindici**.

    Il nome CHIAMATO risponde invece alla domanda giusta: un `vecchio=` dentro
    una chiamata a una firma che questo lotto ha cambiato e' una sponda; lo
    stesso `vecchio=` verso qualunque altra cosa non lo e'.
    """
    (tmp_path / "chiamate.py").write_text(
        "a = ha.storico(entita=[1])\n"
        "b = nota_ripiego(entita=2)\n", encoding="utf-8")
    trovati = rinomina.chiamanti_orfani({"entita": "entities"}, radice=tmp_path)
    chiamati = {chiamato for _, _, _, _, chiamato in trovati}
    assert chiamati == {"storico", "nota_ripiego"}, chiamati


def test_sponde_per_nome_trova_l_import_per_nome_e_l_attributo_di_modulo(tmp_path):
    """Le due sponde che nessun altro strato copre, provate insieme perche'
    insieme sono state trovate a mano -- lotto 15 la prima, lotto 18 la
    seconda, entrambe per fortuna.

    Provato per mutazione: tolto il ramo `nome_importato`, sparisce la riga
    `import` e resta l'attributo; tolto il ramo dell'attributo, il contrario.
    """
    (tmp_path / "importa.py").write_text(
        "from pacchetto.modulo import vecchio_nome\n", encoding="utf-8")
    (tmp_path / "attributo.py").write_text(
        "import pacchetto.modulo as modulo\n"
        "modulo.vecchio_nome = False\n", encoding="utf-8")
    trovati = rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path)
    per_specie = {(f.name, specie) for f, _, _, _, specie in trovati}
    assert ("importa.py", "import") in per_specie, per_specie
    assert ("attributo.py", "attributo") in per_specie, per_specie


def test_sponde_per_nome_tace_su_un_nome_nudo_e_sui_file_file_lotto(tmp_path):
    """La controprova, e serve: un nome vecchio NUDO in un altro file e' quasi
    sempre una variabile locale che si chiama uguale (`esito`, `righe`, `voci`
    vivono in decine di funzioni indipendenti). Segnalarli renderebbe l'elenco
    illeggibile -- il difetto numero uno di questo progetto -- e le due specie
    che contano si perderebbero dentro.

    E i file del lotto in corso si saltano: li' il nome nuovo c'e' gia'. Il
    percorso si calcola sulla RADICE data, non su `ROOT`, o `escludi` non
    combacia mai e salta zero file in silenzio.
    """
    (tmp_path / "nudo.py").write_text("vecchio_nome = 1\n", encoding="utf-8")
    (tmp_path / "file_lotto.py").write_text(
        "from x import vecchio_nome\n", encoding="utf-8")
    assert rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path,
                                    escludi=("file_lotto.py",)) == []


# Ogni coppia (parola qualificata, ambito) in cui la parola E' USATA ma
# `Glossario.per()` torna `None`: la riga esiste per un altro ambito, e qui
# la parola e' MUTA -- lo strumento non la vede e il dry-run non la nomina.
#
# **La mutezza e' il comportamento SICURO, non un difetto**: meglio non
# rinominare che rinominare col significato dell'altra riga. Questo elenco non
# e' quindi un debito da azzerare, e' un'istantanea da non far crescere in
# silenzio -- la stessa forma di `_NOTE_ITALIANE`. Una coppia NUOVA che
# comparisse qui e' la domanda «questa parola va qualificata anche per questo
# ambito, o e' un senso diverso?», ed e' esattamente la domanda che nessuno si
# e' posto per `riga (proxy)`: `Glossario.per("riga", "proxy")` tornava `None`,
# `riga`/`righe` restavano italiane in `proxy/ha_client.py` e **il dry-run non
# diceva niente**. Trovata inciampandoci, non cercandola.
#
# **L'elenco e' DIVISO IN DUE, e la divisione e' il punto** (01/09, review del
# round 14): un elenco che mescola un insieme che si esaurisce con uno che non
# si esaurisce mai non potra' mai dirsi finito. A fine fetta si deve poter dire
# «restano N, tutte volute», non «restano N+M, non chiedermi quante contano».

# ── 1. VOLUTE: qui la parola ha un senso DIVERSO da quello della riga
# qualificata, e la mutezza e' la risposta giusta. **Questo insieme non cala.**
_MUTE_VOLUTE = {
    # `senza` e' qualificata SOLO `(casa)`. Altrove sta dentro nomi italiani
    # per intero o dentro residui gia' dichiarati (`memoria/resolver.py`,
    # `schedulatore/turno.py::_senza_conclusione`).
    ("senza", "api"), ("senza", "azione"), ("senza", "memoria"),
    ("senza", "schedulatore"),
    # `note (casa)` vuol dire «cose che la casa SA» (-> `known`). Fuori da
    # `casa/` `note` sono annotazioni, un senso diverso: la mutezza e' giusta.
    ("note", "api"), ("note", "azione"), ("note", "consumi"),
    ("note", "schedulatore"),
    # `dopo (casa)` e' l'ordine temporale. In `azione/` `dopo` e' la CHIAVE
    # JSON `"prima"`/`"dopo"` di un confronto di stati: valore di dominio,
    # italiano per decisione (vedi la riga `primo` del glossario).
    ("dopo", "azione"),
    # `fuori (casa)` e' «all'aperto». In `consumi/` e `schedulatore/` e' «in
    # uscita»/«fuori finestra»: senso diverso, mutezza giusta.
    ("fuori", "consumi"), ("fuori", "schedulatore"),
    # `lettura` e' qualificata `(casa)`/`(consumi)`. In `schedulatore/` compare
    # solo dentro `SOLA_LETTURA`, dove e' «read-only»: terzo senso.
    ("lettura", "schedulatore"),
    # `loro`/`nostro` sono qualificate SOLO `(casa)`; in `azione/verifica.py`
    # stanno in una riga sola, e non sono state decise per quell'ambito.
    ("loro", "azione"), ("nostro", "azione"),
    # `piano (abbonamento)` E' irraggiungibile per costruzione, con la ragione
    # scritta accanto alla riga: si applica a mano. Qui non e' una scoperta.
    ("piano", "api"),
    # `verifica` e' qualificata `(azione)`/`(memoria)`; in `casa/strumenti.py`
    # c'e' un'occorrenza sola, dentro il residuo dichiarato di quel file.
    ("verifica", "casa"),
}

# ── 2. DA CONVERTIRE: la parola e' muta solo perche' il suo sottosistema non
# e' ancora stato convertito. **Questo insieme si esaurisce**, e ogni fetta lo
# fa calare: quando `agent/` sara' convertito queste righe spariscono, o
# diventano volute con una ragione scritta.
_MUTE_PROVVISORIE = {
    ("senza", "agent"), ("piano", "agent"), ("riga", "agent"),
    ("verifica", "agent"),
}

_MUTE_NOTE = _MUTE_VOLUTE | _MUTE_PROVVISORIE


def _pezzi_per_ambito() -> dict[str, set[str]]:
    """`{ambito: {pezzi minuscoli usati nei suoi identificatori}}`.

    Una passata sola su `hiris/app`: la versione ingenua (un giro per ogni
    coppia parola/ambito) tokenizza gli stessi file centoquarantatre volte.
    """
    from _comune import ROOT
    app = ROOT / "hiris" / "app"
    fuori: dict[str, set[str]] = {}
    for cartella in sorted(p for p in app.iterdir() if p.is_dir()):
        if cartella.name in ("__pycache__", "static"):
            continue
        pezzi: set[str] = set()
        for f in rinomina.file_py(cartella):
            try:
                tk = list(tokenize.generate_tokens(
                    io.StringIO(rinomina._leggi_grezzo(f)).readline))
            except (tokenize.TokenError, IndentationError, SyntaxError):
                continue
            for t in tk:
                if t.type == tokenize.NAME:
                    pezzi.update(p.lower() for p in rinomina.spezza(t.string))
        fuori[cartella.name] = pezzi
    return fuori


def test_ogni_parola_qualificata_e_muta_solo_dove_e_dichiarato():
    """Il cancello sulla cecita' per ambito.

    Qualificare una parola per UN ambito (`riga (api)`) spegne la riga nuda per
    TUTTI gli altri: e' documentato nel glossario da settimane, ma non lo
    controllava nessuno -- e infatti `riga` era muta in `proxy/`, `agent/` e in
    sei file di ambiti STABILI senza che il dry-run lo dicesse.

    Uguaglianza esatta nelle due direzioni, come `_NOTE_ITALIANE`: una coppia
    nuova e' una domanda da porsi (qualificare anche li', o e' un senso
    diverso?), una coppia sparita e' un'eccezione da togliere.

    L'insieme atteso e' l'unione di due, e il messaggio lo dice: `_MUTE_VOLUTE`
    non cala mai (senso diverso, mutezza giusta), `_MUTE_PROVVISORIE` si
    esaurisce a ogni sottosistema convertito.

    Provato per mutazione: tolta la riga `note (casa)` dal glossario, questo
    test va rosso nominando `('note', 'casa')` fra le coppie mai viste prima;
    rimessa, torna verde.

    **La mutazione ovvia NON funziona, ed e' istruttivo**: togliere
    `riga (proxy)` non fa arrossire niente, perche' dopo il lotto 18 in
    `proxy/` non c'e' piu' nessun identificatore che porti il pezzo `riga`
    -- la parola non e' piu' usata li', quindi non puo' essere muta li'.
    Questo cancello vede una parola qualificata solo se qualcuno la USA
    ancora: e' cio' che lo rende leggibile (nessuna coppia inventata) e
    insieme il suo limite dichiarato (una riga qualificata che non serve
    piu' a nessuno resta scritta, e nessuno lo sa).
    """
    g = rinomina.leggi_glossario()
    pezzi = _pezzi_per_ambito()
    mute = {(parola, ambito)
            for parola in g.omonimi
            for ambito, usati in pezzi.items()
            if parola in usati and g.per(parola, ambito) is None}
    nuove = sorted(mute - _MUTE_NOTE)
    sparite = sorted(_MUTE_NOTE - mute)
    assert not nuove, (
        "parole qualificate MUTE in un ambito che le usa, mai viste prima: "
        + ", ".join(f"{p} in {a}" for p, a in nuove)
        + " -- lo strumento non le vedra' e il dry-run non le nominera'. "
          "Decidi: qualificala anche per quell'ambito (`parola (ambito)`), "
          "oppure dichiara qui che li' e' un senso diverso, con la ragione.")
    assert not sparite, (
        "coppie dichiarate mute che non lo sono piu': "
        + ", ".join(f"{p} in {a}" for p, a in sparite)
        + " -- o la parola e' stata qualificata anche li' (bene: togli la "
          "riga), o non e' piu' usata in quell'ambito. Se viene da "
          "`_MUTE_PROVVISORIE` e' l'esito atteso di una conversione; se "
          "viene da `_MUTE_VOLUTE`, guarda perche': quell'insieme non "
          "dovrebbe calare da solo.")


def test_una_sponda_verso_un_COSTRUTTORE_porta_il_nome_della_classe():
    """Un costruttore non si chiama col suo nome, e l'asse del nome chiamato
    deve saperlo.

    `__init__` non compare mai in un sito di chiamata: li' c'e' il nome della
    CLASSE (`ReasoningQueue(leggi_fuso=...)`). Senza questa traduzione l'asse
    nuovo del controllo di chiusura non riconoscerebbe MAI una sponda verso un
    costruttore -- e in un sottosistema che espone una classe sola sono le
    uniche che ci siano.

    Trovato aprendo `reasoning/`, il primo ambito convertito con tutte e
    quattro le reti in piedi: la rete lo ha rivelato prima di sbagliare, non
    dopo. Provato per mutazione: tolta la traduzione, `firme_rinominate`
    restituisce `{'__init__'}` e nessuna delle tre chiamate a
    `ReasoningQueue(leggi_fuso=...)` verrebbe classificata come sponda.
    """
    gf = rinomina.Glossario(mappa={"fuso": "timezone"})
    dentro = ("class Coda:\n"
              "    def __init__(self, db, *, fuso=None):\n"
              "        self.f = fuso\n")
    assert rinomina.firme_rinominate(dentro, gf, "reasoning") == {"Coda"}
    assert rinomina.parametri_def_rinominati(dentro, gf, "reasoning") == {"fuso": "timezone"}


def test_un_metodo_normale_porta_il_proprio_nome_non_quello_della_classe():
    """La controprova: la traduzione vale SOLO per `__init__`. Un metodo
    qualunque si chiama col proprio nome anche nel sito di chiamata, e
    sostituirlo con quello della classe renderebbe l'asse cieco su tutto il
    resto."""
    gf = rinomina.Glossario(mappa={"fuso": "timezone"})
    dentro = ("class Coda:\n"
              "    def leggi(self, fuso=None):\n"
              "        return fuso\n")
    assert rinomina.firme_rinominate(dentro, gf, "reasoning") == {"leggi"}


def test_sponde_per_nome_non_scambia_un_percorso_di_import_per_un_attributo(tmp_path):
    """`from ..casa.strumenti import X` porta `.strumenti` in posizione di
    attributo, ma quello e' il nome di un MODULO -- e un modulo si rinomina con
    `git mv`, non riscrivendo la stringa dell'import.

    Misurato aprendo `backends/`, dove il parametro `strumenti` di `chat()`
    doveva diventare `tools`: senza questa distinzione la terza rete dava **34
    segnalazioni, 32 delle quali erano `casa.strumenti`** in trenta file. Un
    elenco cosi' non si legge -- ed e' il difetto n.1 del progetto («un elenco
    che dice sempre qualcosa») applicato al rimedio invece che al male.

    Provato per mutazione: tolto il filtro sul percorso, questo test vede
    ricomparire la riga dell'import.
    """
    (tmp_path / "importa.py").write_text(
        "from pacchetto.strumenti import qualcosa\n"
        "import pacchetto.strumenti\n", encoding="utf-8")
    (tmp_path / "vero.py").write_text(
        "x = oggetto.strumenti\n", encoding="utf-8")
    trovati = rinomina.sponde_per_nome({"strumenti": "tools"}, radice=tmp_path)
    assert {f.name for f, _, _, _, _ in trovati} == {"vero.py"}, trovati


def test_il_residuo_di_backends_e_solo_la_famiglia_dei_runner(tmp_path):
    """La grana FINE del residuo di `backends/openai_compat_runner.py`.

    Un'eccezione a grana di file nasconderebbe un secondo debito nato dopo per
    un'altra ragione -- e' successo con `memoria/resolver.py`. Qui l'insieme
    atteso ha tre coppie, ed e' ESATTO: sono le tre parole che compongono
    l'interfaccia duck-typed condivisa con `claude_runner.py`.

    Quando i moduli di radice verranno convertiti, questo test si rompe e va
    TOLTO -- non allargato -- perche' il residuo sara' sparito.
    """
    import shutil

    from _comune import ROOT
    base = ROOT / "hiris" / "app" / "backends" / "openai_compat_runner.py"
    copia = tmp_path / "openai_compat_runner.py"
    shutil.copy(base, copia)
    prima = copia.read_text(encoding="utf-8")
    rinomina.applica(copia, "backends", scrivi=True)
    dopo = copia.read_text(encoding="utf-8")
    sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
    assert sostituzioni == {("modello", "model"), ("scelto", "chosen"),
                            ("strumenti", "tools")}, (
        f"backends/openai_compat_runner.py diverge su {sostituzioni}, attese "
        "solo le tre parole della famiglia dei runner -- un nome nuovo e' "
        "comparso: decidilo davvero invece di lasciarlo dentro un'eccezione "
        "a grana di file")


def test_il_triage_degli_orfani_mette_l_asse_del_NOME_CHIAMATO_per_primo():
    """Il cancello che mancava alla ritaratura del filtro.

    Misurato dalla review del 01/09: spegnendo l'asse nuovo dentro `main()`
    (`certi = []`, cioe' riportando il filtro esattamente alla RARITA' che il
    commit esisteva per sostituire) **la suite intera restava verde, 2966
    passed**. Era provato l'ingrediente -- `chiamanti_orfani` restituisce il
    nome chiamato -- non la ricetta. Una decisione nuova senza cancello e' una
    decisione che il prossimo annulla senza saperlo.

    Le tre righe qui sotto sono i tre casi che i due assi separano, e il caso
    (a) e' quello che l'asse vecchio non vede MAI: `nome` e' dichiarato da
    decine di firme del repo (quindi «ambiguo» per la rarita'), ma la chiamata
    e' a una firma che questo lotto ha cambiato -- quindi e' una sponda.

    Provato per mutazione: `sponde = []` in `triage_orfani` fa arrossire
    questo test e nient'altro.
    """
    percorso = Path("x.py")
    a = (percorso, 1, "nome", "name", "storico")       # sponda: firma cambiata
    b = (percorso, 2, "gesto", "operation", "_intento")  # nessuna def lo dichiara
    c = (percorso, 3, "nome", "name", "nota_ripiego")    # firma altrui, ambiguo
    sponde, mai, ambigui = rinomina.triage_orfani(
        [a, b, c], firme={"storico"}, dichiarati={"nome"})
    assert sponde == [a], sponde
    assert mai == [b], mai
    assert ambigui == [c], ambigui


def test_il_triage_non_promuove_a_sponda_una_chiamata_a_una_firma_altrui():
    """La controprova, e non e' un doppione: se l'asse nuovo fosse «qualunque
    chiamata», ogni `motivo=` del repo diventerebbe una sponda e l'elenco
    tornerebbe illeggibile -- il difetto che i due assi esistono per evitare.
    Solo le firme che QUESTO lotto ha cambiato contano."""
    percorso = Path("x.py")
    o = (percorso, 1, "motivo", "reason", "nota_ripiego")
    sponde, mai, ambigui = rinomina.triage_orfani(
        [o], firme=set(), dichiarati={"motivo"})
    assert sponde == [] and mai == [] and ambigui == [o]


def test_le_citazioni_si_ENUMERANO_col_contesto_e_non_si_riscrivono(tmp_path):
    """Lo strumento del giro finale: dichiara, non riscrive.

    Una citazione fra backtick puo' essere un PUNTATORE al codice di oggi
    (segue il codice) o un VERBALE che registra una misura passata (resta coi
    nomi di allora), e **nessun criterio meccanico le separa** -- misurato al
    costo di due giri annullati nel lotto 19c, il secondo dei quali ha
    prodotto la tautologia «`ha.statistics(...)` diventava `ha.statistics(...)`»,
    cioe' ha cancellato la misura che la frase esisteva per registrare.

    Cio' che manca non e' il criterio: e' l'ENUMERAZIONE. Senza, il giro si fa
    a memoria, file per file -- e la prova che non regge sono tre commenti
    fratelli con la stessa frase trattati in tre modi diversi.

    Il contesto e' la RIGA INTERA, perche' e' l'unica cosa che permette di
    decidere. E il file NON si tocca: questo test lo verifica leggendolo dopo.
    """
    f = tmp_path / "prosa.md"
    f.write_text("vedi `HAClient.storico` per la forma\n"
                 "prima `ha.storico()` diventava `ha.history()`\n"
                 "questa riga nomina storico senza backtick e non conta\n",
                 encoding="utf-8")
    prima = f.read_text(encoding="utf-8")
    trovate = rinomina.citazioni({"storico": "history"}, radice=tmp_path)
    assert [(r, v, n) for _, r, v, n, _ in trovate] == [
        (1, "storico", "history"), (2, "storico", "history")], trovate
    assert "diventava" in trovate[1][4], "il contesto e' la riga intera"
    assert f.read_text(encoding="utf-8") == prima, (
        "questo strumento DICHIARA: se riscrivesse, cancellerebbe i verbali")


def test_le_citazioni_si_cercano_in_ogni_estensione_di_testo(tmp_path):
    """Le estensioni si elencano per ESCLUSIONE, mai per inclusione.

    Un elenco per inclusione ne dimentica una la prossima volta che ne nasce
    un tipo: successo davvero (Task 9 round 8, la scansione elencava
    `.py/.js/.css/.html` e i 24 file di `tests/js/` sono `.mjs`).
    """
    (tmp_path / "a.mjs").write_text("// `storico` qui\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("`storico` anche qui\n", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"`storico`")
    trovate = rinomina.citazioni({"storico": "history"}, radice=tmp_path)
    assert {f.name for f, _, _, _, _ in trovate} == {"a.mjs", "b.txt"}


def test_i_nomi_ESPORTATI_non_sono_le_variabili_locali():
    """La cura che ha riportato la terza rete da 192 segnalazioni a 35.

    `sponde_per_nome` cerca un nome vecchio letto altrove come import o come
    attributo. Alimentata con TUTTO cio' che un lotto rinomina -- locali
    comprese -- su un file che usa parole comuni (`esito`, `nome`, `codice`)
    spara centinaia di volte, perche' un attributo omonimo di un ALTRO oggetto
    e' legittimo e frequente. **Una rete che spara 192 volte e' gia' spenta.**

    Una variabile locale non puo' essere una sponda per costruzione: nessuno la
    importa e nessuno la legge per attributo. Non appartiene alla domanda.

    Misurato su `agent/`: 192 -> 35, e zero sui tre sottosistemi gia'
    convertiti (dove non c'e' piu' niente da rinominare).
    """
    gf = rinomina.Glossario(mappa={"esito": "occurrence", "nome": "name",
                                   "archivio": "store"})
    dentro = ("ARCHIVIO = 1\n"
              "\n"
              "def nome(x):\n"
              "    esito = x + 1\n"
              "    return esito\n"
              "\n"
              "class Archivio:\n"
              "    nome = 'a'\n"
              "\n"
              "    def esito(self):\n"
              "        nome = 2\n"
              "        return nome\n")
    esportati = rinomina.nomi_esportati(dentro, gf, "qualunque")
    assert esportati == {"ARCHIVIO": "STORE", "nome": "name",
                         "Archivio": "Store", "esito": "occurrence"}, esportati


def test_una_definizione_annidata_in_una_funzione_non_e_esportata():
    """Una classe definita dentro il corpo di una funzione non la esporta
    nessuno: nessun import puo' nominarla, nessun attributo puo' leggerla da
    fuori. Resta fuori dalla domanda -- ed e' la ragione per cui questa
    funzione legge l'AST e non i token: «e' al livello del modulo o della
    classe» e' una domanda sulla STRUTTURA."""
    gf = rinomina.Glossario(mappa={"esito": "occurrence"})
    dentro = ("def prova():\n"
              "    class esito:\n"
              "        pass\n"
              "    return esito\n")
    assert rinomina.nomi_esportati(dentro, gf, "qualunque") == {}


def test_chiudi_sponde_chiude_i_nomi_importati_e_gli_attributi_approvati(tmp_path):
    """L'altra meta' della terza rete: la stessa rilevazione, applicata ai siti
    che un umano ha approvato.

    Erano due meta' che non si parlavano -- `sponde_per_nome` segnalava i nomi
    importati e nessuno li chiudeva -- ed e' la SECONDA volta che questa forma
    di difetto compare nello stesso strumento (la prima fu
    `parametri_def_rinominati`/`chiamanti_orfani`, uniti al round 8).

    Un sito approvato e un sito applicato non possono divergere: sono lo stesso
    calcolo (`_sponde_tokenizzate`).

    E gli import si toccano per POSIZIONE SINTATTICA: il giro annullato di
    `agent/` e' finito male su una regex sulle righe di import, troppo larga.
    """
    f = tmp_path / "usa.py"
    f.write_text("from pacchetto.modulo import vecchio_nome\n"
                 "x = oggetto.vecchio_nome\n"
                 "vecchio_nome = 1\n", encoding="utf-8")
    siti = rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path)
    assert {s[4] for s in siti} == {"import", "attributo"}, siti
    assert rinomina.chiudi_sponde(siti) == 2
    dopo = f.read_text(encoding="utf-8")
    assert dopo == ("from pacchetto.modulo import new_name\n"
                    "x = oggetto.new_name\n"
                    "vecchio_nome = 1\n"), dopo


def test_chiudi_sponde_non_tocca_un_sito_che_non_e_stato_approvato(tmp_path):
    """La controprova, ed e' cio' che rende usabile la coppia: la rete dichiara
    TUTTO, l'umano ne approva una parte, e si chiude solo quella. Un attributo
    omonimo di un altro oggetto resta dov'e'."""
    f = tmp_path / "usa.py"
    f.write_text("a = mio.vecchio_nome\n" "b = altrui.vecchio_nome\n", encoding="utf-8")
    siti = rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path)
    approvati = [s for s in siti if s[1] == 1]
    assert rinomina.chiudi_sponde(approvati) == 1
    assert f.read_text(encoding="utf-8") == ("a = mio.new_name\n"
                                             "b = altrui.vecchio_nome\n")
