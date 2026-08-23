"""L'archivio delle costruzioni: proposte e atti, lo stesso oggetto in due momenti."""
import os

import pytest

from hiris.app.azione.costruzione.versioni import ArchivioCostruzioni

ADESSO = 1_756_000_000.0


@pytest.fixture()
def archivio(tmp_path):
    a = ArchivioCostruzioni(os.path.join(str(tmp_path), "costruzioni.db"))
    yield a
    a.close()


def _proponi(a, **kw):
    base = dict(gesto="crea", dominio="automation", chiave="1771", origine="chat",
                turno="t1", frase="apri le tapparelle all'alba", prima=None,
                dopo={"id": "1771", "alias": "Tapparelle"}, helper=[],
                anteprima="Creo un'automazione che apre le tapparelle all'alba.",
                adesso=ADESSO)
    base.update(kw)
    return a.proponi(**base)


def test_una_proposta_nasce_in_attesa_e_si_rilegge_intera(archivio):
    helper = [{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}]
    ident = _proponi(archivio, helper=helper)["id"]
    riga = archivio.leggi(ident)
    assert riga["stato"] == "in_attesa"
    assert riga["gesto"] == "crea"
    assert riga["turno"] == "t1"
    assert riga["frase"] == "apri le tapparelle all'alba"
    assert riga["dopo"]["alias"] == "Tapparelle"
    assert riga["prima"] is None
    assert riga["origine"] == "chat"
    assert riga["helper"] == helper
    assert riga["anteprima"] == "Creo un'automazione che apre le tapparelle all'alba."


def test_applicare_scrive_lo_stato_e_il_collegamento_alla_cronaca(archivio):
    ident = _proponi(archivio)["id"]
    archivio.segna_applicata(ident, adesso=ADESSO + 10, esecuzione_id="abc123")
    riga = archivio.leggi(ident)
    assert riga["stato"] == "applicata"
    assert riga["esecuzione_id"] == "abc123"


def test_rifiutare_conserva_il_motivo(archivio):
    ident = _proponi(archivio)["id"]
    archivio.segna_rifiutata(ident, adesso=ADESSO + 5, motivo="l'utente ha detto di no")
    assert archivio.leggi(ident)["stato"] == "rifiutata"
    assert "no" in archivio.leggi(ident)["motivo"]


def test_oltre_il_tetto_non_si_propone_e_il_rifiuto_dice_quante(archivio):
    for n in range(ArchivioCostruzioni.MAX_IN_ATTESA):
        _proponi(archivio, chiave=f"k{n}")
    esito = _proponi(archivio, chiave="una_di_troppo")
    assert "id" not in esito
    assert f"il tetto e' {ArchivioCostruzioni.MAX_IN_ATTESA}" in esito["errore"]


def test_una_proposta_vecchia_scade_e_lo_dichiara(archivio):
    ident = _proponi(archivio)["id"]
    quante = archivio.scadi(ADESSO + ArchivioCostruzioni.SCADENZA_S + 1)
    assert quante == 1
    assert archivio.leggi(ident)["stato"] == "scaduta"


def test_una_proposta_applicata_non_scade(archivio):
    ident = _proponi(archivio)["id"]
    archivio.segna_applicata(ident, adesso=ADESSO, esecuzione_id="x")
    archivio.scadi(ADESSO + ArchivioCostruzioni.SCADENZA_S + 1)
    assert archivio.leggi(ident)["stato"] == "applicata"


def test_proporre_fa_scadere_le_vecchie_da_solo(archivio):
    """Nessuno chiama `scadi` in produzione se non lo fa `proponi`: senza questa
    prova la scadenza sarebbe una regola scritta e mai eseguita."""
    for n in range(ArchivioCostruzioni.MAX_IN_ATTESA):
        _proponi(archivio, chiave=f"k{n}")
    tardi = ADESSO + ArchivioCostruzioni.SCADENZA_S + 1
    esito = _proponi(archivio, chiave="adesso_ci_sta", adesso=tardi)
    assert "id" in esito, "il tetto non si e' liberato: nessuno ha fatto scadere le vecchie"
    assert archivio.leggi(archivio.elenca()[-1]["id"])["stato"] == "scaduta"


def test_l_ultima_versione_applicata_di_un_oggetto_si_ritrova(archivio):
    primo = _proponi(archivio, gesto="modifica", prima={"alias": "vecchio"},
                     dopo={"alias": "nuovo"})["id"]
    archivio.segna_applicata(primo, adesso=ADESSO, esecuzione_id="e1")
    secondo = _proponi(archivio, gesto="modifica", prima={"alias": "nuovo"},
                       dopo={"alias": "nuovissimo"}, adesso=ADESSO + 100)["id"]
    archivio.segna_applicata(secondo, adesso=ADESSO + 100, esecuzione_id="e2")
    # Una terza proposta, piu' recente, ma lasciata `in_attesa`: non e' mai
    # stata applicata, quindi non deve vincere l'ORDER BY su `secondo`.
    _proponi(archivio, gesto="modifica", prima={"alias": "nuovissimo"},
             dopo={"alias": "mai_successo"}, adesso=ADESSO + 200)
    ultima = archivio.ultima_applicata("automation", "1771")
    assert ultima["id"] == secondo
    assert ultima["prima"]["alias"] == "nuovo"


def test_la_potatura_non_cancella_mai_l_ultima_versione_di_un_oggetto(archivio):
    """HA non tiene storico: quella riga e' l'unica copia esistente al mondo."""
    vecchia = _proponi(archivio, gesto="modifica", prima={"alias": "a"},
                       dopo={"alias": "b"})["id"]
    archivio.segna_applicata(vecchia, adesso=ADESSO, esecuzione_id="e1")
    # Una scrittura molto piu' tardi innesca la potatura.
    tardi = ADESSO + ArchivioCostruzioni.CONSERVAZIONE_S + 86400
    nuova = _proponi(archivio, chiave="altra", adesso=tardi)["id"]
    assert archivio.leggi(nuova) is not None
    assert archivio.leggi(vecchia) is not None, "l'unica copia del «prima» e' sparita"


def test_una_riga_vecchia_e_superata_si_pota(archivio):
    superata = _proponi(archivio, gesto="modifica", prima={"alias": "a"},
                        dopo={"alias": "b"})["id"]
    archivio.segna_applicata(superata, adesso=ADESSO, esecuzione_id="e1")
    recente = _proponi(archivio, gesto="modifica", prima={"alias": "b"},
                       dopo={"alias": "c"}, adesso=ADESSO + 60)["id"]
    archivio.segna_applicata(recente, adesso=ADESSO + 60, esecuzione_id="e2")
    tardi = ADESSO + ArchivioCostruzioni.CONSERVAZIONE_S + 86400
    # `_pota` e' l'unica operazione irreversibile del modulo: il suo
    # conteggio va sorvegliato quanto quello pubblico di `scadi`.
    with archivio._lock:
        quante = archivio._pota(tardi)
    assert quante == 1
    assert archivio.leggi(superata) is None
    assert archivio.leggi(recente) is not None


def test_elenca_in_attesa_da_le_sole_proposte_aperte(archivio):
    aperta = _proponi(archivio)["id"]
    chiusa = _proponi(archivio, chiave="altra")["id"]
    archivio.segna_applicata(chiusa, adesso=ADESSO, esecuzione_id="e")
    identificatori = [r["id"] for r in archivio.elenca(solo_in_attesa=True)]
    assert identificatori == [aperta]


def test_applicare_due_volte_la_stessa_proposta_non_si_puo(archivio):
    ident = _proponi(archivio)["id"]
    assert "errore" not in archivio.segna_applicata(ident, adesso=ADESSO, esecuzione_id="e1")
    secondo = archivio.segna_applicata(ident, adesso=ADESSO + 1, esecuzione_id="e2")
    assert "errore" in secondo


def test_rivendicare_prende_in_carico_una_sola_volta(archivio):
    """La stessa guardia usata dalle promesse in schedulatore/archivio.py:
    chi rivendica per primo vince, il secondo trova la porta chiusa."""
    ident = _proponi(archivio)["id"]
    prima = archivio.rivendica(ident, adesso=ADESSO + 1)
    assert "errore" not in prima
    assert archivio.leggi(ident)["stato"] == "in_corso"
    seconda = archivio.rivendica(ident, adesso=ADESSO + 2)
    assert "errore" in seconda


def test_segna_applicata_transita_anche_da_in_corso(archivio):
    """Dopo `rivendica` la riga e' `in_corso`, non piu' `in_attesa`: la
    transizione finale deve continuare a funzionare da li'."""
    ident = _proponi(archivio)["id"]
    archivio.rivendica(ident, adesso=ADESSO + 1)
    esito = archivio.segna_applicata(ident, adesso=ADESSO + 2, esecuzione_id="e1")
    assert "errore" not in esito
    assert archivio.leggi(ident)["stato"] == "applicata"


def test_una_rivendicata_al_riavvio_si_risana_e_non_riparte(archivio):
    """Se l'add-on muore fra `rivendica` e la transizione finale, la riga
    resterebbe `in_corso` per sempre -- un fantasma senza via d'uscita
    (mai scaduta, mai piu' rivendicabile). `risana()` la chiude dichiarando
    l'incertezza, non un esito: dopo un riavvio a meta' non si sa se Home
    Assistant abbia gia' ricevuto la scrittura."""
    ident = _proponi(archivio)["id"]
    archivio.rivendica(ident, adesso=ADESSO + 1)

    quante = archivio.risana(adesso=ADESSO + 100)

    assert quante == 1
    riga = archivio.leggi(ident)
    assert riga["stato"] == "rifiutata"
    assert "riavviato" in riga["motivo"]
    # Non riparte: dopo `risana` non e' piu' rivendicabile ne' scaduta.
    assert "errore" in archivio.rivendica(ident, adesso=ADESSO + 200)


def test_il_no_del_proprietario_e_uno_stato_suo_non_un_fallimento(archivio):
    """`rifiutata` vuol dire «ho provato e non ci sono riuscito». Il no
    dell'utente non e' un fallimento e non deve leggersi come tale."""
    ident = _proponi(archivio)["id"]
    esito = archivio.segna_disdetta(ident, adesso=ADESSO + 5)
    assert "errore" not in esito
    riga = archivio.leggi(ident)
    assert riga["stato"] == "disdetta"
    assert riga["motivo"]


def test_non_si_disdice_cio_che_e_gia_stato_applicato(archivio):
    ident = _proponi(archivio)["id"]
    archivio.segna_applicata(ident, adesso=ADESSO, esecuzione_id="e1")
    assert "errore" in archivio.segna_disdetta(ident, adesso=ADESSO + 5)


def test_una_proposta_disdetta_libera_il_posto_sotto_il_tetto(archivio):
    for n in range(ArchivioCostruzioni.MAX_IN_ATTESA):
        _proponi(archivio, chiave=f"k{n}")
    prima = archivio.elenca(solo_in_attesa=True)[0]["id"]
    archivio.segna_disdetta(prima, adesso=ADESSO + 1)
    assert "id" in _proponi(archivio, chiave="adesso_ci_sta", adesso=ADESSO + 2)


def test_una_proposta_in_corso_compare_fra_le_pendenti_e_conta_contro_il_tetto(archivio):
    """Una proposta rivendicata (`in_corso`) e' ancora in sospeso, non
    conclusa: non deve sparire dall'elenco delle pendenti ne' smettere di
    occupare un posto sotto il tetto nella finestra fra `rivendica` e la
    transizione finale -- altrimenti due `applica` in corsa potrebbero far
    salire il numero vero di proposte in volo oltre il tetto dichiarato."""
    ident = _proponi(archivio)["id"]
    archivio.rivendica(ident, adesso=ADESSO + 1)

    pendenti = [r["id"] for r in archivio.elenca(solo_in_attesa=True)]
    assert pendenti == [ident]

    for n in range(ArchivioCostruzioni.MAX_IN_ATTESA - 1):
        assert "errore" not in _proponi(archivio, chiave=f"altra{n}")
    esito = _proponi(archivio, chiave="una_di_troppo")
    assert "id" not in esito, "in_corso deve continuare a contare per il tetto"

