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
    fuori, _ = rinomina.riscrivi("archivio = 1\n", g, "memory")
    assert fuori == "store = 1\n"


def test_NON_tocca_i_commenti(g):
    """IL CONFINE DEL MANDATO. «Solo ed esclusivamente cio' che e' codice»:
    il commento resta identico, parola per parola."""
    dentro = "# l'archivio dei ricordi\narchivio = 1\n"
    fuori, _ = rinomina.riscrivi(dentro, g, "memory")
    assert fuori == "# l'archivio dei ricordi\nstore = 1\n"


def test_NON_tocca_le_stringhe(g):
    """Le frasi che HIRIS dice al proprietario sono italiane e restano tali.
    E la stessa guardia protegge le query SQL: i nomi delle tabelle sono in
    stringhe, e il database e' fuori perimetro."""
    dentro = 'msg = "l\'archivio e\' pieno"\narchivio = 1\n'
    fuori, _ = rinomina.riscrivi(dentro, g, "memory")
    assert '"l\'archivio e\' pieno"' in fuori
    assert "store = 1" in fuori


def test_NON_tocca_le_query_sql(g):
    """La tabella `ricordi` non si tocca: il database e' fuori perimetro, e
    lo e' per costruzione perche' le query sono stringhe."""
    dentro = 'q = "SELECT * FROM ricordi"\nricordo = 1\n'
    fuori, _ = rinomina.riscrivi(dentro, g, "memory")
    assert 'FROM ricordi' in fuori


def test_i_composti_escono_come_proposte_e_il_file_NON_cambia(g):
    dentro = "archivio_casa = 1\n"
    fuori, proposte = rinomina.riscrivi(dentro, g, "home_space")
    assert fuori == dentro, "un composto non si applica da solo"
    assert [p.nome for p in proposte] == ["archivio_casa"]


def test_e_idempotente(g):
    """Rigirarlo non cambia nulla. Senza questa proprieta' non si potrebbe
    ri-applicare dopo una correzione senza rileggere tutto da capo."""
    uno, _ = rinomina.riscrivi("archivio = 1\n", g, "memory")
    due, _ = rinomina.riscrivi(uno, g, "memory")
    assert uno == due


def test_l_omonimo_segue_il_sottosistema(g):
    assert rinomina.riscrivi("ancora = 1\n", g, "memory")[0] == "tether = 1\n"
    assert rinomina.riscrivi("ancora = 1\n", g, "usage")[0] == "anchor = 1\n"


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
    rinomina.applica(tmp_path, "memory")
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
    fuori, _ = rinomina.riscrivi(dentro, g, "memory")
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
    rinomina.applica(tmp_path, "memory")
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
    rinomina.applica(tmp_path, "memory")
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
    rinomina.applica(f, "memory")
    assert f.read_text(encoding="utf-8") == "store = 1\n"


def test_un_percorso_di_import_non_si_tocca_anche_se_la_parola_e_decisa():
    """`from ..home_space.store import X`: `casa` e `archivio` sono un
    indirizzo verso un altro modulo, non identificatori del proprio
    ambito -- anche quando entrambi hanno una riga nel glossario finto.
    Misurato dal vivo (review del Task 5): senza questa guardia lo
    strumento riscriveva `from ..home_space.topology import ...` in
    `from ..home_space.topology import ...`, un `ModuleNotFoundError`
    certo perche' `home_space/` non viene rinominata da questo task."""
    gf = rinomina.Glossario(mappa={"casa": "home_space", "archivio": "store"})
    dentro = "from ..home_space.store import ArchivioCasa\narchivio = 1\n"
    fuori, _ = rinomina.riscrivi(dentro, gf, "qualunque")
    assert "from ..home_space.store import ArchivioCasa" in fuori, (
        "il percorso dell'import non deve cambiare")
    assert "store = 1" in fuori, (
        "un identificatore VERO, fuori dall'import, deve continuare a tradursi")


def test_un_percorso_di_import_semplice_senza_from_non_si_tocca():
    """`import home_space.store`: stessa guardia, forma senza `from`."""
    gf = rinomina.Glossario(mappa={"casa": "home_space", "archivio": "store"})
    dentro = "import home_space.store\n"
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
    dentro = "import home_space.store as archivio\n"
    fuori, _ = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "import home_space.store as store\n"


def test_una_parola_chiave_in_una_chiamata_non_si_applica_da_sola():
    """`f(origine=\"x\")`: una parola chiave in una chiamata potrebbe
    puntare a una funzione di un ambito non ancora convertito -- lo
    strumento non puo' saperlo, quindi non indovina: propone e si ferma,
    come un composto. Misurato dal vivo (review del Task 5): senza questa
    guardia, `origine=\"schedulatore\"` (verso
    `action/actuator.py::esegui(*, origine)`, non convertito) diventava
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
    `home_space/historian.py::trend`, un `AttributeError` in produzione perche'
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
    `storia` sono metodi PUBBLICI di un ambito gia' chiuso (`usage/`)
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
    """Quarta voce della guardia (Task 9, `api/handlers_chat.py`).

    **Il caso misurato era `registro.esito(...)`** su un `RegistroEsiti`:
    `esito -> occurrence` e' deciso da sempre, e senza questa voce il join
    produceva `registry.occurrence(...)`, cioe' un `AttributeError` alla prima
    chat che ripiega dal piano alla catena. **Quel caso oggi non esiste piu'**:
    dal lotto dei moduli di radice `esiti_provider.py` e' convertito, la classe
    si chiama `OccurrenceRegistry` e il metodo `occurrence` davvero.

    La guardia serve identica nel verso opposto -- il giorno in cui una parola
    inglese di quella classe entrasse nel glossario come traduzione di
    qualcos'altro -- e il glossario di questa prova e' sintetico apposta, cosi'
    misura il MECCANISMO e non lo stato di conversione del modulo."""
    gf = rinomina.Glossario(mappa={"successo": "success"})
    dentro = "esito = registry.successo(backend_name)" + chr(10)
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, (
        "l'attributo di OccurrenceRegistry non si applica da solo")
    assert [p.nome for p in proposte] == ["successo"]


def test_un_attributo_che_non_e_di_registroesiti_si_applica_normalmente():
    """La controprova, come per le altre tre voci: la guardia e' un elenco di
    nomi, non un blocco generico su ogni attributo dopo un punto."""
    gf = rinomina.Glossario(mappa={"esitante": "hesitant"})
    dentro = "x = registro.esitante()\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == "x = registro.hesitant()\n"
    assert proposte == []


def test_un_campo_di_impostazionichat_non_si_applica_da_solo():
    """Terza voce della stessa guardia (Task 9, `api/handlers_settings.py`):
    `ChatSettings` e' un dataclass, non una classe di servizio -- il
    rischio e' un CAMPO letto per attributo, non un metodo. `nome` e' una
    parola ordinaria gia' decisa (`-> name`); l'attributo vero del dataclass
    resta `nome` (`impostazioni_chat.py`, un file di radice, mai deciso).
    Misurato PRIMA di romperlo: senza questa guardia `corrente.nome`
    diventava `corrente.name` in una prova isolata su questo stesso
    snippet."""
    gf = rinomina.Glossario(mappa={"nome": "name"})
    dentro = "etichetta = corrente.nome\n"
    fuori, proposte = rinomina.riscrivi(dentro, gf, "qualunque")
    assert fuori == dentro, "il campo di ChatSettings non si applica da solo"
    assert [p.nome for p in proposte] == ["nome"]
    assert proposte[0].suggerito == "name"


def test_un_campo_che_non_e_di_impostazionichat_si_applica_normalmente():
    """La guardia su `ChatSettings` e' un allowlist quanto le altre due:
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
    dal vivo: `memory/resolver.py::_compila` aveva sia `inizio` (residuo
    dichiarato) sia `prefisso`/`suffisso` -- una meta' di quella seconda
    coppia era stata decisa nel glossario da questo stesso lotto per
    `home_space/tools.py`, e la guardia a grana di file non l'avrebbe vista
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
# `action/construction/composer.py`, vive invece in un ambito che questo
# test non guardava affatto. Allargato a tutti e sei.
#
# `home_space/` non e' ancora finito (`queries.py` e `briefing.py` restano in
# parte italiani, `tools.py` per intero): elencare la cartella intera
# pretenderebbe zero anche li', cosa falsa per costruzione. Si elencano
# invece i singoli file gia' chiusi, uno per lotto -- un dato esplicito
# che chi legge puo' contare, non un'assenza silenziosa. Quando l'ultimo
# lotto di `home_space/` chiude, le cinque righe si possono sostituire con
# `("home_space", "home_space", frozenset())`.
#
# `residui_noti` per `memoria`: `resolver.py::Lookup.find` ha `inizio`
# ancora italiano -- **deliberatamente**, review del lotto 5: tradurlo da
# solo (`inizio -> start`) senza il suo gemello nella stessa espressione
# (`fine`, mai deciso nel glossario) avrebbe lasciato una coppia a meta'
# tradotta (`start, fine = m.span()`), la STESSA asimmetria che ha
# motivato la qualificazione `dopo (home_space)` invece di lasciarlo nudo. La
# correzione tocca solo file gia' miei (`queries.py`), non `resolver.py`
# per intero (~30 identificatori italiani restano li', fuori dal
# perimetro): chiudere le coppie (`fine -> end`,
# `inizio_originale`/`fine_originale`, `candidati`) e' un giro a se',
# rimandato al lotto che convertira' `memory/` per intero -- e servirebbe
# comunque a poco: due nomi corretti non avvicinano il file a
# "convertito".
#
# `residui_noti` per `azione`: `construction/composer.py` ha ancora
# `candidato` (due funzioni private) e il parametro PUBBLICO keyword-only
# `modo` di `compose_automation`/`compose_script` in italiano -- entrambi
# parole gia' decise. **Corretto durante la review del lotto 5**: `modo`
# non ha ZERO chiamanti che lo passano per keyword in tutto il repo
# (verificato con un grep, non presunto) -- il rinvio non e' perche'
# cercarli costerebbe caro, e' semplicemente che `action/` non e' un file
# di questo lotto: rinominare un parametro pubblico, anche a costo zero,
# resta un giro a se', rimandato al lotto che convertira' `action/`.
#
# `schedulatore` mostra `frozenset()` (nessun residuo) qui sotto, ed e'
# VERO -- lo strumento non cambia nulla su quell'ambito -- ma non e'
# COMPLETO: `AgendaStore.list::solo_in_sospeso` (`store.py:213`) e'
# ancora italiano, invisibile perche' nessuno dei suoi tre pezzi (`solo`,
# `in`, `sospeso`) e' mai stato deciso -- non una parola gia' decisa
# rimandata (come `modo` sopra), una parola MAI vista dal glossario.
# Questa guardia misura stabilita', non completezza (Task 9, scoperto
# convertendo `api/handlers_agenda.py`, che chiama gia' questo
# parametro per keyword e lo lascia intatto): tracciato a grana di parola
# in `test_il_residuo_di_schedulatore_archivio_e_solo_solo_in_sospeso`,
# non qui, perche' non c'e' nessun `prima`/`dopo` da confrontare quando
# lo strumento non tocca nulla.
#
# **Corretto il 02/09, dalla fetta dei nomi degli strumenti.** La riga qui
# sopra non e' piu' vera: `schedulatore` porta ora DUE file di residuo. La
# causa non e' un lotto che ha convertito male, e' il passo 0 di quella
# fetta -- `concludi` e' il quattordicesimo strumento e il glossario non
# l'aveva mai nominato; deciderlo (`concludi -> conclude`, «I nomi degli
# strumenti») mette la parola nella mappa piatta, e da quel momento
# `AgendaStore.concludi` e i suoi chiamanti dentro `keeper/` sono
# identificatori GIA' DECISI e non piu' invisibili.
#
# **Non e' un debito nuovo: e' lo stesso debito, che smette di essere
# invisibile.** Era gia' scritto -- «`store.concludi(...)`/
# `_senza_conclusione` lasciati intatti di proposito ... mai decisi»
# (docs/GLOSSARIO.md, elenco del debito) -- e la ragione registrata li'
# («mai decisi») e' proprio quella che oggi cade. Quello che NON cambia e'
# il perimetro: la fetta del 02/09 converte i NOMI DEGLI STRUMENTI, cioe'
# le stringhe che il modello legge, non gli identificatori Python di un
# ambito gia' chiuso -- e applicare `concludi -> conclude` qui sarebbe una
# rinomina a meta', perche' `server.py:122`,
# `api/handlers_reasoning.py:67` e `api/handlers_mcp.py:474` chiamano
# `store.concludi(...)`/`sweeper.concludi_chiedi(...)` da FUORI
# dell'ambito, dove un giro limitato a `keeper` non li vedrebbe.
# Tracciato qui, con la grana fine sotto, invece che applicato di sfuggita.
_SORVEGLIATI: tuple[tuple[str, str, frozenset], ...] = (
    ("keeper", "keeper",
     frozenset({Path("store.py"), Path("sweeper.py")})),
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
    # `agent` entra il 01/09, senza residui, al SECONDO tentativo: il primo e'
    # stato annullato perche' la mappa conteneva nomi che sembravano suoi e non
    # lo erano (cinque costanti importate da `chat_store.py`, la famiglia dei
    # runner). Le nove proposte che restano nel dry-run sono tutte di ALTRI
    # moduli -- cinque nomi importati, due parole chiave di firme altrui -- e
    # non sono residui: sono nomi che questo ambito non possiede.
    ("agent", "agent", frozenset()),
    # `backends` e' entrato il 01/09 con un residuo dichiarato -- le tre
    # parole della famiglia dei runner, che non si potevano tradurre a meta'
    # perche' `claude_runner.py` portava la stessa interfaccia duck-typed.
    # **Il residuo e' USCITO col lotto dei moduli di radice**, che ha
    # convertito i due runner nello stesso commit: qui resta la riga senza
    # eccezioni, e il canarino a grana fine e' stato tolto invece che
    # aggiornato -- e' la disciplina scritta per `memory/resolver.py`.
    ("backends", "backends", frozenset()),
    ("memory", "memory", frozenset({Path("resolver.py")})),
    ("usage", "usage", frozenset()),
    ("mind", "mind", frozenset()),
    ("action", "action", frozenset({Path("construction/composer.py")})),
    ("home_space/yaml_loader.py", "home_space", frozenset()),
    ("home_space/behavior.py", "home_space", frozenset()),
    ("home_space/store.py", "home_space", frozenset()),
    ("home_space/historian.py", "home_space", frozenset()),
    ("home_space/topology.py", "home_space", frozenset()),
    ("home_space/queries.py", "home_space", frozenset()),
    ("home_space/briefing.py", "home_space", frozenset()),
    # **L'eccezione di `tools.py` e' USCITA il 02/09, sciolta dalla rinomina dei
    # file invece che aggirata.** Diceva: `strumenti.py` importa il vicino con
    # `from . import tempo`, e la protezione dei percorsi di import
    # (`_righe_di_percorso_e_parola_chiave`) non copre quella forma -- "tempo"
    # arriva DOPO "import", quindi resta un NAME qualunque e lo strumento lo
    # riscriveva in `from . import historian`, cioe' un `ModuleNotFoundError`,
    # **perche' il file si chiamava ancora `tempo.py`**. Ora si chiama
    # `historian.py`: quella riscrittura e' esattamente quella giusta, la
    # divergenza sparisce e l'eccezione non ha piu' niente da coprire.
    # Il buco dello strumento resta (la forma `from . import X` non e'
    # protetta): e' scritto qui perche' il prossimo che ci inciampa lo sappia.
    ("home_space/tools.py", "home_space", frozenset()),
)


def test_gli_ambiti_chiusi_restano_idempotenti(tmp_path):
    """La guardia sui sei ambiti (cinque interi piu' i file gia' chiusi di
    `home_space/`, vedi `_SORVEGLIATI` sopra): una regressione futura (in questo
    script o nel glossario) si vede qui, sull'ambito dove e' successa,
    invece di scoprirsi per caso al prossimo lotto che tocca quell'ambito."""
    from _comune import ROOT
    for percorso, ambito, residui_noti in _SORVEGLIATI:
        etichetta = percorso.replace("/", "_")
        _verifica_idempotenza(ROOT / "hiris" / "app" / percorso, ambito,
                              tmp_path / etichetta, residui_noti)


def test_il_residuo_di_memoria_resolver_e_solo_inizio_start(tmp_path):
    """La grana FINE del residuo noto di `memory/resolver.py` (sopra, in
    `_SORVEGLIATI`): non basta sapere che il file diverge, serve sapere
    COSA cambia -- l'eccezione a grana di file l'ha gia' nascosto una volta
    (vedi `_sostituzioni_di_identificatori`). Se domani un'altra parola di
    `resolver.py` entra nel glossario per un altro lotto, questa prova
    arrossisce ANCHE SE il file resta nell'elenco dei cambiati sopra."""
    import shutil

    from _comune import ROOT
    base = ROOT / "hiris" / "app" / "memory" / "resolver.py"
    copia = tmp_path / "resolver.py"
    shutil.copy(base, copia)
    prima = copia.read_text(encoding="utf-8")
    rinomina.applica(copia, "memory", scrivi=True)
    dopo = copia.read_text(encoding="utf-8")
    sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
    assert sostituzioni == {("inizio", "start")}, (
        f"memory/resolver.py diverge su {sostituzioni}, atteso solo "
        "{('inizio', 'start')} -- un nuovo nome e' comparso: decidilo "
        "davvero (applicalo, o traccialo qui) invece di lasciarlo dentro "
        "un'eccezione a grana di file")


def test_il_residuo_di_schedulatore_e_solo_concludi_conclude(tmp_path):
    """La grana FINE del residuo di `schedulatore` (sopra, in `_SORVEGLIATI`),
    nato il 02/09 quando `concludi` e' stato deciso nel glossario: due file
    divergono, e su una SOLA coppia. `concludi_chiedi` non compare -- e' un
    composto il cui secondo pezzo (`chiedi`) non e' mai stato deciso, quindi
    lo strumento non lo applica da solo -- ed e' proprio il genere di cosa
    che l'eccezione a grana di file nasconderebbe se comparisse domani."""
    import shutil

    from _comune import ROOT
    for nome in ("store.py", "sweeper.py"):
        base = ROOT / "hiris" / "app" / "keeper" / nome
        copia = tmp_path / nome
        shutil.copy(base, copia)
        prima = copia.read_text(encoding="utf-8")
        rinomina.applica(copia, "keeper", scrivi=True)
        dopo = copia.read_text(encoding="utf-8")
        sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
        assert sostituzioni == {("concludi", "conclude")}, (
            f"keeper/{nome} diverge su {sostituzioni}, atteso solo "
            "{('concludi', 'conclude')} -- un nuovo nome e' comparso: "
            "decidilo davvero (applicalo, o traccialo qui) invece di "
            "lasciarlo dentro un'eccezione a grana di file")


def test_il_residuo_di_azione_composer_e_solo_candidato_e_modo(tmp_path):
    """Il terzo gemello: `action/construction/composer.py` in `_SORVEGLIATI`
    porta DUE parole (`candidato`, `modo`), non una -- l'insieme atteso ha
    due elementi, non uno, ed e' comunque ESATTO: un terzo nome che comparisse
    domani deve far arrossire questa prova, non allargarla in silenzio."""
    import shutil

    from _comune import ROOT
    base = ROOT / "hiris" / "app" / "action" / "construction" / "composer.py"
    copia = tmp_path / "composer.py"
    shutil.copy(base, copia)
    prima = copia.read_text(encoding="utf-8")
    rinomina.applica(copia, "action", scrivi=True)
    dopo = copia.read_text(encoding="utf-8")
    sostituzioni = _sostituzioni_di_identificatori(prima, dopo)
    assert sostituzioni == {("candidato", "candidate"), ("modo", "mode")}, (
        f"azione/construction/composer.py diverge su {sostituzioni}, atteso "
        "solo {('candidato', 'candidate'), ('modo', 'mode')} -- un nuovo "
        "nome e' comparso: decidilo davvero (applicalo, o traccialo qui) "
        "invece di lasciarlo dentro un'eccezione a grana di file")


def test_il_residuo_di_schedulatore_archivio_e_solo_solo_in_sospeso():
    """Un quarto residuo, di una specie diversa dai tre sopra: qui lo
    strumento non ha NIENTE da applicare, quindi non c'e' un `prima`/`dopo`
    da confrontare con `_sostituzioni_di_identificatori`.

    `AgendaStore.list` (`keeper/store.py:213`) ha ancora il
    parametro keyword-only `solo_in_sospeso: bool = False`, mai deciso: i
    suoi tre pezzi (`solo`, `in`, `sospeso`) sono tutti fuori dal
    glossario, quindi `classifica()` torna `None` per ciascuno e la parola
    e' invisibile al dry-run come al join meccanico -- verificato
    eseguendo `python scripts/rinomina.py --percorso hiris/app/keeper
    --ambito keeper --dry-run`: non compare ne' fra i composti ne'
    applicata. Per questo `_SORVEGLIATI` dichiara `keeper` con
    residuo `frozenset()` (vuoto): la guardia di idempotenza e' vera --
    lo strumento non cambia nulla, quindi e' stabile -- ma stabile non
    e' completo. La firma vera e' un canarino diretto sul parametro,
    non un confronto testuale: se domani qualcuno rinomina
    `solo_in_sospeso` (decidendo le sue tre parole nel glossario e
    applicandole, il modo per farlo SPARIRE invece di restare tracciato),
    questo test si rompe con un messaggio che spiega perche', invece di
    restare silenziosamente disallineato.

    Due chiamanti pubblici usano gia' questo nome esatto per keyword, ed
    e' per questo che nessuno dei due lo tocca: `api/handlers_agenda.py`
    (`store.list(solo_in_sospeso=not show_all, ...)`, Task 9 di questa
    fetta) e `home_space/tools.py:1630` (gia' chiuso). Se le tre parole
    vengono decise un domani, tutti e due i chiamanti vanno aggiornati
    nello stesso commit del parametro, non lasciati indietro."""
    import inspect

    from hiris.app.keeper.store import AgendaStore

    parametri = inspect.signature(AgendaStore.list).parameters
    assert "solo_in_sospeso" in parametri, (
        "il residuo tracciato qui e' sparito: se e' stato deciso e "
        "applicato per davvero (keeper/store.py, "
        "api/handlers_agenda.py, home_space/tools.py, i due test dedicati), "
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
        _verifica_idempotenza(modulo, "memory", tmp_path / "copia.py")


def test_un_residuo_noto_dimenticato_arrossisce_anche_lui(tmp_path):
    """Il gemello nella direzione opposta: se un `residuo_noto` smette di
    divergere davvero (qualcuno l'ha corretto altrove) e nessuno toglie la
    riga da `_SORVEGLIATI`, la lista mentirebbe silenziosamente -- questa
    prova dimostra che l'uguaglianza `cambiati == residui_noti` e' ESATTA,
    non un `>=`, quindi un'eccezione dimenticata si vede."""
    modulo = tmp_path / "sorgente.py"
    modulo.write_text("x = 1\n", encoding="utf-8")  # niente da rinominare
    with pytest.raises(AssertionError):
        _verifica_idempotenza(modulo, "memory", tmp_path / "copia.py",
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
    # per intero o dentro residui gia' dichiarati (`memory/resolver.py`,
    # `keeper/exchange.py::_senza_conclusione`).
    ("senza", "api"), ("senza", "action"), ("senza", "memory"),
    ("senza", "keeper"),
    # `note (home_space)` vuol dire «cose che la casa SA» (-> `known`). Fuori da
    # `home_space/` `note` sono annotazioni, un senso diverso: la mutezza e' giusta.
    ("note", "api"), ("note", "action"), ("note", "usage"),
    ("note", "keeper"),
    # `note` in `radice` non e' italiano affatto: e' l'INGLESE che ci ha messo
    # la conversione stessa (`nota -> note`, `decisione_modelli.py`). Il
    # cancello lo vede perche' guarda i PEZZI, e `note` e' anche un plurale
    # italiano: e' lo stesso incrocio gia' descritto per `workshop.py` accanto
    # alla riga `note (home_space)` del glossario, misurato una seconda volta.
    ("note", "radice"),
    # `dopo (home_space)` e' l'ordine temporale. In `action/` `dopo` e' la CHIAVE
    # JSON `"prima"`/`"dopo"` di un confronto di stati: valore di dominio,
    # italiano per decisione (vedi la riga `primo` del glossario).
    ("dopo", "action"),
    # `fuori (home_space)` e' «all'aperto». In `usage/` e `keeper/` e' «in
    # uscita»/«fuori finestra»: senso diverso, mutezza giusta.
    ("fuori", "usage"), ("fuori", "keeper"),
    # `lettura` e' qualificata `(casa)`/`(usage)`. In `keeper/` compare
    # solo dentro `SOLA_LETTURA`, dove e' «read-only»: terzo senso.
    ("lettura", "keeper"),
    # `loro`/`nostro` sono qualificate SOLO `(casa)`; in `action/verification.py`
    # stanno in una riga sola, e non sono state decise per quell'ambito.
    ("loro", "action"), ("nostro", "action"),
    # `("verifica", "casa")` e' USCITA il 02/09, e la ragione va letta perche'
    # riguarda tutto questo insieme: l'unica occorrenza del pezzo `verifica`
    # in `home_space/` non era un identificatore di `home_space/` -- era il PERCORSO
    # dell'import differito `from ..azione.verifica import verification`
    # dentro `tools.py`. Rinominata la cartella (`azione/verifica.py` ->
    # `action/verification.py`), il pezzo non compare piu' in quell'ambito e
    # la mutezza non esiste piu'. **Una voce di `_MUTE_VOLUTE` che viveva di
    # un percorso e non di un nome**: e' stato questo cancello a dirlo,
    # andando rosso da solo.
}

# ── 2. DA CONVERTIRE: la parola e' muta solo perche' il suo sottosistema non
# e' ancora stato convertito. **Questo insieme si esaurisce**, e ogni fetta lo
# fa calare: quando `agent/` sara' convertito queste righe spariscono, o
# diventano volute con una ragione scritta.
# **Vuoto dal 01/09**: `agent/` era l'ultimo dei tre, e convertendolo le
# quattro coppie sono sparite -- cioe' l'insieme si e' esaurito come la sua
# definizione prometteva. Resta scritto, e non cancellato, perche' i moduli
# di radice ne porteranno altre: un insieme vuoto DICHIARATO dice una cosa
# che un insieme cancellato non direbbe piu'.
_MUTE_PROVVISORIE = {
    # I moduli di RADICE, ancora da convertire: `decisione_modelli.py`,
    # `server.py`, `chat_store.py`, `token_interno.py`, `migrazione_opzioni.py`.
    # **Sono comparse il 01/09, appena il cancello ha smesso di guardare le sole
    # CARTELLE** -- prima erano invisibili, e una di loro (`lettura`) era gia'
    # costata un nome rimasto italiano (`cache_lettura`, `claude_runner.py`).
    # Ognuna va decisa quando tocchera' al suo file: qualificarla `(radice)`, o
    # dichiararla voluta con la ragione.
    # **`senza` e' sparita il 01/09** convertendo `decisione_modelli.py`: la
    # portava `senza_modello`, diventato `without_model`. E con lei sono
    # sparite `("piano", "api")` e `("piano", "agent")`, che stavano fra le
    # VOLUTE: le portavano `piano_ha_il_token` e `ALIAS_DEL_PIANO`, due nomi
    # importati da questo stesso file. **La lezione e' che una coppia muta puo'
    # vivere in un ambito che non la scrive**: spariscono convertendo un altro
    # file, non il loro.
    # **`piano` e' sparita l'01/09**, col secondo lotto di radice:
    # `semina_modello_del_piano -> seed_subscription_model` era il suo ultimo
    # portatore in un ambito che la scrive. Il senso *subscription* resta
    # irraggiungibile per costruzione, com'e' scritto accanto alla sua riga.
    ("fuori", "radice"), ("guarda", "radice"), ("riga", "radice"),
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

    def raccogli_pezzi(file) -> set[str]:
        pezzi: set[str] = set()
        for f in file:
            try:
                tk = list(tokenize.generate_tokens(
                    io.StringIO(rinomina._leggi_grezzo(f)).readline))
            except (tokenize.TokenError, IndentationError, SyntaxError):
                continue
            for t in tk:
                if t.type == tokenize.NAME:
                    pezzi.update(p.lower() for p in rinomina.spezza(t.string))
        return pezzi

    # **I moduli di RADICE sono un ambito, e il cancello non li guardava.**
    # Trovato dal lotto `radice`: `cache_lettura` (`claude_runner.py`) e' rimasto
    # italiano perche' `lettura` e' qualificata `(casa)`/`(usage)` e quindi
    # muta li' -- ma nessuna riga di questo elenco poteva dirlo, perche'
    # `iterdir()` filtrava sulle sole CARTELLE. Un cancello che guarda meta' del
    # perimetro non protegge meta': non protegge, e sembra di si'.
    fuori["radice"] = raccogli_pezzi(sorted(app.glob("*.py")))
    for cartella in sorted(p for p in app.iterdir() if p.is_dir()):
        if cartella.name in ("__pycache__", "static"):
            continue
        fuori[cartella.name] = raccogli_pezzi(rinomina.file_py(cartella))
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

    Provato per mutazione: tolta la riga `note (home_space)` dal glossario, questo
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

    **La prima stesura SOSTITUIVA `__init__` col nome della classe, e la frase
    che la giustificava era falsa alla lettera**: `super().__init__` e
    `Exception.__init__` compaiono in otto siti del repo, uno dei quali in
    `backends/openrouter_runner.py:69` -- l'ambito appena convertito. Cosi'
    l'asse nuovo diventava cieco sulle sponde via `super()`, cioe' la STESSA
    classe di cecita' che la cura esisteva per chiudere. Si dichiarano
    entrambi.
    """
    gf = rinomina.Glossario(mappa={"fuso": "timezone"})
    dentro = ("class Coda:\n"
              "    def __init__(self, db, *, fuso=None):\n"
              "        self.f = fuso\n")
    assert rinomina.firme_rinominate(dentro, gf, "reasoning") == {"Coda", "__init__"}, (
        "l'UNIONE, non la sostituzione: `super().__init__(db, fuso=...)` e "
        "`Exception.__init__` esistono davvero -- uno in "
        "`backends/openrouter_runner.py` -- e sostituire `__init__` col nome "
        "della classe chiuderebbe una cecita' aprendone un'altra")
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
    """`from ..home_space.tools import X` porta `.strumenti` in posizione di
    attributo, ma quello e' il nome di un MODULO -- e un modulo si rinomina con
    `git mv`, non riscrivendo la stringa dell'import.

    Misurato aprendo `backends/`, dove il parametro `strumenti` di `chat()`
    doveva diventare `tools`: senza questa distinzione la terza rete dava **34
    segnalazioni, 32 delle quali erano `home_space.tools`** in trenta file. Un
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


def test_le_citazioni_hanno_un_CONFINE_DI_PAROLA(tmp_path):
    """`storico` non e' `storicone`, e il confine e' l'unica cosa che lo dice.

    **Scritto il 02/09, curando la lentezza di `citazioni()`.** La cura sposta
    la compilazione del pattern fuori dal ciclo, e nel farlo riscrive
    l'espressione: e' esattamente il gesto in cui un confine di parola si perde
    senza che niente diventi rosso. I due test qui sopra non lo prendono --
    nelle loro finte `storico` non e' MAI sottostringa di un'altra parola,
    quindi passerebbero anche col confine tolto del tutto.

    Provato per mutazione: tolti i due confini dal pattern di `citazioni`,
    questo test va rosso e nessun altro si muove.
    """
    (tmp_path / "p.md").write_text(
        "`storico` e' il nome\n"
        "`storicone` non lo e', e nemmeno `lo_storico_vecchio`\n",
        encoding="utf-8")
    trovate = rinomina.citazioni({"storico": "history"}, radice=tmp_path)
    assert [r for _, r, _, _, _ in trovate] == [1], (
        "il confine di parola deve escludere `storicone` e `lo_storico_vecchio`: "
        f"trovate {trovate}")


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

    **Il terzo cambio e' la QUARTA posizione, e mancava**: in un file che fa
    `from X import vecchio`, ogni `vecchio` NUDO e' quel nome -- e' il legame
    dell'import a renderlo certo. Chiudendo i soli import, il lotto di `agent/`
    ha prodotto 38 errori `F401`/`F821` (import rinominato, usi rimasti
    indietro). Fuori da un file che importa, un nome nudo resta ambiguo e la
    rete non lo segnala nemmeno.
    """
    f = tmp_path / "usa.py"
    f.write_text("from pacchetto.modulo import vecchio_nome\n"
                 "x = oggetto.vecchio_nome\n"
                 "vecchio_nome = 1\n", encoding="utf-8")
    siti = rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path)
    assert {s[4] for s in siti} == {"import", "attributo"}, siti
    assert rinomina.chiudi_sponde(siti) == 3
    dopo = f.read_text(encoding="utf-8")
    assert dopo == ("from pacchetto.modulo import new_name\n"
                    "x = oggetto.new_name\n"
                    "new_name = 1\n"), dopo


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


def test_una_parola_scartata_non_si_raggiunge_per_singolarizzazione():
    """`g.per` torna `None` sia per «non decisa» sia per «SCARTATA», e senza la
    distinzione l'euristica del plurale scavalca la decisione.

    Misurato dal vivo (fetta «la rinomina», review del lotto di `backends/`):
    `code` e' scartata perche' e' INGLESE -- il campo `exc.status_code` -- ma
    `_radici_plurali("code")` la riporta a `coda -> tail`, e il dry-run
    proponeva `status_tail`. Correggere il NOME (`_code_of -> _status_code`) ha
    peggiorato il conto, da uno a due composti falsi: **la cura apparteneva al
    glossario, non a un'altra rinomina**.

    Provato per mutazione: tolta la condizione `chiave not in g.scartate`,
    questo test va rosso e `_status_code` torna a proporre `status_tail`.
    """
    gf = rinomina.Glossario(mappa={"coda": "tail"}, scartate={"code"})
    assert rinomina.classifica("code", gf, "qualunque") is None
    assert rinomina.classifica("_status_code", gf, "qualunque") is None
    # la controprova: un plurale NON scartato si raggiunge ancora, e resta
    # una PROPOSTA -- una singolarizzazione e' una supposizione morfologica,
    # mai una lettura diretta del glossario
    proposta = rinomina.classifica(
        "code", rinomina.Glossario(mappa={"coda": "tail"}), "qualunque")
    assert isinstance(proposta, rinomina.Proposta)
    assert proposta.suggerito == "tail"


def test_chiudi_sponde_segue_un_riassegnamento_che_ombreggia_un_import(tmp_path):
    """Il caso che il repo NON contiene, e che quindi va costruito.

    `chiudi_sponde` chiude anche un `vecchio = ...` in un file che fa
    `from X import vecchio`: e' coerente -- e' la STESSA legatura, e lasciare
    il riassegnamento col nome vecchio produrrebbe due nomi per una variabile
    sola -- ma nel repo non esiste nessun file che ombreggi un proprio import,
    quindi il comportamento non era esercitato da niente.

    **Un codice senza caso non e' provato**, ed e' il rovescio esatto del
    difetto n.1 di questo progetto: li' un test che non puo' fallire, qui un
    codice che non puo' essere esercitato. Dentro l'attrezzo che riscrive la
    codebase e' il posto peggiore dove lasciarlo.

    Provato per mutazione: tolto il ramo dei nomi nudi da `chiudi_sponde`, la
    riga `vecchio_nome = 1` resta indietro e questo test va rosso.
    """
    f = tmp_path / "ombra.py"
    f.write_text("from pacchetto.modulo import vecchio_nome\n"
                 "\n"
                 "def prepara():\n"
                 "    global vecchio_nome\n"
                 "    vecchio_nome = 1\n"
                 "    return vecchio_nome\n", encoding="utf-8")
    siti = rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path)
    assert [s[4] for s in siti] == ["import"], (
        "solo l'import e' una sponda dichiarata: i tre usi nudi non lo sono, "
        "ed e' proprio per questo che il ramo dei nomi nudi doveva esistere")
    assert rinomina.chiudi_sponde(siti) == 4
    assert f.read_text(encoding="utf-8") == (
        "from pacchetto.modulo import new_name\n"
        "\n"
        "def prepara():\n"
        "    global new_name\n"
        "    new_name = 1\n"
        "    return new_name\n")


def test_chiudi_sponde_non_segue_un_nome_nudo_in_un_file_che_non_lo_importa(tmp_path):
    """La controprova, ed e' il confine della regola: il legame dell'import
    rende CERTO che un nome nudo sia quello importato. Senza l'import, lo
    stesso nome nudo e' una variabile qualunque -- e questa funzione non lo
    tocca, esattamente come la rete non lo segnala."""
    f = tmp_path / "estraneo.py"
    f.write_text("vecchio_nome = 1\n" "x = oggetto.vecchio_nome\n", encoding="utf-8")
    siti = rinomina.sponde_per_nome({"vecchio_nome": "new_name"}, radice=tmp_path)
    assert [s[4] for s in siti] == ["attributo"]
    assert rinomina.chiudi_sponde(siti) == 1
    assert f.read_text(encoding="utf-8") == ("vecchio_nome = 1\n"
                                             "x = oggetto.new_name\n")


def test_chiudi_sponde_non_tocca_un_binding_DIVERSO_collo_stesso_nome(tmp_path):
    """«Ogni `vecchio` nudo E' quel nome» e' FALSO, e questo e' il caso che lo
    dimostra.

    La regola del ramo dei nomi nudi era: in un file che fa `from X import v`,
    ogni `v` nudo e' quel nome, perche' e' il legame dell'import a renderlo
    certo. **Non e' vero quando nello stesso file esiste un binding DIVERSO
    collo stesso nome**: un parametro di un'altra funzione, o una parola chiave
    verso una firma altrui. Li' `chiudi_sponde` riscriveva la firma di
    qualcun altro e la chiave di una chiamata altrui -- cinque token invece di
    uno.

    **Misurato: 63 siti nel repo** in cui un nome importato e' anche un binding
    diverso nello stesso file (`client`, `csrf_stretto`, `reference_frame`...).
    Bastava un lotto che rinominasse uno di quei nomi.

    La cura e' conservativa e la ragione e' che non c'e' modo di essere
    precisi senza analisi di scope: **se il file contiene un binding
    concorrente per quel nome, i nomi nudi NON si toccano** e resta solo cio'
    che la rete ha dichiarato (l'import). Meglio chiudere di meno e dirlo, che
    riscrivere la firma di un altro.
    """
    f = tmp_path / "ambiguo.py"
    f.write_text("from pacchetto.modulo import esito\n"
                 "\n"
                 "def altrui(esito=None):\n"
                 "    return esito\n"
                 "\n"
                 "x = altrui(esito=1)\n"
                 "y = esito\n", encoding="utf-8")
    siti = rinomina.sponde_per_nome({"esito": "occurrence"}, radice=tmp_path)
    assert [s[4] for s in siti] == ["import"], siti
    assert rinomina.chiudi_sponde(siti) == 1, (
        "con un binding concorrente nello stesso file si chiude SOLO l'import: "
        "gli usi nudi diventano ambigui, e la firma di `altrui` non e' nostra")
    assert f.read_text(encoding="utf-8") == (
        "from pacchetto.modulo import occurrence\n"
        "\n"
        "def altrui(esito=None):\n"
        "    return esito\n"
        "\n"
        "x = altrui(esito=1)\n"
        "y = esito\n")


def test_gli_attributi_d_istanza_sono_ESPORTATI_quanto_un_metodo():
    """`self.x = ...` assegnato dentro un metodo si legge da fuori come
    `oggetto.x`, e la terza rete e' l'UNICA che vede gli attributi: se la mappa
    non li porta, la rete tace su di loro.

    **Non e' costato niente fino ad `agent/`** (zero attributi `self.` in tutto
    il sottosistema) **e costa sui moduli di radice**:
    `RunnerBackendError.codice` e `.famiglia` (`claude_runner.py`) sono letti da
    fuori in otto siti di due file di test. La rete 1 vede il costruttore, la
    rete 3 -- l'unica che vede gli attributi -- non li avrebbe dichiarati.

    Le variabili LOCALI restano fuori, che e' il punto di `nomi_esportati`:
    `locale` qui non e' esportato da niente.
    """
    gf = rinomina.Glossario(mappa={"codice": "code", "famiglia": "family",
                                   "locale": "local"})
    dentro = ("class ErroreRunner(Exception):\n"
              "    def __init__(self, msg, *, famiglia=None, codice=None):\n"
              "        self.famiglia = famiglia\n"
              "        self.codice = codice\n"
              "        locale = 1\n"
              "        return locale\n")
    esportati = rinomina.nomi_esportati(dentro, gf, "radice")
    assert esportati == {"famiglia": "family", "codice": "code"}, esportati


def test_la_settima_rete_vede_un_attributo_letto_per_NOME(tmp_path):
    """La settima specie: un attributo letto come STRINGA.

    **Le prime sei le abbiamo trovate a caro prezzo; questa l'ha presa la suite
    andando rossa** -- `llm_router.py:231`, `getattr(exc, "famiglia", "altro")`
    su un `RunnerBackendError` i cui campi erano appena diventati
    `family`/`code`. Non e' un `def`, non e' un attributo per sintassi, non e'
    un import, non e' una parola chiave: **nessuna delle sei reti guarda dentro
    una stringa**, e nemmeno il linter -- un nome sbagliato li' si scopre in
    produzione.

    Validata contro l'albero vero di `c46e07c^`, dove il caso era ancora vivo:
    **due segnalazioni, esattamente i due siti** che la suite aveva preso per
    fortuna.
    """
    (tmp_path / "legge.py").write_text(
        'a = getattr(exc, "famiglia", "altro")\n'
        'b = hasattr(x, "codice")\n'
        'import operator\n'
        'c = operator.attrgetter("famiglia")\n', encoding="utf-8")
    trovati = rinomina.accessi_dinamici({"famiglia": "family", "codice": "code"},
                                        radice=tmp_path)
    assert [(r, v, n, forma) for _, r, v, n, forma in trovati] == [
        (1, "famiglia", "family", "getattr"),
        (2, "codice", "code", "hasattr"),
        (4, "famiglia", "family", "attrgetter")], trovati


def test_la_settima_rete_non_guarda_ogni_stringa_del_repo(tmp_path):
    """La controprova, ed e' il confine: **una stringa non e' un accesso
    dinamico**. Le chiavi JSON di questo prodotto portano gli stessi nomi
    italiani per decisione (`{"famiglia": ...}` e' un campo del contratto), e
    segnalarle renderebbe l'elenco illeggibile -- il difetto n.1 applicato al
    rimedio.

    Si guardano solo le forme che leggono un attributo PER NOME, e sono un
    elenco corto e chiuso (`_FORME_DINAMICHE`).
    """
    (tmp_path / "dati.py").write_text(
        'riga = {"famiglia": "altro", "codice": None}\n'
        'msg = "la famiglia non e\' nota"\n'
        'x = chiamata("famiglia")\n', encoding="utf-8")
    assert rinomina.accessi_dinamici({"famiglia": "family", "codice": "code"},
                                     radice=tmp_path) == []


def test_le_reti_alimentate_dal_glossario_sono_cieche_su_cio_che_si_fa_a_mano():
    """**Il quasi-incidente dell'01/09, e la sua cura, nello stesso test.**

    Le sette reti sono nate dando per scontato che a rinominare fosse lo
    strumento, quindi si alimentavano da `classifica()`. Ma da `api/` in poi
    ogni lotto ha una parte fatta A MANO -- le trappole di senso, gli omonimi,
    i nomi che il glossario farebbe mentire -- e su quella parte erano CIECHE.

    Misurato su `decisione_modelli.py`: 27 nomi esportati rinominati, di cui il
    glossario ne spiegava 6; la terza rete alimentata dal glossario dichiarava
    4 sponde, alimentata dalle coppie vere ne dichiarava 40, e fra le 36
    mancanti c'era l'import di `server.py:59` -- l'add-on che non parte.

    Qui il caso e' ridotto all'osso: `piano_ha_il_token` non e' nel glossario
    (`piano (abbonamento)` e' irraggiungibile per costruzione, con la sua
    ragione scritta accanto alla riga), quindi il glossario NON lo vede; le
    coppie del lavoro si'. **La mutazione e' il primo assert**: togliendo
    `coppie=` alla chiamata, il secondo assert torna vuoto.
    """
    sorgente = ("VARIABILE = 1\n"
                "def piano_ha_il_token():\n"
                "    return VARIABILE\n")
    g = rinomina.g_corrente()
    esportati_glossario = rinomina.nomi_esportati(sorgente, g, "radice")
    assert "piano_ha_il_token" not in esportati_glossario

    applicate = {"piano_ha_il_token": "subscription_has_token"}
    esportati_applicate = rinomina.nomi_esportati(sorgente, g, "radice", coppie=applicate)
    assert esportati_applicate == {"piano_ha_il_token": "subscription_has_token"}


def test_le_coppie_del_lavoro_si_leggono_dai_token_e_non_si_indovinano():
    """Due versioni dello stesso file: se i flussi di token NAME hanno la
    stessa lunghezza, la coppia i-esima si legge senza interpretare niente."""
    prima = "def componi_topologia(catena, esiti):\n    return catena, esiti\n"
    dopo = "def compose_topology(chain, occurrences):\n    return chain, occurrences\n"
    assert rinomina.coppie_misurate(prima, dopo) == {
        "componi_topologia": "compose_topology",
        "catena": "chain",
        "esiti": "occurrences"}


def test_un_file_che_non_e_una_pura_rinomina_si_dichiara_invece_di_indovinarlo():
    """**La guardia che rende il confronto onesto.** Se nello stesso giro
    qualcuno ha aggiunto o tolto codice, i due flussi non si allineano piu' e
    ogni coppia dopo il punto di scarto sarebbe inventata -- il modo peggiore
    di sbagliare, perche' ha l'aspetto di una misura. Si torna `None` e il
    chiamante mette il file fra quelli che le reti NON coprono.
    """
    prima = "def f(catena):\n    return catena\n"
    dopo = "def f(chain):\n    x = 1\n    return chain\n"
    assert rinomina.coppie_misurate(prima, dopo) is None


def test_l_ottava_rete_vede_una_parola_chiave_scritta_come_stringa(tmp_path):
    """L'OTTAVA specie, e come la settima l'ha trovata la suite andando rossa.

    `tests/test_decisione_modelli.py` aveva un involucro `def
    componi_topologia(**kw)` che faceva `kw.setdefault("esiti", {})` prima di
    inoltrare `**kw`. Rinominato il parametro, la chiave letterale e' rimasta
    indietro: `TypeError: got an unexpected keyword argument 'esiti'`. Non e'
    un attributo (`accessi_dinamici` guarda `getattr` e compagni), non e' una
    parola chiave per sintassi (`chiamanti_orfani` guarda `nome=`).
    """
    (tmp_path / "involucro.py").write_text(
        "def componi(**kw):\n"
        '    kw.setdefault("esiti", {})\n'
        '    kw["adesso"] = 0\n'
        "    return vero(**kw)\n", encoding="utf-8")
    trovati = rinomina.chiavi_inoltrate({"esiti": "occurrences", "adesso": "now"},
                                         radice=tmp_path)
    assert sorted((r, v, n) for _, r, v, n, _ in trovati) == [
        (2, "esiti", "occurrences"), (3, "adesso", "now")], trovati


def test_l_ottava_rete_chiede_l_INOLTRO_e_non_solo_la_chiave(tmp_path):
    """**La meta' che rende la specie una specie, e il conto che l'ha decisa.**

    Il criterio largo -- «ogni stringa letterale uguale a un nome rinominato»
    -- da' **1.424 occorrenze** sul solo lotto di `decisione_modelli.py`
    (`nome` da solo ne fa 391): le chiavi JSON di questo prodotto portano di
    proposito i nomi italiani, e una rete cosi' e' gia' spenta -- lo stesso
    incidente di `nomi_esportati` prima della cura. Il criterio stretto ne
    trova **cinque in tutto il repo**. Chiedere anche l'inoltro costa una riga
    e toglie il 99,6% del rumore.

    Provato per mutazione: togliendo il controllo `inoltra` da
    `_letterali_inoltrati`, questo test va rosso su tutte e tre le forme.
    """
    (tmp_path / "non_inoltra.py").write_text(
        "def legge(**kw):\n"
        '    return kw.get("esiti")\n'
        "def senza_kwargs(d):\n"
        '    return d["esiti"]\n'
        'JSON = {"esiti": 1}\n', encoding="utf-8")
    assert rinomina.chiavi_inoltrate({"esiti": "occurrences"},
                                      radice=tmp_path) == []


def test_l_ottava_rete_conta_cinque_siti_nel_prodotto():
    """Il perimetro si misura come il contenuto (regola scritta il 01/09 dopo
    il caso di `buchi`). Cinque involucri con `**kwargs` inoltrato in tutto il
    repo: tre `kwargs.get("model")` (`claude_runner.py`, `llm_router.py` due
    volte) e i due dell'involucro di `tests/test_decisione_modelli.py`. Se ne
    nasce un sesto, questo test lo dice: e' un posto dove una rinomina futura
    puo' rompersi in silenzio.
    """
    import ast

    trovati = []
    for f in rinomina.file_py(rinomina.ROOT):
        try:
            albero = ast.parse(rinomina._leggi_grezzo(f))
        except (SyntaxError, ValueError):
            continue
        trovati += [(rinomina.rel(f), chiave)
                    for chiave, _, _ in rinomina._letterali_inoltrati(albero)]
    assert sorted(trovati) == [
        ("hiris/app/claude_runner.py", "model"),
        ("hiris/app/llm_router.py", "model"),
        ("hiris/app/llm_router.py", "model"),
        ("tests/test_decisione_modelli.py", "now"),
        ("tests/test_decisione_modelli.py", "occurrences")], trovati


_DATACLASS = """
from dataclasses import dataclass

@dataclass
class ChatSettings:
    nome: str = "HIRIS"
    giorni_conservazione: int = 90
"""


def test_i_campi_di_una_dataclass_sono_parole_chiave_che_nessuna_def_dichiara():
    """La NONA specie, misurata l'01/09 convertendo `impostazioni_chat.py`.

    I campi di una `@dataclass` diventano parole chiave del costruttore che il
    decoratore genera a import time. Nessun `def` li dichiara, quindi il
    controllo di chiusura -- che legge i parametri delle `def` -- non li
    vedeva: `ChatSettings(giorni_conservazione=...)` in **ventidue siti**, e
    l'ha preso la suite andando rossa con `TypeError: got an unexpected
    keyword argument 'giorni_conservazione'`.

    E' la stessa forma gia' curata per `__init__` e il nome della classe, e
    per questo il nome chiamato e' la CLASSE. Il perimetro e' misurato: dodici
    `@dataclass` e 57 campi in tutto il repo, quindi niente rumore.

    Provato per mutazione: tolto il giro su `campi_dataclass` da
    `parametri_def_rinominati`, il primo assert va rosso; tolto da
    `firme_rinominate`, il secondo.
    """
    g = rinomina.g_corrente()
    coppie = {"giorni_conservazione": "retention_days"}
    assert rinomina.parametri_def_rinominati(
        _DATACLASS, g, "", coppie=coppie) == coppie
    assert rinomina.firme_rinominate(_DATACLASS, g, "", coppie=coppie) == {"ChatSettings"}


def test_una_classe_senza_dataclass_non_porta_parole_chiave():
    """Il confine: senza il decoratore non c'e' nessun costruttore generato, e
    quelle annotazioni sono attributi di classe -- che la TERZA rete copre
    gia' come attributi. Segnalarle qui sarebbe contarle due volte."""
    sorgente = _DATACLASS.replace("@dataclass\n", "")
    coppie = {"giorni_conservazione": "retention_days"}
    assert rinomina.parametri_def_rinominati(sorgente, rinomina.g_corrente(),
                                             "", coppie=coppie) == {}


def test_le_dataclass_del_prodotto_sono_dodici_e_i_campi_cinquantasette():
    """Il perimetro si misura come il contenuto. E' il conto che ha deciso di
    scrivere questa rete invece di dichiararla scoperta, come si e' fatto col
    criterio largo dell'ottava (1.424 occorrenze): dodici classi si leggono."""
    classi = campi = 0
    for f in rinomina.file_py(rinomina.ROOT):
        trovate = rinomina.campi_dataclass(rinomina._leggi_grezzo(f))
        classi += len(trovate)
        campi += sum(len(c) for c in trovate.values())
    assert (classi, campi) == (12, 57), (classi, campi)


def _repo_finto(tmp_path, prima: dict, dopo: dict) -> None:
    """Un repo git vero con un «prima» commesso e un «dopo» sul disco.

    `reti()` legge la revisione con `git cat-file` e il disco con `open()`:
    senza un repo vero non si esercita la funzione, si esercita una sua
    parafrasi -- ed e' proprio la differenza fra le due che questa fetta
    passa il tempo a inseguire.
    """
    import subprocess

    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "prova@hiris")
    git("config", "user.name", "prova")
    for nome, testo in prima.items():
        (tmp_path / nome).write_text(testo, encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "prima")
    for nome, testo in dopo.items():
        (tmp_path / nome).write_text(testo, encoding="utf-8")


def test_le_reti_dichiarano_le_firme_in_TUTT_E_DUE_LE_LINGUE(tmp_path, monkeypatch, capsys):
    """**Il modo `--reti` gira in un momento diverso da `main()`, e questo
    cambia in che lingua sono i chiamanti.**

    `main()` fa girare le reti subito dopo `applica()`, quando i chiamanti
    portano ancora il nome VECCHIO della firma. `reti()` gira a conversione
    fatta, quando molti lo portano gia' NUOVO -- un sito puo' avere il nome
    aggiornato e la parola chiave rimasta indietro, che e' esattamente la
    forma del guasto di `server.py:2764` (`risana(adesso=)` verso
    `def risana(*, now)`, in produzione dal 29 agosto).

    L'asse del chiamato chiede «il nome chiamato e' una firma che questo
    lotto ha cambiato?»: `firme_rinominate` legge il sorgente PRIMA e
    risponde col nome vecchio, quindi da sola non riconosce il sito. Serve
    dichiarare **entrambi** i nomi -- la stessa cura gia' scritta per
    `__init__` e il nome della classe.

    Provato per mutazione: tolta la riga `metodi |= {applicate.get(m, m) for
    m in metodi}` da `reti()`, il sito finisce fra gli «ambigui» e non viene
    piu' stampato come SPONDA -- questo test va rosso.
    """
    _repo_finto(
        tmp_path,
        prima={"mod.py": "def componi(catena):\n    return catena\n",
               "uso.py": "from mod import componi\n\ncomponi(catena=1)\n"},
        dopo={"mod.py": "def compose(chain):\n    return chain\n",
              # il chiamante ha seguito il NOME e non la PAROLA CHIAVE
              "uso.py": "from mod import compose\n\ncompose(catena=1)\n"})
    monkeypatch.setattr(rinomina, "ROOT", tmp_path)

    assert rinomina.reti("mod.py") == 0
    fuori = capsys.readouterr().out

    assert "2 nomi rinominati" in fuori, fuori
    assert "1 verso una firma di questo lotto" in fuori, fuori
    assert "compose(catena=...) -> chain=" in fuori, fuori


def test_le_reti_tacciono_quando_non_c_e_niente_da_dire(tmp_path, monkeypatch, capsys):
    """La controprova: un file che nessuno legge non produce sponde, e la
    funzione lo DICE invece di stampare il nulla -- un silenzio ambiguo fra
    «nessuna sponda» e «non ho guardato» sarebbe il difetto n.1 applicato
    all'attrezzo che lo cura."""
    _repo_finto(
        tmp_path,
        prima={"mod.py": "def componi(catena):\n    return catena\n"},
        dopo={"mod.py": "def compose(chain):\n    return chain\n"})
    monkeypatch.setattr(rinomina, "ROOT", tmp_path)

    assert rinomina.reti("mod.py") == 0
    assert "nessuna sponda aperta" in capsys.readouterr().out


def test_un_file_che_non_e_una_pura_rinomina_le_reti_lo_DICHIARANO(tmp_path, monkeypatch, capsys):
    """Il file che il confronto non sa leggere non sparisce in silenzio: viene
    nominato, con la ragione. E' la meta' che rende onesto `coppie_misurate`
    -- tornare `None` non serve a niente se poi il chiamante lo ignora."""
    _repo_finto(
        tmp_path,
        prima={"mod.py": "def componi(catena):\n    return catena\n"},
        dopo={"mod.py": "def compose(chain):\n    x = 1\n    return chain\n"})
    monkeypatch.setattr(rinomina, "ROOT", tmp_path)

    assert rinomina.reti("mod.py") == 0
    fuori = capsys.readouterr().out
    assert "non confrontabili" in fuori and "mod.py" in fuori, fuori
    assert "le reti NON li coprono" in fuori, fuori
