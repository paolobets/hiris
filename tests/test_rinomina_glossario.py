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
