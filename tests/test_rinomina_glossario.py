"""Il lettore del glossario e lo spezzatore di identificatori."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rinomina


@pytest.fixture(scope="module")
def g():
    return rinomina.leggi_glossario()


def test_legge_le_parole_ordinarie(g):
    """`| adesso | now |` -- due colonne, la tabella piu' semplice."""
    assert g.mappa["adesso"] == "now"
    assert g.mappa["aggiungi"] == "add"


def test_legge_i_concetti_dalla_terza_colonna(g):
    """`| archivio | che cosa fa... | store | prova |` -- l'inglese e' la TERZA
    colonna, non l'ultima: leggere l'ultima prenderebbe l'esito della prova."""
    assert g.mappa["archivio"] == "store"
    assert g.mappa["osservatore"] == "watcher"


def test_gli_omonimi_non_finiscono_nella_mappa_semplice(g):
    """`ancora` e `piano` hanno DUE righe ciascuno, distinte dal sottosistema
    fra parentesi. Metterne una sola nella mappa piatta significherebbe
    rinominare meta' delle occorrenze col significato dell'altra."""
    assert "ancora" not in g.mappa
    assert "piano" not in g.mappa
    assert g.omonimi["ancora"]["memoria"] == "tether"
    assert g.omonimi["ancora"]["consumi"] == "anchor"


def test_per_risolve_l_omonimo_col_sottosistema(g):
    assert g.per("ancora", "memoria") == "tether"
    assert g.per("ancora", "consumi") == "anchor"
    assert g.per("adesso", "consumi") == "now"


def test_per_un_omonimo_senza_ambito_noto_non_indovina(g):
    """Meglio non rinominare che rinominare col significato sbagliato."""
    assert g.per("ancora", "cervello") is None


def test_le_parole_scartate_non_si_rinominano_mai(g):
    """Il glossario le ha ESCLUSE di proposito: applicarle sarebbe decidere
    al posto suo. Sono l'unica lista intoccabile che serve davvero -- le
    parole di confine si rinominano eccome (`stato` -> `state`)."""
    assert g.scartate, "la sezione «Parole scartate» non e' stata letta"
    for p in g.scartate:
        assert p not in g.mappa


def test_il_glossario_vero_ha_le_dimensioni_attese(g):
    """Se il lettore prendesse solo meta' delle tabelle passerebbe tutti i
    test sopra e fallirebbe qui. Le soglie sono minimi, non uguaglianze: il
    glossario e' vivo e puo' crescere."""
    assert len(g.mappa) > 150, f"solo {len(g.mappa)} parole lette"


def test_spezza_snake_case():
    assert rinomina.spezza("archivio_casa") == ["archivio", "casa"]


def test_spezza_camel_case():
    assert rinomina.spezza("ArchivioMemoria") == ["Archivio", "Memoria"]


def test_spezza_tiene_il_trattino_basso_iniziale_fuori_dai_pezzi():
    """`_registra_consumo` e' privato: il trattino iniziale e' una convenzione
    Python, non una parola da tradurre."""
    assert rinomina.spezza("_registra_consumo") == ["registra", "consumo"]


def test_una_parola_sola_si_classifica_e_si_applica(g):
    assert rinomina.classifica("archivio", g, "memoria") == "store"


def test_una_parola_sola_maiuscola_diventa_PASCALCASE(g):
    """`Archivio` -> `Store`: la classe resta una classe."""
    assert rinomina.classifica("Archivio", g, "memoria") == "Store"


def test_una_costante_TUTTA_MAIUSCOLA_resta_TUTTA_MAIUSCOLA(g):
    """`ETICHETTA` e' una costante di modulo (convenzione TUTTA MAIUSCOLA),
    non una classe: il solo controllo sulla prima lettera maiuscola la
    confonderebbe con `Archivio` e produrrebbe `Label`, non `LABEL` --
    rompendo la convenzione delle costanti in silenzio. Trovato puntando lo
    strumento su `consumi/vocabolario.py` (Task 4, poi rinominato
    `consumi/vocabulary.py` nello stesso task)."""
    assert rinomina.classifica("ETICHETTA", g, "consumi") == "LABEL"


def test_un_prefisso_privato_si_conserva(g):
    """`_fuso` e' un aiutante privato per convenzione Python (il trattino
    basso iniziale): sparire lo trasforma in interfaccia PUBBLICA senza che
    nessuno lo decida. Stessa famiglia del difetto sopra (la forma
    dell'originale va conservata, non solo le maiuscole) -- trovato in
    produzione: `hiris/app/consumi/store.py`, `_fuso` era diventato
    `timezone` invece di `_timezone`."""
    assert rinomina.classifica("_archivio", g, "memoria") == "_store"
    assert rinomina.classifica("_fuso", g, "consumi") == "_timezone"


def test_un_trattino_basso_finale_si_conserva(g):
    """Convenzione Python per evitare di ombreggiare una parola riservata
    (`tipo_` invece di `tipo`, che coprirebbe il builtin `type`): il
    trattino basso finale non e' una parola da tradurre, va conservato come
    quello iniziale. Trovato cercando di proposito una quarta variante di
    forma non coperta, dopo maiuscole, costanti TUTTE MAIUSCOLE e prefisso
    privato: `gamba_` (`hiris/app/cervello/oggetti.py`, evita di ombreggiare
    `gamba`) sarebbe diventato `aspect`, non `aspect_`."""
    assert rinomina.classifica("tipo_", g, "casa") == "type_"
    assert rinomina.classifica("gamba_", g, "cervello") == "aspect_"
    assert rinomina.classifica("_archivio_", g, "memoria") == "_store_"


def test_un_composto_si_classifica_come_PROPOSTA_non_come_nome(g):
    """IL CUORE DELLO STRUMENTO. `unita_vive` non e' `unit_reported`: e'
    `reported_units`. L'italiano mette l'aggettivo dopo, l'inglese prima, e
    nessuna sostituzione pezzo per pezzo puo' saperlo. Quindi si propone."""
    esito = rinomina.classifica("unita_vive", g, "casa")
    assert isinstance(esito, rinomina.Proposta)
    assert esito.nome == "unita_vive"
    assert esito.pezzi == ["unita", "vive"]


def test_un_nome_senza_nessuna_parola_del_glossario_resta_fermo(g):
    assert rinomina.classifica("json", g, "casa") is None
    assert rinomina.classifica("self", g, "casa") is None


def test_una_parola_scartata_resta_ferma(g):
    for p in list(g.scartate)[:1]:
        assert rinomina.classifica(p, g, "casa") is None


def test_i_veri_scarti_restano_scartate(g):
    """`backend`, `sanitize`, `yaml`: parole gia' inglesi o sigle, che il
    glossario ha escluso di proposito da ogni decisione di rinomina."""
    for parola in ("backend", "sanitize", "yaml"):
        assert parola in g.scartate


def test_le_forme_plurali_alias_NON_sono_scartate(g):
    """`costruzioni`, `esiti`, `gambe` sono la seconda tabella della sezione
    -- forme plurali gia' ricondotte a un lemma singolare (`costruzione`,
    `esito`, `gamba`), non parole che il glossario ha rifiutato di decidere.
    Trattarle da scarti le lascerebbe per sempre in italiano."""
    for parola in ("costruzioni", "esiti", "gambe"):
        assert parola not in g.scartate


def test_una_forma_alias_si_propone_con_l_inglese_del_lemma(g):
    """`costruzioni` e' il plurale di `costruzione` (-> `construction`), ma
    l'inflessione inglese non e' sempre «+s»: lo strumento non indovina
    `constructions`, propone `construction` e si ferma -- lo stesso
    principio dei composti, applicato a un alias invece che a un pezzo."""
    esito = rinomina.classifica("costruzioni", g, "casa")
    assert isinstance(esito, rinomina.Proposta)
    assert esito.nome == "costruzioni"
    assert esito.suggerito == "construction"


def test_se_l_intestazione_della_tabella_alias_cambia_il_lettore_se_ne_accorge(tmp_path):
    """Legare la lettura all'intestazione, non alla posizione: se il titolo
    della tabella degli alias cambiasse silenziosamente, l'alternativa
    sarebbe leggerne le righe come scarti -- il contrario del vero (le
    parole raggiunte per alias andrebbero perse in italiano per sempre,
    scambiate per scarti intoccabili). Meglio fermarsi rumorosamente."""
    testo = rinomina.leggi(rinomina.GLOSSARIO)
    intestazione = "| forma uscita dallo script | lemma nel glossario |"
    assert intestazione in testo, "l'intestazione attesa non e' nel glossario vero"
    modificato = testo.replace(intestazione, "| forma uscita dallo script | ALTRO |")
    percorso = tmp_path / "glossario_modificato.md"
    percorso.write_text(modificato, encoding="utf-8")
    with pytest.raises(ValueError):
        rinomina.leggi_glossario(percorso)
