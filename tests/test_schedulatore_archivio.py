"""L'archivio delle promesse: l'unica casa di «cosa e quando»."""
import os

import pytest

from hiris.app.schedulatore.archivio import ArchivioPromesse
from hiris.app.schedulatore.promessa import (
    CONSERVAZIONE_S, TETTO_IN_SOSPESO,
)

ADESSO = 1_755_600_000.0


@pytest.fixture()
def archivio(tmp_path):
    a = ArchivioPromesse(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _fai(**extra):
    dati = {
        "specie": "fai",
        "frase": "alle 17 accendi lo studio",
        "quando_ts": ADESSO + 3600,
        "quando_detto": "alle 17",
        "fuso": "Europe/Rome",
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
    }
    dati.update(extra)
    return dati


def test_una_promessa_creata_si_rilegge_con_la_stessa_forma(archivio):
    esito = archivio.crea(_fai(), adesso=ADESSO)
    assert "errore" not in esito
    p = esito["promessa"]
    assert p["stato"] == "in_attesa"
    assert p["frase"] == "alle 17 accendi lo studio"
    assert p["chiamata"]["servizio"] == "light.turn_on"
    assert archivio.leggi(p["id"]) == p


def test_una_promessa_non_valida_non_entra(archivio):
    esito = archivio.crea(_fai(quando_ts=ADESSO - 1), adesso=ADESSO)
    assert "errore" in esito
    assert archivio.elenca() == []


def test_sopravvive_alla_chiusura_e_riapertura(tmp_path):
    """Il riavvio dell'add-on, ridotto alla sua essenza."""
    percorso = os.path.join(str(tmp_path), "promesse.db")
    primo = ArchivioPromesse(percorso)
    ident = primo.crea(_fai(), adesso=ADESSO)["promessa"]["id"]
    primo.close()

    secondo = ArchivioPromesse(percorso)
    try:
        assert secondo.leggi(ident)["stato"] == "in_attesa"
    finally:
        secondo.close()


def test_scadute_torna_solo_cio_che_e_in_attesa_e_gia_scaduto(archivio):
    presto = archivio.crea(_fai(quando_ts=ADESSO + 10), adesso=ADESSO)["promessa"]["id"]
    tardi = archivio.crea(_fai(quando_ts=ADESSO + 9999), adesso=ADESSO)["promessa"]["id"]
    scadute = archivio.scadute(ADESSO + 60)
    assert [p["id"] for p in scadute] == [presto]
    assert tardi not in [p["id"] for p in scadute]


def test_prendi_riesce_una_volta_sola(archivio):
    """Mai due volte: e' `prendi` a garantirlo, non il chiamante."""
    ident = archivio.crea(_fai(quando_ts=ADESSO + 10), adesso=ADESSO)["promessa"]["id"]
    assert archivio.prendi(ident, adesso=ADESSO + 20) is True
    assert archivio.prendi(ident, adesso=ADESSO + 20) is False
    assert archivio.leggi(ident)["stato"] == "in_corso"


def test_una_presa_in_corso_al_riavvio_diventa_fallita_e_non_riparte(archivio):
    ident = archivio.crea(_fai(quando_ts=ADESSO + 10), adesso=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, adesso=ADESSO + 20)

    assert archivio.risana(adesso=ADESSO + 100) == 1

    p = archivio.leggi(ident)
    assert p["stato"] == "fallita"
    assert "si e' fermato" in p["motivo"]
    assert archivio.scadute(ADESSO + 999) == []  # non torna in circolo


def test_concludi_scrive_stato_motivo_e_collegamento(archivio):
    ident = archivio.crea(_fai(quando_ts=ADESSO + 10), adesso=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, adesso=ADESSO + 20)
    archivio.concludi(ident, stato="mantenuta", esecuzione_id="e42", adesso=ADESSO + 21)

    p = archivio.leggi(ident)
    assert (p["stato"], p["esecuzione_id"], p["motivo"]) == ("mantenuta", "e42", None)
    assert p["risvegliata_ts"] == ADESSO + 20


def test_disdire_una_promessa_in_attesa_riesce_e_una_conclusa_no(archivio):
    ident = archivio.crea(_fai(), adesso=ADESSO)["promessa"]["id"]
    assert "errore" not in archivio.disdici(ident, adesso=ADESSO + 1)
    assert archivio.leggi(ident)["stato"] == "disdetta"

    secondo = archivio.disdici(ident, adesso=ADESSO + 2)
    assert "errore" in secondo
    assert "disdetta" in secondo["errore"]


def test_una_promessa_presa_non_si_disdice(archivio):
    """La decisione di `disdici` vive nella query, non in una lettura fatta
    prima: se un `prendi` fosse gia' passato, disdire non deve ne' riuscire
    ne' toccare lo stato che l'orologio ha appena scritto."""
    ident = archivio.crea(_fai(quando_ts=ADESSO + 10), adesso=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, adesso=ADESSO + 20)

    esito = archivio.disdici(ident, adesso=ADESSO + 21)
    assert "errore" in esito
    assert archivio.leggi(ident)["stato"] == "in_corso"


def test_il_tetto_delle_in_sospeso_rifiuta_nominandolo(archivio):
    for _ in range(TETTO_IN_SOSPESO):
        assert "errore" not in archivio.crea(_fai(), adesso=ADESSO)
    esito = archivio.crea(_fai(), adesso=ADESSO)
    assert "errore" in esito
    assert str(TETTO_IN_SOSPESO) in esito["errore"]


def test_le_concluse_vecchie_si_potano_alla_scrittura_le_in_sospeso_mai(archivio):
    vecchia = archivio.crea(_fai(quando_ts=ADESSO + 10), adesso=ADESSO)["promessa"]["id"]
    archivio.prendi(vecchia, adesso=ADESSO + 10)
    archivio.concludi(vecchia, stato="mantenuta", adesso=ADESSO + 10)
    in_sospeso = archivio.crea(_fai(quando_ts=ADESSO + 20 * 86400), adesso=ADESSO)["promessa"]["id"]

    dopo = ADESSO + CONSERVAZIONE_S + 86400
    recente = archivio.crea(_fai(quando_ts=dopo + 3600), adesso=dopo)["promessa"]["id"]
    archivio.prendi(recente, adesso=dopo + 3600)
    archivio.concludi(recente, stato="mantenuta", adesso=dopo + 3600)

    poco_dopo = dopo + 100  # troppo presto perche' «recente» sia fuori conservazione
    archivio.crea(_fai(quando_ts=poco_dopo + 3600), adesso=poco_dopo)

    assert archivio.leggi(vecchia) is None      # potata: piu' vecchia della conservazione
    assert archivio.leggi(in_sospeso) is not None  # mai potata: e' ancora una promessa
    assert archivio.leggi(recente) is not None  # conclusa ma giovane: non ancora il suo turno


def test_la_potatura_misura_l_eta_dalla_conclusione_non_dalla_nascita(archivio):
    """Fix review finale, rilievo minore. La spec §8.1 dice novanta giorni
    "per le promesse concluse": l'orologio della potatura deve partire da
    QUANDO si e' conclusa (`risvegliata_ts`), non da quando e' nata
    (`nata_ts`). Il test sopra non lo vedeva: crea e conclude quasi nello
    stesso istante, quindi `nata_ts` e `risvegliata_ts` sono troppo vicini
    per distinguere i due criteri.

    Qui una promessa nata 91 giorni fa (oltre la conservazione, se si
    guardasse la nascita) ma CONCLUSA ieri (dentro la conservazione, come
    dev'essere per una conclusione recente) non deve sparire.

    Mutazione che deve farlo fallire: rimettere `nata_ts` al posto di
    `risvegliata_ts` nella query di `_pota`.
    """
    nata = ADESSO - 91 * 86400
    conclusa = ADESSO - 86400  # ieri
    ident = archivio.crea(_fai(quando_ts=nata + 3600), adesso=nata)["promessa"]["id"]
    archivio.prendi(ident, adesso=conclusa)
    archivio.concludi(ident, stato="mantenuta", adesso=conclusa)

    # una scrittura successiva e' cio' che innesca la potatura (spec §8.1)
    archivio.crea(_fai(quando_ts=ADESSO + 3600), adesso=ADESSO)

    assert archivio.leggi(ident) is not None, (
        "nata 91 giorni fa ma CONCLUSA ieri: l'eta' della potatura deve "
        "partire dalla conclusione (risvegliata_ts), non dalla nascita "
        "(nata_ts) -- altrimenti una promessa legittimamente mantenuta ieri "
        "sparirebbe oggi solo perche' e' nata tardi")
