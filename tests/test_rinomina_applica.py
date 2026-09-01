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

    Provato per mutazione: tolto il blocco che emette `DefinizioneProtetta` da
    `riscrivi`, questo test va rosso mentre TUTTI gli altri restano verdi --
    cioe' nessun cancello esistente vedeva il difetto.
    """
    gf = rinomina.Glossario(mappa={"statistiche": "statistics"})
    dentro = ("class HAClient:\n"
              "    async def statistiche(self, ids):\n"
              "        return ids\n")
    fuori, proposte = rinomina.riscrivi(dentro, gf, "proxy")
    assert "async def statistics(self, ids):" in fuori, (
        "la `def` si rinomina davvero: il lotto che possiede la classe deve "
        "poterlo fare")
    dichiarate = [p for p in proposte if isinstance(p, rinomina.DefinizioneProtetta)]
    assert len(dichiarate) == 1, proposte
    assert (dichiarate[0].nome, dichiarate[0].nuovo, dichiarate[0].riga) == (
        "statistiche", "statistics", 2)


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
