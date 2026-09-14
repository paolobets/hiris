"""Il sapere: cio' che HIRIS ha capito, con la provenienza e le prove.

Spec `docs/design/2026-09-10-i-tre-attori.md` §8. **I due assi restano due**:
`provenance` dice DA DOVE VIENE, `verification` dice COSA HA DETTO IL
CONTROLLO. Fonderle in una parola sola e' il difetto che questo progetto ha
gia' pagato sei volte, e il modo di non rifarlo non e' ricordarselo: e' un
costruttore che non lascia nascere una riga sbagliata -- la disciplina di
`home_space/type_vocabulary.Field`, che non si costruisce senza provenienza.
"""
import json

import pytest

from hiris.app.mind import knowledge as sap


def _riga(**cambi):
    """Una riga valida, da cui ogni prova cambia il pezzo che la riguarda."""
    base = {"subject_kind": "integrazione", "subject": "zcsazzurro",
            "field": "direzione:energy_generating_today", "value": "produzione",
            "provenance": "dedotto", "evidence": "translation_key dell'entita'",
            "who": "claude-opus-5", "when_ts": 1789000000.0}
    base.update(cambi)
    return sap.Fact(**base)


# -- Il costruttore e' il cancello ------------------------------------------

def test_una_riga_del_sapere_porta_i_due_assi_separati():
    """Provenienza e verifica sono due campi, e si leggono separatamente."""
    f = _riga(verification="confermata", source="manifest zcsazzurro 1.4.2")

    assert f.provenance == "dedotto"
    assert f.verification == "confermata"


def test_un_genere_di_soggetto_inventato_NON_nasce():
    """Quattro generi: `tipo`, `integrazione`, `entita`, `dispositivo`. Non e'
    un elenco aperto -- cio' che la spec §8 esclude e' una colonna `ambito`,
    perche' il genere dice gia' da solo se una riga e' universale (`tipo` e
    `integrazione`) o di questa casa (`entita` e `dispositivo`).

    Il quarto e' nato il 13/09/2026 con le ricette che l'osservatore chiede al
    modello: una ricetta non ha nessun altro soggetto onesto -- non e'
    dell'integrazione (nomina entita' che un'altra casa non ha) e non e' di
    un'entita' sola (ne mette insieme sette).

    Mutazione che la uccide: togliere il controllo su `SUBJECT_KINDS`.
    """
    with pytest.raises(ValueError, match="genere"):
        _riga(subject_kind="stanza")


def test_una_provenienza_inventata_NON_nasce():
    with pytest.raises(ValueError, match="provenienza"):
        _riga(provenance="indovinato")


def test_una_verifica_inventata_NON_nasce():
    with pytest.raises(ValueError, match="verifica"):
        _riga(verification="quasi", source="x")


def test_un_campo_NOSTRO_non_puo_essere_verificato():
    """**La regola piu' netta della spec §8**: *«un campo `nostro` non e' ne'
    confermato ne' dedotto: e' un giudizio che HA non puo' darci, e `verifica`
    per lui e' NULL»*.

    Non e' pedanteria: «confermata» su un giudizio nostro vorrebbe dire che
    qualcuno la' fuori ce l'ha confermato, e non e' successo. E' la forma
    esatta della motivazione falsa.

    Mutazione che la uccide: togliere il controllo su `nostro`.
    """
    with pytest.raises(ValueError, match="nostro"):
        _riga(provenance="nostro", verification="confermata",
              source="una fonte qualunque")


def test_un_campo_NOSTRO_con_verifica_vuota_nasce_benissimo():
    f = _riga(provenance="nostro", verification=None, evidence=None)

    assert f.verification is None


def test_una_verifica_CONFERMATA_senza_la_sua_citazione_NON_nasce():
    """La spec vuole `fonte` come *«la citazione, con la versione, quando la
    verifica ha confermato»*. Una conferma senza la citazione e' una parola
    che nessuno puo' controllare: e' la forma della motivazione falsa, e
    questo progetto ne ha gia' pagate diverse.

    Mutazione che la uccide: accettare `source=None` con `confermata`.
    """
    with pytest.raises(ValueError, match="fonte"):
        _riga(verification="confermata", source=None)


def test_una_deduzione_senza_prove_NON_nasce():
    """`prove` e' *«cosa e' stato letto per dedurlo»*. Una deduzione che non
    dice su cosa si basa non si puo' ne' rifare ne' smentire.

    Mutazione che la uccide: accettare `evidence=None` con `dedotto`.
    """
    with pytest.raises(ValueError, match="prove"):
        _riga(provenance="dedotto", evidence=None)


def test_NON_CAPITO_si_scrive_ed_e_una_riga_come_le_altre():
    """*«Tre esiti distinti -- confermata, non confermabile, **non capito**,
    che si scrive»*. Il silenzio e' il difetto: una casa che non sa una cosa
    deve poterlo dire, o la prossima sessione la ridedurra' da capo.
    """
    f = _riga(verification="non_capito")

    assert f.verification == "non_capito"
    assert f.value == "produzione"


def test_un_campo_senza_nome_NON_nasce():
    with pytest.raises(ValueError, match="campo"):
        _riga(field="   ")


def test_chi_e_quando_sono_obbligatori():
    """Chi l'ha scritto e quando: senza, una riga non si puo' ne' datare ne'
    attribuire, e fra sei mesi nessuno sa se valga ancora."""
    with pytest.raises(ValueError, match="chi"):
        _riga(who="")


# -- L'archivio -------------------------------------------------------------

@pytest.fixture
def sapere(tmp_path):
    s = sap.KnowledgeStore(str(tmp_path / "sapere.db"))
    yield s
    s.close()


def test_si_scrive_e_si_rilegge_uguale(sapere):
    sapere.write(_riga())

    [letta] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")

    assert letta.field == "direzione:energy_generating_today"
    assert letta.value == "produzione"
    assert letta.provenance == "dedotto"
    assert letta.evidence == "translation_key dell'entita'"


def test_la_chiave_e_la_TERNA_e_riscrivere_SOSTITUISCE(sapere):
    """`PRIMARY KEY (soggetto_genere, soggetto, campo)`: la stessa cosa detta
    due volte e' una riga sola, non due che possono divergere. E' la seconda
    fondamenta -- nessun doppione -- applicata all'archivio.

    Mutazione che la uccide: `INSERT` nudo al posto dell'`INSERT ... ON
    CONFLICT DO UPDATE`.
    """
    sapere.write(_riga(value="produzione"))
    sapere.write(_riga(value="immissione", who="proprietario",
                       provenance="chiesto", evidence=None))

    righe = sapere.read(subject_kind="integrazione", subject="zcsazzurro")

    assert len(righe) == 1
    assert righe[0].value == "immissione"
    assert righe[0].provenance == "chiesto"


def test_soggetti_diversi_con_lo_STESSO_campo_sono_righe_diverse(sapere):
    """Due inverter dello stesso genere non si sovrascrivono."""
    sapere.write(_riga(subject="zcsazzurro"))
    sapere.write(_riga(subject="solaredge"))

    assert len(sapere.read(subject_kind="integrazione", subject="zcsazzurro")) == 1
    assert len(sapere.read(subject_kind="integrazione", subject="solaredge")) == 1


def test_leggere_un_soggetto_che_non_c_e_torna_VUOTO_non_un_errore(sapere):
    assert sapere.read(subject_kind="entita", subject="sensor.mai_vista") == []


def test_un_campo_solo_si_chiede_per_nome(sapere):
    sapere.write(_riga(field="ricetta", value="{}"))
    sapere.write(_riga(field="ruolo", value="inverter"))

    assert sapere.get("integrazione", "zcsazzurro", "ruolo").value == "inverter"
    assert sapere.get("integrazione", "zcsazzurro", "mai_scritto") is None


def test_il_seme_del_repo_si_carica_e_NON_schiaccia_la_casa(sapere):
    """*«Il repo diventa il seme»* (spec §8): le righe scritte, riviste e
    linterate si caricano all'avvio con la loro provenienza, **e la casa
    scrive sopra**.

    Se il seme sovrascrivesse, ogni riavvio cancellerebbe cio' che la casa ha
    imparato -- e il difetto sarebbe invisibile, perche' il valore tornerebbe
    semplicemente a essere quello giusto-di-default.

    Mutazione che la uccide: usare `write` al posto di `seed` nel caricamento.
    """
    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None)])
    sapere.write(_riga(value="immissione", provenance="chiesto",
                       who="proprietario", evidence=None))
    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None)])

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")

    assert riga.value == "immissione", "il seme ha schiacciato cio' che la casa sapeva"
    assert riga.provenance == "chiesto"


def test_il_seme_scrive_cio_che_ANCORA_non_c_e(sapere):
    """L'altra meta': un seme che non scrivesse mai non servirebbe a niente."""
    sapere.seed([_riga(provenance="nostro", verification=None, evidence=None)])

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")

    assert riga.value == "produzione"
    assert riga.provenance == "nostro"


def test_il_seme_CORREGGE_le_righe_che_sono_ancora_SUE(sapere):
    """**Il difetto che la revisione indipendente ha trovato il 13/09/2026.**

    Con un `INSERT OR IGNORE` nudo, una riga sbagliata del repo sarebbe
    congelata per sempre su ogni casa che ha gia' avviato una volta: il
    giorno in cui si scoprisse che `power_autoconsuming` non significa
    «autoconsumo», correggerlo nel repo non riparerebbe nessuna installazione
    -- prima serviva un rilascio, dopo non basterebbe nemmeno quello.

    Il seme corregge cio' che e' ancora suo: si guarda `who`.

    Mutazione ESEGUITA: togliere la clausola `ON CONFLICT ... DO UPDATE` --
    rossa, la correzione non arriva.

    **Una mutazione piu' ovvia esce VERDE, e vale la pena saperlo**: aggiungere
    `OR IGNORE` lasciando l'upsert non cambia niente. In SQLite la clausola
    `ON CONFLICT` ha la precedenza sulla risoluzione `OR IGNORE` per il
    conflitto che nomina, quindi quella mutazione e' un no-op -- non una prova
    debole, una mutazione che non muta.
    """
    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None, who="seme del repo")])

    corrette = sapere.seed([_riga(value="immissione", provenance="nostro",
                                  verification=None, evidence=None,
                                  who="seme del repo")])

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")
    assert riga.value == "immissione"
    assert corrette == 1


def test_il_seme_NON_tocca_una_riga_su_cui_qualcun_altro_ha_scritto(sapere):
    """L'altra meta', ed e' quella che conta di piu': appena qualcuno scrive
    sopra, il seme si ferma. Senza questa regola la correzione cancellerebbe a
    ogni riavvio cio' che la casa ha imparato.

    Mutazione ESEGUITA: togliere `knowledge.value IS knowledge.seeded_value`
    dal `WHERE` -- rossa, il seme schiaccia la decisione del proprietario.
    """
    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None, who="seme del repo")])
    sapere.write(_riga(value="immissione", provenance="chiesto",
                       who="proprietario", evidence=None))

    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None, who="seme del repo")])

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")
    assert riga.value == "immissione"
    assert riga.who == "proprietario"


def test_una_riga_STORTA_sul_disco_non_fa_cadere_la_lettura(sapere, caplog):
    """**Questo archivio e' fatto per essere corretto a mano**, e una riga
    incoerente scritta li' dentro non deve spegnere una porta intera.

    `Fact` rivaluta i suoi controlli su cio' che arriva dal disco -- ed e'
    giusto, una riga incoerente non deve circolare come un fatto. Ma senza
    quarantena la lettura dell'intero soggetto solleverebbe, e il chiamante
    tradurrebbe l'eccezione in un messaggio che parla d'altro.

    Mutazione ESEGUITA: rimettere `[Fact(**dict(r)) for r in rows]` --
    rossa, `ValueError` invece della riga buona.
    """
    import logging

    sapere.write(_riga(field="buona"))
    # Una riga che il costruttore non lascerebbe nascere, scritta a mano
    # nell'archivio come farebbe qualcuno che lo corregge da fuori.
    sapere._conn.execute(
        "INSERT INTO knowledge (subject_kind, subject, field, value, provenance,"
        " verification, who, when_ts) VALUES (?,?,?,?,?,?,?,?)",
        ("integrazione", "zcsazzurro", "storta", "x", "nostro", "confermata",
         "una mano umana", 1789000000.0))
    sapere._conn.commit()

    with caplog.at_level(logging.WARNING):
        righe = sapere.read(subject_kind="integrazione", subject="zcsazzurro")

    assert [r.field for r in righe] == ["buona"]
    assert any("storta" in r.getMessage() for r in caplog.records)


def test_una_correzione_A_MANO_non_torna_indietro_al_riavvio(sapere):
    """**Il difetto che Fable 5.1 ha trovato il 13/09/2026.**

    L'archivio dichiara di essere fatto per essere corretto a mano. Chi lo
    corregge con un `UPDATE` **non cambia `who`** -- nessuno glielo ha detto --
    e con la regola letta dall'autore quella correzione tornava indietro al
    riavvio successivo, in silenzio, contata nel log come «una riga del seme
    scritta».

    «Nessuno l'ha toccata» si legge dal VALORE, non dall'autore.

    Mutazione ESEGUITA: rimettere `WHERE knowledge.who = excluded.who` al
    posto del confronto col valore seminato -- rossa, la correzione sparisce.
    """
    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None, who="seme del repo")])
    sapere._conn.execute(
        "UPDATE knowledge SET value = 'consumo_lordo' WHERE field = ?",
        ("direzione:energy_generating_today",))
    sapere._conn.commit()

    sapere.seed([_riga(value="produzione", provenance="nostro",
                       verification=None, evidence=None, who="seme del repo")])

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")
    assert riga.value == "consumo_lordo", "il seme ha schiacciato una correzione a mano"


def test_un_seme_di_PRIORITA_ALTA_corregge_uno_di_priorita_bassa(sapere):
    """**Il repo batte l'installazione, e non per ordine d'arrivo.**

    Senza una precedenza esplicita vinceva chi arrivava prima: su una casa che
    aveva gia' importato il nome pubblicato da Home Assistant («Indice AQI»),
    la frase piu' ricca aggiunta da un rilascio successivo non sarebbe
    atterrata mai. E' l'ordine sfortunato, che la prova gemella non copriva.

    Mutazione ESEGUITA: togliere il confronto fra le priorita' -- rossa.
    """
    sapere.seed([_riga(value="Indice AQI", provenance="importato",
                       evidence=None, who="l'installazione")], priority=1)

    sapere.seed([_riga(value="l'indice di qualita' dell'aria, non una misura",
                       provenance="importato", evidence=None,
                       who="seme del repo")], priority=2)

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")
    assert riga.value.startswith("l'indice")


def test_un_seme_di_PRIORITA_BASSA_non_tocca_quello_del_repo(sapere):
    """L'altra direzione: il nome pubblicato non schiaccia la frase, nemmeno
    quando arriva dopo."""
    sapere.seed([_riga(value="la frase del repo", provenance="importato",
                       evidence=None, who="seme del repo")], priority=2)

    sapere.seed([_riga(value="Nome", provenance="importato",
                       evidence=None, who="l'installazione")], priority=1)

    [riga] = sapere.read(subject_kind="integrazione", subject="zcsazzurro")
    assert riga.value == "la frase del repo"

def test_migration_4_toglie_le_ricette_che_il_registro_rifiuta(tmp_path):
    """**La prima ricetta che il modello abbia mai scritto era ineseguibile**,
    e non per colpa sua: gliel'avevamo offerta noi. Il 14/09/2026 la casa vera
    rispondeva

        riparazione: {"oggetti": "sollevata",
                      "perche": "TypeError: _episode() missing 2 required
                                 keyword-only arguments: 'is_on' and 'period_end'"}

    e la riaggregazione moriva a ogni riavvio.

    La validazione nuova la rifiuta, quindi il resoconto non muore piu'. Ma la
    riga resterebbe nel sapere per sempre, e `devices_to_ask` non richiede a chi
    una risposta l'ha gia' data: quel dispositivo non avrebbe una ricetta mai
    piu'. **Si toglie**, e il giro successivo lo richiede -- stavolta con un
    catalogo che non offre cio' che non si puo' scrivere.

    Non e' un'eccezione alla regola «mai dati dell'utente», per la stessa
    ragione di `_migration_3`: e' una riga che questo programma ha scritto su se
    stesso, sbagliando.

    Mutazione: togliere `4: _migration_4` dal dizionario `migrations` -- il
    test torna rosso su `assert rimaste == ["dev_buono"]`.
    """
    percorso = str(tmp_path / "sapere.db")
    sapere = sap.KnowledgeStore(percorso)
    buona = {"why": "quanto ha prodotto", "steps": [
        {"name": "totale", "operation": "somma_periodo",
         "inputs": ["@sensor.p"], "params": {"unit": "kWh"}}]}
    storta = {"why": "quanto e' stato acceso", "steps": [
        {"name": "acceso", "operation": "episodio", "inputs": ["@climate.x"]}]}
    for soggetto, dati in (("dev_buono", buona), ("dev_storto", storta)):
        sapere.write(sap.Fact(subject_kind="dispositivo", subject=soggetto,
                          field="ricetta", value=json.dumps(dati),
                          provenance="dedotto",
                          evidence="il dispositivo con le sue entita'",
                          who="modello", when_ts=1.0))
    # Si riporta lo schema indietro, come farebbe l'archivio del proprietario
    # prima dell'aggiornamento.
    sapere._conn.execute("PRAGMA user_version = 3")
    sapere._conn.commit()
    sapere.close()

    riaperto = sap.KnowledgeStore(percorso)
    rimaste = sorted(r["subject"] for r in riaperto._conn.execute(
        "SELECT subject FROM knowledge WHERE field = 'ricetta'").fetchall())
    assert rimaste == ["dev_buono"]
    riaperto.close()


def test_migration_4_non_tocca_una_ricetta_che_si_puo_ancora_eseguire(tmp_path):
    """Il contrario della precedente, detto da solo: una ricetta valida resta,
    con il suo contenuto intatto. Cancellare il sapere buono per riguadagnare
    cio' che c'era gia' sarebbe il danno peggiore dei due.

    Mutazione: cancellare tutte le righe `ricetta` invece delle sole rifiutate
    -- rossa.
    """
    percorso = str(tmp_path / "sapere.db")
    sapere = sap.KnowledgeStore(percorso)
    buona = {"why": "quanto ha prodotto", "steps": [
        {"name": "totale", "operation": "somma_periodo",
         "inputs": ["@sensor.p"], "params": {"unit": "kWh"}}]}
    sapere.write(sap.Fact(subject_kind="dispositivo", subject="dev_buono",
                      field="ricetta", value=json.dumps(buona),
                      provenance="dedotto",
                      evidence="il dispositivo con le sue entita'",
                      who="modello", when_ts=1.0))
    sapere._conn.execute("PRAGMA user_version = 3")
    sapere._conn.commit()
    sapere.close()

    riaperto = sap.KnowledgeStore(percorso)
    righe = riaperto._conn.execute(
        "SELECT value FROM knowledge WHERE subject = 'dev_buono'").fetchall()
    assert len(righe) == 1
    assert json.loads(righe[0]["value"]) == buona
    riaperto.close()
