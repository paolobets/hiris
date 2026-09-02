"""Il rinominatore del frontend: propone, e non applica mai.

**Perche' due file e non uno.** Gli AMBITI del JavaScript li puo' ricostruire
solo un parser vero (`scripts/legami_js.mjs`, con `acorn`), e il glossario ce
l'ha gia' il Python (`scripts/rinomina_js.py`). Misurato: 1.542 dichiarazioni
portano 704 nomi distinti, e 202 nomi sono dichiarati piu' di una volta -- uno
strumento a token li tratterebbe come una cosa sola, che e' la classe di
`server.py` del 1 settembre moltiplicata per venti.

**Il lato `node` si salta quando `node` non c'e'**, ed e' voluto: il job
`pytest` del CI monta solo Python. Cio' che questo file pinna sempre e' il lato
delle decisioni, su un albero dei legami sintetico -- che e' anche il solo modo
di far PRODURRE alla finta i difetti che le guardie devono trovare.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rinomina_js


def _legami(*legami, proprieta=()):
    return {"finta.js": {"legami": list(legami), "liberi": [],
                         "proprieta": list(proprieta), "ambiti": 1}}


def test_un_nome_deciso_e_di_una_parola_sola_si_applica(capsys):
    dati = _legami({"nome": "pannello", "specie": "var", "ambito": 0,
                    "dich": [0], "rif": [10], "globale": False})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 1" in fuori
    assert "pannello -> panel" in fuori


def test_un_composto_diventa_una_proposta_e_non_si_applica(capsys):
    """L'inglese inverte l'ordine delle parole e lo strumento non lo sa: e' la
    stessa legge del gemello Python, «non indovina»."""
    dati = _legami({"nome": "corpoPannello", "specie": "var", "ambito": 0,
                    "dich": [0], "rif": [], "globale": False})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 0" in fuori
    assert "PROPOSTE (composti" in fuori and "corpoPannello" in fuori


def test_il_nome_nuovo_gia_legato_nello_stesso_ambito_e_una_collisione(capsys):
    """Il gemello che `rinomina.Collisione` dichiara di NON avere, e che il
    1 settembre e' costato un 500 su ogni asset: `richiesta -> request` dentro
    `_security_headers(request, handler)` riassegnava il parametro. Qui l'AST
    lo rende visibile, e la rinomina si rifiuta."""
    dati = _legami(
        {"nome": "pannello", "specie": "var", "ambito": 0, "dich": [0], "rif": [],
         "globale": False},
        {"nome": "panel", "specie": "var", "ambito": 0, "dich": [5], "rif": [],
         "globale": False},
    )
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 0" in fuori
    assert "COLLISIONI" in fuori and "gia' legato nello stesso ambito" in fuori


def test_una_proprieta_letta_solo_in_posizione_di_verita_si_dichiara(capsys):
    """La specie che nessun cancello vede: rinominata da un lato solo, la
    lettura orfana da' `undefined`, e `undefined` in posizione di verita'
    diventa `false` senza che niente lanci. Misurato su 41 mutazioni: 4 casi
    ciechi, tutti di questa forma, e nessuno fuori da essa."""
    dati = _legami(proprieta=[
        {"nome": "aperto", "lato": "chiave", "riga": 1, "verita": False},
        {"nome": "aperto", "lato": "lettura", "riga": 2, "verita": True},
    ])
    p = _scrivi(dati)
    assert "aperto" in rinomina_js.proprieta_cieche(json.loads(Path(p).read_text(encoding="utf-8")))
    rinomina_js.main(["--legami", p])
    assert "PROPRIETA' CIECHE: 1" in capsys.readouterr().out


def test_una_lettura_che_esce_dalla_verita_toglie_la_proprieta_dalla_lista():
    """La prova per mutazione del predicato: basta UNA lettura fuori dalla
    posizione di verita' e la forma non e' piu' silenziosa, perche' li'
    `undefined` diventa visibile."""
    dati = _legami(proprieta=[
        {"nome": "aperto", "lato": "chiave", "riga": 1, "verita": False},
        {"nome": "aperto", "lato": "lettura", "riga": 2, "verita": True},
        {"nome": "aperto", "lato": "lettura", "riga": 3, "verita": False},
    ])
    assert rinomina_js.proprieta_cieche(dati) == set()


def test_l_ambito_predefinito_e_static():
    """Otto parole sono qualificate `(static)` nel glossario. Con l'ambito
    vuoto `Glossario.per` risponderebbe `None` su tutte e otto, IN SILENZIO:
    il valore predefinito non e' una comodita', e' una guardia."""
    fonte = Path(ROOT / "scripts" / "rinomina_js.py").read_text(encoding="utf-8")
    assert '"--ambito", default="static"' in fonte, (
        "l'ambito predefinito non e' piu' `static`: otto parole qualificate "
        "diventerebbero mute, in silenzio")


@pytest.mark.skipif(shutil.which("node") is None or
                    not (ROOT / "node_modules" / "acorn").exists(),
                    reason="serve node con acorn: il job pytest del CI monta solo Python")
def test_acorn_legge_tutti_i_file_di_static_senza_un_solo_errore():
    fuori = subprocess.run([shutil.which("node"), str(ROOT / "scripts" / "legami_js.mjs")],
                           cwd=ROOT, capture_output=True, text=True, check=True)
    dati = json.loads(fuori.stdout)
    errori = {k: v["errore"] for k, v in dati.items() if "errore" in v}
    assert not errori, errori
    assert len(dati) == len(list((ROOT / "hiris" / "app" / "static").rglob("*.js")))
    # il numero che giustifica il parser: i LEGAMI sono piu' dei nomi
    legami = sum(len(v["legami"]) for v in dati.values())
    nomi = len({x["nome"] for v in dati.values() for x in v["legami"]})
    assert legami > nomi * 2, (legami, nomi)


def _scrivi(dati):
    import tempfile
    f = Path(tempfile.mkdtemp()) / "legami.json"
    f.write_text(json.dumps(dati), encoding="utf-8")
    return str(f)


def test_una_parola_riservata_di_javascript_non_si_applica_mai(capsys):
    """La guardia sulla FORMA NUDA, e il suo caso e' vero.

    Il glossario decide `classe -> class`, e la decisione e' giusta. Applicata
    a un identificatore nudo produce `var class = ...`, che in JavaScript non
    e' un nome ombreggiato: e' un errore di sintassi. Successo il 02/09 su
    `config/usage-route.js:61` -- tre cancelli rossi insieme, ma un'ora prima
    la stessa parola sarebbe passata in un file che nessun test carica. La
    stessa classe era gia' costata un guasto nel Python (`class = _text(...)`
    in `cervello/pavimento.py`, trovato solo da `py_compile`)."""
    dati = _legami({"nome": "classe", "specie": "var", "ambito": 0,
                    "dich": [0], "rif": [10], "globale": False})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 0" in fuori
    assert "parola riservata" in fuori


def test_un_nome_che_ombreggia_un_globale_del_browser_non_si_applica(capsys):
    """La meta' silenziosa della stessa guardia, e conta DOVE.

    Al livello di modulo, in uno script classico, `var name` non ombreggia il
    globale del browser: gli scrive sopra. Dentro una funzione lo stesso nome
    e' un ombreggiamento locale e innocuo -- il test gemello qui sotto lo
    verifica, ed e' la ragione per cui la prima stesura di questa guardia era
    sbagliata: rifiutava ogni `nome -> name`, la rinomina piu' comune della
    fetta."""
    dati = _legami({"nome": "nome", "specie": "var", "ambito": 0,
                    "dich": [0], "rif": [], "globale": True})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 0" in fuori
    assert "gli si SCRIVE sopra" in fuori


def test_lo_stesso_nome_dentro_una_funzione_e_solo_un_ombreggiamento(capsys):
    """La mutazione che separa le due meta': stesso nome, `globale` falso."""
    dati = _legami({"nome": "nome", "specie": "var", "ambito": 3,
                    "dich": [0], "rif": [], "globale": False})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 1" in fuori and "nome -> name" in fuori


def test_la_guardia_non_blocca_un_nome_innocuo(capsys):
    """La prova per mutazione al contrario: se la guardia bloccasse tutto
    sarebbe verde per la ragione sbagliata."""
    dati = _legami({"nome": "pannello", "specie": "var", "ambito": 0,
                    "dich": [0], "rif": [], "globale": False})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 1" in fuori and "pannello -> panel" in fuori


def test_una_parola_raggiunta_per_alias_si_propone_e_non_si_applica(capsys):
    """Un alias dice che due parole sono la STESSA parola, non che si scrivano
    allo stesso modo in inglese: la flessione si perde.

    Misurato il 02/09 su `config/api.js:105`, dove
    `var righe = widget.querySelectorAll('.usage-row')` sarebbe diventato
    `var line`: sbagliato nel numero (un NodeList non e' una riga) e sbagliato
    nel senso (quelle sono righe di una TABELLA, `riga (api) -> row`, non
    `riga (static) -> line`). Il gemello Python lo sapeva gia':
    `rinomina.classifica('righe')` restituisce una Proposta, non una stringa."""
    dati = _legami({"nome": "righe", "specie": "var", "ambito": 0,
                    "dich": [0], "rif": [], "globale": False})
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "APPLICABILI: 0" in fuori
    assert "raggiunta per alias" in fuori


def test_nessun_rifiuto_con_una_ragione_sparisce_in_silenzio(capsys):
    """La prima stesura elencava solo i rifiuti che cominciavano per
    «composto», e quelli per alias non comparivano affatto: un nome che nessuno
    vede e' un nome che nessuno decidera'. Qui si prova che il conto delle
    proposte cresce, non che il rifiuto avvenga."""
    dati = _legami(
        {"nome": "righe", "specie": "var", "ambito": 0, "dich": [0], "rif": [],
         "globale": False},
        {"nome": "corpoPannello", "specie": "var", "ambito": 0, "dich": [5],
         "rif": [], "globale": False},
    )
    rinomina_js.main(["--legami", _scrivi(dati)])
    fuori = capsys.readouterr().out
    assert "PROPOSTE (composti: lo strumento non indovina): 2" in fuori
