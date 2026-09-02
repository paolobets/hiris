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
    assert g.omonimi["ancora"]["memory"] == "tether"
    assert g.omonimi["ancora"]["usage"] == "anchor"


def test_per_risolve_l_omonimo_col_sottosistema(g):
    assert g.per("ancora", "memory") == "tether"
    assert g.per("ancora", "usage") == "anchor"
    assert g.per("adesso", "usage") == "now"


def test_per_un_omonimo_senza_ambito_noto_non_indovina(g):
    """Meglio non rinominare che rinominare col significato sbagliato."""
    assert g.per("ancora", "mind") is None


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
    assert rinomina.classifica("archivio", g, "memory") == "store"


def test_una_parola_sola_maiuscola_diventa_PASCALCASE(g):
    """`Archivio` -> `Store`: la classe resta una classe."""
    assert rinomina.classifica("Archivio", g, "memory") == "Store"


def test_una_costante_TUTTA_MAIUSCOLA_resta_TUTTA_MAIUSCOLA(g):
    """`ETICHETTA` e' una costante di modulo (convenzione TUTTA MAIUSCOLA),
    non una classe: il solo controllo sulla prima lettera maiuscola la
    confonderebbe con `Archivio` e produrrebbe `Label`, non `LABEL` --
    rompendo la convenzione delle costanti in silenzio. Trovato puntando lo
    strumento su `consumi/vocabolario.py` (Task 4, poi rinominato
    `usage/vocabulary.py` nello stesso task)."""
    assert rinomina.classifica("ETICHETTA", g, "usage") == "LABEL"


def test_un_prefisso_privato_si_conserva(g):
    """`_fuso` e' un aiutante privato per convenzione Python (il trattino
    basso iniziale): sparire lo trasforma in interfaccia PUBBLICA senza che
    nessuno lo decida. Stessa famiglia del difetto sopra (la forma
    dell'originale va conservata, non solo le maiuscole) -- trovato in
    produzione: `hiris/app/usage/store.py`, `_fuso` era diventato
    `timezone` invece di `_timezone`."""
    assert rinomina.classifica("_archivio", g, "memory") == "_store"
    assert rinomina.classifica("_fuso", g, "usage") == "_timezone"


def test_un_trattino_basso_finale_si_conserva(g):
    """Convenzione Python per evitare di ombreggiare una parola riservata
    (`tipo_` invece di `tipo`, che coprirebbe il builtin `type`): il
    trattino basso finale non e' una parola da tradurre, va conservato come
    quello iniziale. Trovato cercando di proposito una quarta variante di
    forma non coperta, dopo maiuscole, costanti TUTTE MAIUSCOLE e prefisso
    privato: `gamba_` (`hiris/app/mind/facts.py`, evita di ombreggiare
    `gamba`) sarebbe diventato `aspect`, non `aspect_`."""
    assert rinomina.classifica("tipo_", g, "casa") == "type_"
    assert rinomina.classifica("gamba_", g, "mind") == "aspect_"
    assert rinomina.classifica("_archivio_", g, "memory") == "_store_"


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


# -- La guardia sulle keyword e sui builtin (rilievo del revisore, Task 6) --
#
# Lo strumento applicava l'inglese deciso anche quando coincideva con una
# keyword Python (`class`) o un builtin (`type`, `list`, `round`...). Il
# primo caso e' rumoroso (SyntaxError, trovato subito da py_compile); il
# secondo e' silenzioso -- nessun cancello attivo lo vede, perche'
# `flake8-builtins` non e' nel set di ruff -- e produce un TypeError solo
# quando qualcosa chiama davvero il builtin ombreggiato.

def test_una_keyword_python_non_si_applica_da_sola():
    """`classe -> class`: applicato a un identificatore nudo produrrebbe
    `class = ...`, un SyntaxError. Misurato dal vivo su
    `mind/baseline.py` (Task 6)."""
    gf = rinomina.Glossario(mappa={"classe": "class"})
    esito = rinomina.classifica("classe", gf, "qualunque")
    assert isinstance(esito, rinomina.Proposta), (
        "una keyword Python non deve mai applicarsi da sola su un nome nudo")
    assert esito.suggerito == "class"


def test_un_builtin_ombreggiato_non_si_applica_da_solo():
    """`tipo -> type`: non e' un SyntaxError, e' peggio -- parsa, e
    ombreggia silenziosamente il builtin. Un `tipo` che nello stesso scope
    chiama anche `type(x)` diventerebbe un TypeError solo a runtime, mai un
    rosso in CI (nessuna regola flake8-builtins attiva su questo
    progetto)."""
    gf = rinomina.Glossario(mappa={"tipo": "type"})
    esito = rinomina.classifica("tipo", gf, "qualunque")
    assert isinstance(esito, rinomina.Proposta), (
        "un builtin ombreggiato non deve mai applicarsi da solo su un nome nudo")
    assert esito.suggerito == "type"


def test_un_prefisso_protegge_dalla_guardia_keyword_builtin():
    """`_tipo` non ombreggia niente -- e' gia' un nome diverso da `type` --
    quindi la guardia non deve bloccarlo: stessa disciplina del prefisso
    privato gia' provata sopra (`_archivio -> _store`)."""
    gf = rinomina.Glossario(mappa={"tipo": "type"})
    assert rinomina.classifica("_tipo", gf, "qualunque") == "_type"


def test_un_suffisso_protegge_dalla_guardia_keyword_builtin():
    """`tipo_` (convenzione Python per evitare di ombreggiare `type`) non
    ombreggia niente neanche lui: si applica."""
    gf = rinomina.Glossario(mappa={"tipo": "type"})
    assert rinomina.classifica("tipo_", gf, "qualunque") == "type_"


def test_una_costante_che_diventa_un_builtin_non_e_pericolosa():
    """`TIPO -> TYPE`: una costante tutta maiuscola non ombreggia il builtin
    minuscolo `type`. La guardia si applica alla forma FINALE, non alla
    parola del glossario da sola."""
    gf = rinomina.Glossario(mappa={"tipo": "type"})
    assert rinomina.classifica("TIPO", gf, "qualunque") == "TYPE"


@pytest.mark.parametrize("parola", ["classe", "tipo", "elenca", "elenco", "giro"])
def test_le_parole_pericolose_vere_del_glossario_si_propongono(g, parola):
    """Misurato dal revisore sul glossario vero: `classe`(28 occorrenze),
    `tipo`(89), `elenca`/`elenco`(54), `giro`(22) -- applicate alla cieca su
    identificatori nudi, la prima produce un SyntaxError rumoroso, le altre
    tre ombreggiano `type`/`list`/`round` in silenzio. Tutte e cinque devono
    uscire come proposte, mai come applicazioni dirette."""
    assert isinstance(rinomina.classifica(parola, g, "casa"), rinomina.Proposta)


def test_la_guardia_keyword_builtin_si_vede_anche_nel_file_riscritto(g):
    """Prova per mutazione della guardia end-to-end (non solo su
    `classifica()` isolata): un file con `tipo = 1` non deve diventare
    `type = 1`."""
    dentro = "tipo = 1\n"
    fuori, proposte = rinomina.riscrivi(dentro, g, "casa")
    assert fuori == dentro, "un builtin ombreggiato non si applica da solo"
    assert [p.nome for p in proposte] == ["tipo"]


# -- I plurali invisibili (rilievo del revisore, Task 6) --------------------
#
# Un plurale che non e' ne' la chiave esatta del glossario (`genere`,
# singolare) ne' un alias dichiarato (come `gambe -> gamba`) sparisce da
# `classifica()` SENZA nessuna proposta: `classifica()` ritorna `None`
# quando nessun pezzo traduce, e un `None` non compare mai nell'elenco dei
# composti del dry-run. Misurato dal vivo: `GENERI`/`DIREZIONI_BILANCIO`
# (Task 6) erano invisibili cosi'.

def test_un_plurale_non_aliasato_diventa_una_proposta():
    """`GENERI` (plurale di `genere`, nessun alias) deve comparire come
    proposta -- non sparire in silenzio come faceva prima di questa
    guardia."""
    gf = rinomina.Glossario(mappa={"genere": "genre"})
    esito = rinomina.classifica("GENERI", gf, "qualunque")
    assert isinstance(esito, rinomina.Proposta), (
        "un plurale non aliasato non deve sparire senza proposta")
    assert esito.suggerito == "genre"


def test_un_plurale_via_euristica_non_si_applica_mai_da_solo():
    """Anche quando il nome e' un pezzo solo, una singolarizzazione trovata
    per euristica non e' una lettura diretta del glossario: si propone,
    come un alias -- non si applica MAI da sola, a differenza di una parola
    che il glossario ha davvero in tabella."""
    gf = rinomina.Glossario(mappa={"tipo": "type"})
    esito = rinomina.classifica("tipi", gf, "qualunque")
    assert isinstance(esito, rinomina.Proposta)
    assert esito.suggerito == "type"


def test_una_parola_singolare_vera_non_passa_dall_euristica_del_plurale():
    """Controllo di non regressione: una parola che il glossario decide GIA'
    al singolare continua ad applicarsi direttamente -- l'euristica del
    plurale scatta solo quando la lettura diretta fallisce."""
    gf = rinomina.Glossario(mappa={"genere": "genre"})
    assert rinomina.classifica("genere", gf, "qualunque") == "genre"


def test_un_composto_con_un_pezzo_plurale_lo_recupera_via_euristica():
    """`_TIPI_ANCORA`-simile: un composto in cui un pezzo e' un plurale non
    aliasato deve comunque proporre l'inglese di quel pezzo, non lasciarlo
    intraducibile."""
    gf = rinomina.Glossario(mappa={"tipo": "type"})
    esito = rinomina.classifica("tipi_ancora", gf, "qualunque")
    assert isinstance(esito, rinomina.Proposta)
    assert esito.pezzi == ["tipi", "ancora"]
    assert esito.suggerito == "type_ancora"


@pytest.mark.parametrize("costante", ["GENERI", "GAMBE"])
def test_le_costanti_vere_invisibili_ora_compaiono(g, costante):
    """Regressione diretta sul glossario vero: `GENERI` e `GAMBE` erano
    completamente invisibili al dry-run prima di questa guardia (nessuna
    proposta, nessun cambio -- `classifica()` tornava `None`). Ora devono
    comparire come proposte."""
    esito = rinomina.classifica(costante, g, "mind")
    assert isinstance(esito, rinomina.Proposta), (
        f"{costante} deve comparire come proposta, non sparire in silenzio")


def test_direzioni_bilancio_ora_compare_come_proposta(g):
    """`DIREZIONI_BILANCIO`: due pezzi, entrambi plurali/non decisi da soli
    (`direzioni` non e' `direzione`, `bilancio` e' un valore di dominio
    rinviato) -- prima di questa guardia era invisibile per intero."""
    esito = rinomina.classifica("DIREZIONI_BILANCIO", g, "action")
    assert isinstance(esito, rinomina.Proposta)
    assert "direzioni" in esito.pezzi


# -- Il conflitto silenzioso fra tabelle (rilievo del revisore, Task 6) -----
#
# `guarda` era `look` fra le parole ordinarie e `view` fra i nomi degli
# strumenti -- due righe NUDE, nessun ambito a dichiarare l'omonimia,
# nessun segnale: l'ultima tabella letta vinceva in silenzio.

def test_due_righe_nude_con_inglesi_diversi_fermano_la_lettura(tmp_path):
    """Riproduce il difetto vero su un glossario sintetico minimo: due
    tabelle, la stessa parola nuda, due inglesi diversi. Deve fermarsi
    rumorosamente, non scegliere l'ultima in silenzio."""
    testo = """## I concetti

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|
| prova | placeholder | look | ✓ arriva |

## Le parole ordinarie

| italiano | inglese |
|---|---|
| prova | view |

## I nomi degli strumenti

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|

## Parole scartate durante l'estrazione

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| backend | e' gia' inglese |

| forma uscita dallo script | lemma nel glossario |
|---|---|
| costruzioni | costruzione |
"""
    percorso = tmp_path / "conflitto.md"
    percorso.write_text(testo, encoding="utf-8")
    with pytest.raises(ValueError, match="prova"):
        rinomina.leggi_glossario(percorso)


def test_la_stessa_riga_ripetuta_con_lo_stesso_inglese_non_e_un_conflitto(tmp_path):
    """Due righe nude per la stessa parola che concordano non sono un
    conflitto: e' ridondante, non contraddittorio. Non deve sollevare."""
    testo = """## I concetti

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|
| prova | placeholder | view | ✓ arriva |

## Le parole ordinarie

| italiano | inglese |
|---|---|
| prova | view |

## I nomi degli strumenti

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|

## Parole scartate durante l'estrazione

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| backend | e' gia' inglese |

| forma uscita dallo script | lemma nel glossario |
|---|---|
| costruzioni | costruzione |
"""
    percorso = tmp_path / "concorde.md"
    percorso.write_text(testo, encoding="utf-8")
    g = rinomina.leggi_glossario(percorso)
    assert g.mappa["prova"] == "view"


def test_un_omonimo_dichiarato_due_volte_in_disaccordo_ferma_la_lettura(tmp_path):
    """Lo stesso principio, per una riga CON ambito: due dichiarazioni della
    stessa coppia (parola, ambito) con inglesi diversi sono una
    contraddizione, non una correzione dell'ultima riga sulla prima."""
    testo = """## I concetti

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|
| prova (memory) | placeholder uno | alpha | ✓ arriva |
| prova (memory) | placeholder due | beta | ✓ arriva |

## Le parole ordinarie

| italiano | inglese |
|---|---|

## I nomi degli strumenti

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|

## Parole scartate durante l'estrazione

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| backend | e' gia' inglese |

| forma uscita dallo script | lemma nel glossario |
|---|---|
| costruzioni | costruzione |
"""
    percorso = tmp_path / "conflitto_omonimo.md"
    percorso.write_text(testo, encoding="utf-8")
    with pytest.raises(ValueError, match="prova"):
        rinomina.leggi_glossario(percorso)


def test_il_glossario_vero_non_ha_conflitti_silenziosi(g):
    """Il glossario vero deve gia' passare questa guardia -- l'ha gia'
    passata per caricare `g` (fixture di modulo): se non sollevasse qui e
    l'avesse sollevato altrove, vorrebbe dire che la correzione di `guarda`
    non e' completa."""
    assert g.omonimi["guarda"] == {"mind": "watch", "casa": "view"}
    assert "guarda" not in g.mappa


# **Vuoto dal 01/09, e il vuoto e' il risultato.** L'unica coppia che
# ritornava era `codice -> code` (`code` e' il plurale di `coda -> tail`), e
# la cura NON e' stata rinominare: e' stata decidere `code` nel glossario,
# come parola SCARTATA perche' e' inglese. Rinominare `_code_of` in
# `_status_code` aveva PEGGIORATO il conto -- `classifica('_status_code')`
# proponeva `status_tail`, e i composti falsi erano passati da uno a due.
#
# La lezione, che vale piu' della riga: **quando l'inglese prodotto e'
# leggibile come italiano, la cura appartiene al glossario, non a un'altra
# rinomina** -- altrimenti si insegue un nome con un altro nome.
_RITORNANTI_NOTE: set[tuple[str, str, str]] = set()


def test_nessuna_parola_produce_un_inglese_che_il_glossario_rilegge_da_capo():
    """Il TERZO posto in cui lo strumento sapeva due cose e non le univa.

    Sapeva quale inglese produce e sapeva come si legge una parola italiana, e
    non si e' mai chiesto se il nome che PRODUCE sia a sua volta leggibile come
    ingresso. Misurato dal vivo (fetta «la rinomina», lotto di `backends/`):
    `_codice_di` e' diventato `_code_of`, e il dry-run successivo proponeva
    `_code_of -> tail_of`, perche' **`code` e' italiano** -- plurale di `coda`.

    E' la seconda trappola della famiglia di `rotta` (una parola che il
    glossario legge nel senso sbagliato) e la piu' insidiosa finora, perche'
    il nome prodotto sembra corretto in inglese: nessuna review si ferma su
    `_code_of`.

    Non rompe niente il giorno che nasce -- resta una proposta per sempre e
    confonde chi legge -- quindi il rimedio non e' vietarla ma DICHIARARLA:
    l'istantanea ha una voce sola, e una seconda va guardata prima di
    accettarla.

    Provato per mutazione: aggiunta una riga `mano -> hand` (e `hand` non e'
    italiano) resta verde; aggiunta `pesce -> pesci` (dove `pesci` si
    rileggerebbe) arrossisce.
    """
    g = rinomina.leggi_glossario()
    trovate = set()
    for italiano, inglese in g.mappa.items():
        if inglese == italiano:
            continue
        esito = rinomina.classifica(inglese, g, "qualunque")
        if esito is None:
            continue
        riletto = esito if isinstance(esito, str) else esito.suggerito
        if riletto != inglese:
            trovate.add((italiano, inglese, riletto))
    nuove = sorted(trovate - _RITORNANTI_NOTE)
    sparite = sorted(_RITORNANTI_NOTE - trovate)
    assert not nuove, (
        "parole il cui inglese il glossario rilegge come italiano: "
        + ", ".join(f"{i} -> {e} (che rileggerebbe come {r})" for i, e, r in nuove)
        + " -- il nome prodotto SEMBRA inglese corretto e nessuna review si "
          "ferma su di lui, ma il dry-run successivo continuera' a proporlo. "
          "Scegli un altro inglese, oppure dichiaralo qui con la ragione")
    assert not sparite, (
        "coppie dichiarate che non ritornano piu': "
        + ", ".join(f"{i} -> {e}" for i, e, _ in sparite)
        + " -- bene: togli la riga da `_RITORNANTI_NOTE`")
