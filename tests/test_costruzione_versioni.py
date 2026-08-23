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
