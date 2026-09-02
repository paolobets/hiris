"""L'archivio delle promesse: l'unica casa di «cosa e quando»."""
import os

import pytest

from hiris.app.keeper.promise import (
    CEILING_IN_SOSPESO,
    CONSERVAZIONE_S,
)
from hiris.app.keeper.store import AgendaStore

ADESSO = 1_755_600_000.0


@pytest.fixture()
def archivio(tmp_path):
    a = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _fai(**extra):
    data = {
        "specie": "fai",
        "frase": "alle 17 accendi lo studio",
        "quando_ts": ADESSO + 3600,
        "quando_detto": "alle 17",
        "fuso": "Europe/Rome",
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
    }
    data.update(extra)
    return data


def test_una_promessa_creata_si_rilegge_con_la_stessa_forma(archivio):
    esito = archivio.create(_fai(), now=ADESSO)
    assert "errore" not in esito
    p = esito["promessa"]
    assert p["stato"] == "in_attesa"
    assert p["frase"] == "alle 17 accendi lo studio"
    assert p["chiamata"]["servizio"] == "light.turn_on"
    assert archivio.read(p["id"]) == p


def test_una_promessa_non_valida_non_entra(archivio):
    esito = archivio.create(_fai(quando_ts=ADESSO - 1), now=ADESSO)
    assert "errore" in esito
    assert archivio.list() == []


def test_sopravvive_alla_chiusura_e_riapertura(tmp_path):
    """Il riavvio dell'add-on, ridotto alla sua essenza."""
    percorso = os.path.join(str(tmp_path), "promesse.db")
    primo = AgendaStore(percorso)
    ident = primo.create(_fai(), now=ADESSO)["promessa"]["id"]
    primo.close()

    secondo = AgendaStore(percorso)
    try:
        assert secondo.read(ident)["stato"] == "in_attesa"
    finally:
        secondo.close()


def test_scadute_torna_solo_cio_che_e_in_attesa_e_gia_scaduto(archivio):
    presto = archivio.create(_fai(quando_ts=ADESSO + 10), now=ADESSO)["promessa"]["id"]
    tardi = archivio.create(_fai(quando_ts=ADESSO + 9999), now=ADESSO)["promessa"]["id"]
    scadute = archivio.scadute(ADESSO + 60)
    assert [p["id"] for p in scadute] == [presto]
    assert tardi not in [p["id"] for p in scadute]


def test_prendi_riesce_una_volta_sola(archivio):
    """Mai due volte: e' `prendi` a garantirlo, non il chiamante."""
    ident = archivio.create(_fai(quando_ts=ADESSO + 10), now=ADESSO)["promessa"]["id"]
    assert archivio.prendi(ident, now=ADESSO + 20) is True
    assert archivio.prendi(ident, now=ADESSO + 20) is False
    assert archivio.read(ident)["stato"] == "in_corso"


def test_una_presa_in_corso_al_riavvio_diventa_fallita_e_non_riparte(archivio):
    ident = archivio.create(_fai(quando_ts=ADESSO + 10), now=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, now=ADESSO + 20)

    assert archivio.risana(now=ADESSO + 100) == 1

    p = archivio.read(ident)
    assert p["stato"] == "fallita"
    assert "si e' fermato" in p["motivo"]
    assert archivio.scadute(ADESSO + 999) == []  # non torna in circolo


def test_concludi_scrive_stato_motivo_e_collegamento(archivio):
    ident = archivio.create(_fai(quando_ts=ADESSO + 10), now=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, now=ADESSO + 20)
    archivio.concludi(ident, state="mantenuta", execution_id="e42", now=ADESSO + 21)

    p = archivio.read(ident)
    assert (p["stato"], p["esecuzione_id"], p["motivo"]) == ("mantenuta", "e42", None)
    assert p["risvegliata_ts"] == ADESSO + 20


def test_disdire_una_promessa_in_attesa_riesce_e_una_conclusa_no(archivio):
    ident = archivio.create(_fai(), now=ADESSO)["promessa"]["id"]
    assert "errore" not in archivio.cancel(ident, now=ADESSO + 1)
    assert archivio.read(ident)["stato"] == "disdetta"

    secondo = archivio.cancel(ident, now=ADESSO + 2)
    assert "errore" in secondo
    assert "disdetta" in secondo["errore"]


def test_una_promessa_presa_non_si_disdice(archivio):
    """La decisione di `cancel` vive nella query, non in una lettura fatta
    prima: se un `prendi` fosse gia' passato, disdire non deve ne' riuscire
    ne' toccare lo stato che l'orologio ha appena scritto."""
    ident = archivio.create(_fai(quando_ts=ADESSO + 10), now=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, now=ADESSO + 20)

    esito = archivio.cancel(ident, now=ADESSO + 21)
    assert "errore" in esito
    assert archivio.read(ident)["stato"] == "in_corso"


def test_il_tetto_delle_in_sospeso_rifiuta_nominandolo(archivio):
    for _ in range(CEILING_IN_SOSPESO):
        assert "errore" not in archivio.create(_fai(), now=ADESSO)
    esito = archivio.create(_fai(), now=ADESSO)
    assert "errore" in esito
    assert str(CEILING_IN_SOSPESO) in esito["errore"]


def test_elenca_in_sospeso_include_anche_in_corso(archivio):
    """Review finale, rilievo ②: l'insieme «in sospeso» e' `STATES_SOSPESO`
    (`keeper/promise.py`), non solo `in_attesa` -- una promessa presa
    dall'orologio (`in_corso`) non e' ancora conclusa (guida di disegno §1),
    e non deve sparire dall'elenco fra `prendi()` e `concludi()`.

    Mutazione che deve farlo fallire: restringere la query di `list` a
    `stato='in_attesa'`."""
    ident = archivio.create(_fai(), now=ADESSO)["promessa"]["id"]
    archivio.prendi(ident, now=ADESSO + 1)

    sospese = archivio.list(solo_in_sospeso=True)
    assert [p["id"] for p in sospese] == [ident]
    assert sospese[0]["stato"] == "in_corso"


def test_lo_stato_in_corso_conta_nel_tetto_delle_in_sospeso(archivio):
    """Una promessa presa dall'orologio (`in_corso`) e' ancora sospesa, e
    deve continuare a occupare un posto sotto `CEILING_IN_SOSPESO` -- se
    contasse solo `in_attesa`, l'orologio potrebbe far salire il numero vero
    di promesse in volo oltre il tetto nella finestra fra `prendi` e
    `concludi`.

    Mutazione che deve farlo fallire: contare `stato='in_attesa'` invece di
    `stato IN (STATES_SOSPESO)` in `create()`."""
    for _ in range(CEILING_IN_SOSPESO - 1):
        archivio.create(_fai(), now=ADESSO)
    ultima = archivio.create(_fai(), now=ADESSO)["promessa"]["id"]
    assert archivio.prendi(ultima, now=ADESSO + 1) is True  # ora e' in_corso

    esito = archivio.create(_fai(), now=ADESSO)
    assert "errore" in esito, "in_corso deve continuare a contare per il tetto"


def test_le_concluse_vecchie_si_potano_alla_scrittura_le_in_sospeso_mai(archivio):
    vecchia = archivio.create(_fai(quando_ts=ADESSO + 10), now=ADESSO)["promessa"]["id"]
    archivio.prendi(vecchia, now=ADESSO + 10)
    archivio.concludi(vecchia, state="mantenuta", now=ADESSO + 10)
    in_sospeso = archivio.create(_fai(quando_ts=ADESSO + 20 * 86400), now=ADESSO)["promessa"]["id"]

    dopo = ADESSO + CONSERVAZIONE_S + 86400
    recente = archivio.create(_fai(quando_ts=dopo + 3600), now=dopo)["promessa"]["id"]
    archivio.prendi(recente, now=dopo + 3600)
    archivio.concludi(recente, state="mantenuta", now=dopo + 3600)

    poco_dopo = dopo + 100  # troppo presto perche' «recente» sia fuori conservazione
    archivio.create(_fai(quando_ts=poco_dopo + 3600), now=poco_dopo)

    assert archivio.read(vecchia) is None      # potata: piu' vecchia della conservazione
    assert archivio.read(in_sospeso) is not None  # mai potata: e' ancora una promessa
    assert archivio.read(recente) is not None  # conclusa ma giovane: non ancora il suo turno


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
    `risvegliata_ts` nella query di `_prune`.
    """
    nata = ADESSO - 91 * 86400
    conclusa = ADESSO - 86400  # ieri
    ident = archivio.create(_fai(quando_ts=nata + 3600), now=nata)["promessa"]["id"]
    archivio.prendi(ident, now=conclusa)
    archivio.concludi(ident, state="mantenuta", now=conclusa)

    # una scrittura successiva e' cio' che innesca la potatura (spec §8.1)
    archivio.create(_fai(quando_ts=ADESSO + 3600), now=ADESSO)

    assert archivio.read(ident) is not None, (
        "nata 91 giorni fa ma CONCLUSA ieri: l'eta' della potatura deve "
        "partire dalla conclusione (risvegliata_ts), non dalla nascita "
        "(nata_ts) -- altrimenti una promessa legittimamente mantenuta ieri "
        "sparirebbe oggi solo perche' e' nata tardi")
