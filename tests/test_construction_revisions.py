"""L'archivio delle costruzioni: proposte e atti, lo stesso oggetto in due momenti."""
import os
import sqlite3

import pytest

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.chat_thread import ChatThread

ADESSO = 1_756_000_000.0
PAOLO = ChatThread("persona:p", "pannello")


@pytest.fixture()
def archivio(tmp_path):
    a = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    yield a
    a.close()


def _proponi(a, **kw):
    base = {"operation": "crea", "domain": "automation", "key": "1771", "actor": "chat",
                "exchange": "t1", "phrase": "apri le tapparelle all'alba", "prima": None,
                "dopo": {"id": "1771", "alias": "Tapparelle"}, "helper": [],
                "preview": "Creo un'automazione che apre le tapparelle all'alba.", "stakes": None,
                "now": ADESSO}
    base.update(kw)
    return a.propose(**base)


def test_una_proposta_nasce_in_attesa_e_si_rilegge_intera(archivio):
    helper = [{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}]
    ident = _proponi(archivio, helper=helper)["id"]
    riga = archivio.read(ident, now=ADESSO)
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
    archivio.mark_applied(ident, now=ADESSO + 10, execution_id="abc123")
    riga = archivio.read(ident, now=ADESSO)
    assert riga["stato"] == "applicata"
    assert riga["esecuzione_id"] == "abc123"


def test_rifiutare_conserva_il_motivo(archivio):
    ident = _proponi(archivio)["id"]
    archivio.mark_rejected(ident, now=ADESSO + 5, reason="l'utente ha detto di no")
    assert archivio.read(ident, now=ADESSO)["stato"] == "rifiutata"
    assert "no" in archivio.read(ident, now=ADESSO)["motivo"]


def test_oltre_il_tetto_non_si_propone_e_il_rifiuto_dice_quante(archivio):
    for n in range(ConstructionStore.MAX_PENDING):
        _proponi(archivio, key=f"k{n}")
    esito = _proponi(archivio, key="una_di_troppo")
    assert "id" not in esito
    assert f"il tetto e' {ConstructionStore.MAX_PENDING}" in esito["errore"]


def test_una_proposta_vecchia_si_LEGGE_scaduta_e_lo_dichiara(archivio):
    """Una lettura non scrive (misura del Task 4.0 degli attori, 06/10/2026):
    la scaduta esce scaduta col suo motivo, e il disco resta com'era."""
    ident = _proponi(archivio)["id"]
    oltre = ADESSO + ConstructionStore.DEADLINE_S + 1

    assert archivio.read(ident, now=ADESSO)["stato"] == "in_attesa"
    riga = archivio.read(ident, now=oltre)
    assert (riga["stato"], riga["motivo"]) == ("scaduta", "scaduta senza risposta")
    assert [r["stato"] for r in archivio.list(now=oltre)] == ["scaduta"]
    assert archivio.list(now=oltre, pending_only=True) == []
    assert archivio._conn.execute(
        "SELECT stato FROM costruzioni WHERE id=?", (ident,)).fetchone()[0] == "in_attesa"


def test_una_proposta_applicata_non_scade(archivio):
    ident = _proponi(archivio)["id"]
    archivio.mark_applied(ident, now=ADESSO, execution_id="x")
    oltre = ADESSO + ConstructionStore.DEADLINE_S + 1
    assert archivio.read(ident, now=oltre)["stato"] == "applicata"


def test_una_scaduta_mai_segnata_non_si_rivendica_ne_si_disdice(archivio):
    """Fino al 06/10/2026 la scadenza la scriveva solo l'apertura della
    pagina: una proposta scaduta che nessuno aveva aperto restava
    confermabile dalla chat. Rivendicarla o disdirla guarda la stessa regola
    di chi la legge.

    Mutazione ESEGUITA (06/10/2026): tolto `AND NOT _EXPIRED_SQL` da `claim`
    -- rossa, la rivendicazione passa."""
    ident = _proponi(archivio)["id"]
    oltre = ADESSO + ConstructionStore.DEADLINE_S + 1

    assert "errore" in archivio.claim(ident, now=oltre)
    assert "errore" in archivio.mark_cancelled(ident, now=oltre)
    assert archivio.read(ident, now=oltre)["stato"] == "scaduta"


def test_proporre_fa_scadere_le_vecchie_da_solo(archivio):
    """L'unico che SEGNA le scadute sul disco e' `propose`, e libera il
    tetto: senza questa prova la scadenza scritta sarebbe una regola mai
    eseguita."""
    for n in range(ConstructionStore.MAX_PENDING):
        _proponi(archivio, key=f"k{n}")
    tardi = ADESSO + ConstructionStore.DEADLINE_S + 1
    esito = _proponi(archivio, key="adesso_ci_sta", now=tardi)
    assert "id" in esito, "il tetto non si e' liberato: nessuno ha fatto scadere le vecchie"
    assert archivio.read(archivio.list(now=ADESSO)[-1]["id"], now=ADESSO)["stato"] == "scaduta"


def test_la_potatura_non_cancella_mai_l_ultima_versione_di_un_oggetto(archivio):
    """HA non tiene storico: quella riga e' l'unica copia esistente al mondo."""
    vecchia = _proponi(archivio, operation="modifica", prima={"alias": "a"},
                       dopo={"alias": "b"})["id"]
    archivio.mark_applied(vecchia, now=ADESSO, execution_id="e1")
    # Una scrittura molto piu' tardi innesca la potatura.
    tardi = ADESSO + ConstructionStore.RETENTION_S + 86400
    nuova = _proponi(archivio, key="altra", now=tardi)["id"]
    assert archivio.read(nuova, now=ADESSO) is not None
    assert archivio.read(vecchia, now=ADESSO) is not None, "l'unica copia del «prima» e' sparita"


def test_una_riga_vecchia_e_superata_si_pota(archivio):
    superata = _proponi(archivio, operation="modifica", prima={"alias": "a"},
                        dopo={"alias": "b"})["id"]
    archivio.mark_applied(superata, now=ADESSO, execution_id="e1")
    recente = _proponi(archivio, operation="modifica", prima={"alias": "b"},
                       dopo={"alias": "c"}, now=ADESSO + 60)["id"]
    archivio.mark_applied(recente, now=ADESSO + 60, execution_id="e2")
    tardi = ADESSO + ConstructionStore.RETENTION_S + 86400
    # `_prune` e' l'unica operazione irreversibile del modulo: il suo
    # conteggio va sorvegliato quanto quello di `_scadi`.
    with archivio._lock:
        quante = archivio._prune(tardi)
    assert quante == 1
    assert archivio.read(superata, now=ADESSO) is None
    assert archivio.read(recente, now=ADESSO) is not None


def test_elenca_in_attesa_da_le_sole_proposte_aperte(archivio):
    aperta = _proponi(archivio)["id"]
    chiusa = _proponi(archivio, key="altra")["id"]
    archivio.mark_applied(chiusa, now=ADESSO, execution_id="e")
    identificatori = [r["id"] for r in archivio.list(now=ADESSO, pending_only=True)]
    assert identificatori == [aperta]


def test_applicare_due_volte_la_stessa_proposta_non_si_puo(archivio):
    ident = _proponi(archivio)["id"]
    assert "errore" not in archivio.mark_applied(ident, now=ADESSO, execution_id="e1")
    secondo = archivio.mark_applied(ident, now=ADESSO + 1, execution_id="e2")
    assert "errore" in secondo


def test_rivendicare_prende_in_carico_una_sola_volta(archivio):
    """La stessa guardia usata dalle promesse in keeper/store.py:
    chi rivendica per primo vince, il secondo trova la porta chiusa."""
    ident = _proponi(archivio)["id"]
    prima = archivio.claim(ident, now=ADESSO + 1)
    assert "errore" not in prima
    assert archivio.read(ident, now=ADESSO)["stato"] == "in_corso"
    seconda = archivio.claim(ident, now=ADESSO + 2)
    assert "errore" in seconda


def test_segna_applicata_transita_anche_da_in_corso(archivio):
    """Dopo `claim` la riga e' `in_corso`, non piu' `in_attesa`: la
    transizione finale deve continuare a funzionare da li'."""
    ident = _proponi(archivio)["id"]
    archivio.claim(ident, now=ADESSO + 1)
    esito = archivio.mark_applied(ident, now=ADESSO + 2, execution_id="e1")
    assert "errore" not in esito
    assert archivio.read(ident, now=ADESSO)["stato"] == "applicata"


def test_una_rivendicata_al_riavvio_si_risana_e_non_riparte(archivio):
    """Se l'add-on muore fra `claim` e la transizione finale, la riga
    resterebbe `in_corso` per sempre -- un fantasma senza via d'uscita
    (mai scaduta, mai piu' rivendicabile). `risana()` la chiude dichiarando
    l'incertezza, non un esito: dopo un riavvio a meta' non si sa se Home
    Assistant abbia gia' ricevuto la scrittura."""
    ident = _proponi(archivio)["id"]
    archivio.claim(ident, now=ADESSO + 1)

    quante = archivio.risana(now=ADESSO + 100)

    assert quante == 1
    riga = archivio.read(ident, now=ADESSO)
    assert riga["stato"] == "rifiutata"
    assert "riavviato" in riga["motivo"]
    # Non riparte: dopo `risana` non e' piu' rivendicabile ne' scaduta.
    assert "errore" in archivio.claim(ident, now=ADESSO + 200)


def test_il_no_del_proprietario_e_uno_stato_suo_non_un_fallimento(archivio):
    """`rifiutata` vuol dire «ho provato e non ci sono riuscito». Il no
    dell'utente non e' un fallimento e non deve leggersi come tale."""
    ident = _proponi(archivio)["id"]
    esito = archivio.mark_cancelled(ident, now=ADESSO + 5)
    assert "errore" not in esito
    riga = archivio.read(ident, now=ADESSO)
    assert riga["stato"] == "disdetta"
    assert riga["motivo"]


def test_non_si_disdice_cio_che_e_gia_stato_applicato(archivio):
    ident = _proponi(archivio)["id"]
    archivio.mark_applied(ident, now=ADESSO, execution_id="e1")
    assert "errore" in archivio.mark_cancelled(ident, now=ADESSO + 5)


def test_non_si_disdice_una_riga_gia_rivendicata(archivio):
    """Cucitura Task 5 <-> Task 10-bis (ondata finale, punto 2): la disdetta
    transita SOLO da `in_attesa`, non anche da `in_corso` come la `WHERE`
    condivisa da `_change_state` ammetterebbe.

    La corsa che questo test chiude: una conferma dalla chat rivendica la
    riga (passa a `in_corso`) e comincia a scrivere su Home Assistant; nella
    stessa finestra un Rifiuta dalla pagina arriverebbe a `disdetta` PRIMA
    che la scrittura torni. Se la disdetta fosse permessa da `in_corso`, la
    scrittura arriverebbe comunque a Home Assistant -- l'automazione
    esisterebbe DAVVERO -- ma la riga che la descrive resterebbe `disdetta`,
    fuori dall'insieme che `_prune` protegge per sempre: il suo «prima»,
    l'unica copia al mondo di com'era l'oggetto, diventerebbe cancellabile a
    90 giorni. Impedendo la transizione da `in_corso`, chi ha vinto la
    rivendicazione e' l'unico che puo' portare la riga a uno stato finale."""
    ident = _proponi(archivio)["id"]
    rivendicata = archivio.claim(ident, now=ADESSO + 1)
    assert "errore" not in rivendicata
    assert archivio.read(ident, now=ADESSO)["stato"] == "in_corso"

    esito = archivio.mark_cancelled(ident, now=ADESSO + 2)

    assert "errore" in esito
    assert archivio.read(ident, now=ADESSO)["stato"] == "in_corso"


def test_una_proposta_disdetta_libera_il_posto_sotto_il_tetto(archivio):
    for n in range(ConstructionStore.MAX_PENDING):
        _proponi(archivio, key=f"k{n}")
    prima = archivio.list(now=ADESSO, pending_only=True)[0]["id"]
    archivio.mark_cancelled(prima, now=ADESSO + 1)
    assert "id" in _proponi(archivio, key="adesso_ci_sta", now=ADESSO + 2)


def test_una_proposta_in_corso_compare_fra_le_pendenti_e_conta_contro_il_tetto(archivio):
    """Una proposta rivendicata (`in_corso`) e' ancora in sospeso, non
    conclusa: non deve sparire dall'elenco delle pendenti ne' smettere di
    occupare un posto sotto il tetto nella finestra fra `claim` e la
    transizione finale -- altrimenti due `apply` in corsa potrebbero far
    salire il numero vero di proposte in volo oltre il tetto dichiarato."""
    ident = _proponi(archivio)["id"]
    archivio.claim(ident, now=ADESSO + 1)

    pendenti = [r["id"] for r in archivio.list(now=ADESSO, pending_only=True)]
    assert pendenti == [ident]

    for n in range(ConstructionStore.MAX_PENDING - 1):
        assert "errore" not in _proponi(archivio, key=f"altra{n}")
    esito = _proponi(archivio, key="una_di_troppo")
    assert "id" not in esito, "in_corso deve continuare a contare per il tetto"


# ==== Task 7 «confirm resta nel filo» ======================================

def test_proporre_con_un_filo_lo_scrive(archivio):
    ident = _proponi(archivio, thread=PAOLO)["id"]
    riga = archivio.read(ident, now=ADESSO)
    assert riga["thread"] == ChatThread("persona:p", "pannello")
    assert "subject_key" not in riga and "entry_point" not in riga


def test_proporre_senza_filo_resta_senza(archivio):
    """Il comportamento di sempre: nessun filo passato, nessun filo scritto --
    e' cosi' che propone anche l'attuatore (`server.py::_file_proposals`)."""
    ident = _proponi(archivio)["id"]
    riga = archivio.read(ident, now=ADESSO)
    assert riga["thread"] is None


def test_la_migrazione_v1_conserva_le_righe_come_senza_filo(tmp_path):
    """Un archivio nato prima della fetta «le chat divise» (v1, senza
    `subject_key`/`entry_point`): la migrazione aggiunge le colonne con
    `ALTER TABLE` e la riga esistente resta leggibile, senza filo -- stesso
    principio della migrazione v3 di `chat_store.py` per la cronologia di
    prima (decisione 5)."""
    db = str(tmp_path / "c.db")
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE costruzioni (
          id TEXT PRIMARY KEY, creata_ts REAL NOT NULL, aggiornata_ts REAL NOT NULL,
          stato TEXT NOT NULL, gesto TEXT NOT NULL, dominio TEXT NOT NULL, chiave TEXT NOT NULL,
          origine TEXT NOT NULL, turno TEXT, frase TEXT, prima_json TEXT, dopo_json TEXT,
          helper_json TEXT, anteprima TEXT, esecuzione_id TEXT, motivo TEXT
      );
      INSERT INTO costruzioni(id,creata_ts,aggiornata_ts,stato,gesto,dominio,chiave,origine,
          turno,frase,prima_json,dopo_json,helper_json,anteprima,esecuzione_id,motivo)
        VALUES ('c1', 1.0, 1.0, 'in_attesa', 'crea', 'automation', '1771', 'chat',
          't1', 'apri le tapparelle', NULL, '{"id":"1771"}', '[]', 'anteprima', NULL, NULL);
      PRAGMA user_version=1;
    """)
    c.close()

    a = ConstructionStore(db)
    riga = a.read("c1", now=1.0)
    assert riga["thread"] is None
    # Anche cio' che c'era prima resta intatto -- non solo cio' che e' nuovo.
    assert riga["stato"] == "in_attesa"
    assert riga["chiave"] == "1771"
    a.close()



def test_le_proposte_del_CERVELLO_si_leggono_per_impronta(archivio):
    """Revisione indipendente, giro 24 (D24-2): l'impronta e la prova di una
    costruibile restano sulla sua riga, e si leggono con la stessa forma delle
    proposte a mano. `aperta` e' sospesa e non scaduta; quelle della chat,
    senza impronta, non ci sono.

    Mutazione ESEGUITA (06/10/2026): `aperta` senza il predicato della
    scadenza -- rossa sulla scaduta."""
    _proponi(archivio, key="dalla_chat")
    aperta = _proponi(archivio, key="a", fingerprint="dev1|prelievo|None|1",
                      prova={"base": 19})["id"]
    oltre = ADESSO + ConstructionStore.DEADLINE_S + 1

    decise = archivio.decided_proposals(now=ADESSO)
    assert decise == {"dev1|prelievo|None|1": {
        "prova": {"base": 19}, "aperta": True, "creata_ts": ADESSO}}
    assert archivio.decided_proposals(now=oltre)["dev1|prelievo|None|1"]["aperta"] is False
    riga = archivio.read(aperta, now=ADESSO)
    assert (riga["impronta"], riga["prova"]) == ("dev1|prelievo|None|1", {"base": 19})
