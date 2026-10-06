"""L'archivio delle PROPOSTE da fare a mano (spec 2026-09-21 §3).

**Due archivi, una pagina.** Le proposte costruibili vivono dove vivono oggi,
nella tabella dell'officina, con l'anteprima e il diff; quelle che deve fare
una persona -- «sposta i consumi flessibili nel pomeriggio» -- non hanno
gesto, ne' dominio, ne' un diff, e infilarle li' vorrebbe dire riempire cinque
colonne di finti valori e avere una riga su cui meta' della macchina
dell'officina non si applica.

«Un posto solo dove si decide» e' una promessa sulla **pagina**, non sulla
tabella: e' la pagina a mostrarle insieme.

**I tre esiti** valgono per entrambe: crea (solo per le costruibili), rifiuta,
e **«fatto fuori da HA»** -- che chiude la proposta come applicata dichiarando
che non e' stato HIRIS a farlo. Per il verificatore, un domani, «l'ho fatto io»
e «lo hai fatto tu» sono due prove diverse.
"""
import pytest

from hiris.app.mind.store import ObservationsStore


@pytest.fixture()
def archivio(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        yield store
    finally:
        store.close()


def _proposta(archivio, **extra):
    campi = {"text": "Sposta la lavatrice nel primo pomeriggio",
             "perche": "il prelievo dalla rete si concentra la mattina",
             "fingerprint": "dev1|prelievo|None|1",
             "prova": {"base": 19, "quanti_scarti": 3, "spiegato": None},
             "stakes": None}
    campi.update(extra)
    return archivio.add_proposal(**campi, now_ts=100.0)


def test_una_proposta_si_scrive_e_si_rilegge(archivio):
    """Mutazione: non scrivere `perche` -- rossa (una proposta senza la sua
    ragione e' un ordine, e questa pagina esiste per non darne)."""
    ident = _proposta(archivio)

    righe = archivio.proposals()
    assert len(righe) == 1
    assert righe[0]["id"] == ident
    assert righe[0]["testo"].startswith("Sposta la lavatrice")
    assert righe[0]["perche"].startswith("il prelievo")
    assert righe[0]["stato"] == "attesa"


def test_i_TRE_esiti_chiudono_la_proposta(archivio):
    """Crea non si applica qui (nessun oggetto da scrivere): restano rifiuta e
    «fatto fuori da HA», e sono esiti DIVERSI -- il secondo e' positivo.

    Mutazione: trattarli come lo stesso stato -- rossa (il verificatore non
    potrebbe distinguere «non l'ho voluto» da «l'ho fatto io»)."""
    rifiutata = _proposta(archivio)
    fatta = _proposta(archivio, fingerprint="dev2|consumo|None|1")

    archivio.close_proposal(rifiutata, "rifiutata")
    archivio.close_proposal(fatta, "fatta_fuori", why="l'ho spostata a mano")

    per_id = {r["id"]: r for r in archivio.proposals()}
    assert per_id[rifiutata]["stato"] == "rifiutata"
    assert per_id[fatta]["stato"] == "fatta_fuori"
    assert per_id[fatta]["esito_nota"] == "l'ho spostata a mano"


def test_un_esito_SCONOSCIUTO_si_rifiuta(archivio):
    """Gli esiti sono chiusi: una parola nuova arriverebbe da una rotta, e
    diventerebbe uno stato che nessuna pagina sa disegnare.

    Mutazione: accettare qualunque stringa -- rossa."""
    ident = _proposta(archivio)

    with pytest.raises(ValueError):
        archivio.close_proposal(ident, "forse")


def test_solo_le_proposte_APERTE_quando_si_chiedono_quelle(archivio):
    """Il pallino conta cio' che aspetta te: una proposta chiusa non aspetta
    piu' niente.

    Mutazione: ignorare `pending_only` -- rossa."""
    aperta = _proposta(archivio)
    chiusa = _proposta(archivio, fingerprint="dev2|consumo|None|1")
    archivio.close_proposal(chiusa, "rifiutata")

    aperte = archivio.proposals(pending_only=True)
    assert [r["id"] for r in aperte] == [aperta]


def test_il_filo_dei_GIRI_si_accoda_e_si_rilegge_in_ordine(archivio):
    """«Rifalla» apre un testo e ripete il turno, senza limiti: ogni giro
    resta attaccato alla proposta -- la forma scartata e cio' che hai chiesto
    -- cosi' il modello vede il filo intero e non ripropone quello che hai
    appena rifiutato.

    Mutazione: sostituire invece di accodare -- rossa (il modello vedrebbe
    solo l'ultima richiesta e potrebbe tornare alla prima forma)."""
    ident = _proposta(archivio)

    archivio.add_proposal_round(ident, request="troppo presto, dopo le 14",
                                text="Sposta la lavatrice dopo le 14", now_ts=300.0)
    archivio.add_proposal_round(ident, request="e solo nei feriali",
                                text="Sposta la lavatrice dopo le 14, nei feriali",
                                now_ts=400.0)

    riga = archivio.proposals()[0]
    assert [g["richiesta"] for g in riga["giri"]] == [
        "troppo presto, dopo le 14", "e solo nei feriali"]
    assert riga["testo"].endswith("nei feriali"), (
        "il testo della proposta deve essere l'ULTIMA forma, non la prima")
    assert riga["stato"] == "attesa", "un giro non chiude niente"


def test_le_proposte_DECISE_si_leggono_per_impronta(archivio):
    """E' cio' che serve all'anti-ripetizione: l'attuatore salta una domanda
    la cui impronta ha gia' una proposta decisa **con la stessa prova**.

    Mutazione: tornare anche quelle in attesa senza distinguerle -- rossa (una
    proposta aperta verrebbe riproposta come se fosse stata decisa)."""
    aperta = _proposta(archivio)
    chiusa = _proposta(archivio, fingerprint="dev2|consumo|None|1",
                       prova={"base": 3, "quanti_scarti": 1, "spiegato": None})
    archivio.close_proposal(chiusa, "rifiutata")

    decise = archivio.decided_proposals()
    assert set(decise) == {"dev1|prelievo|None|1", "dev2|consumo|None|1"}
    assert decise["dev2|consumo|None|1"]["base"] == 3
    assert aperta  # la proposta aperta conta: non si duplica una coda aperta


def test_una_proposta_senza_IMPRONTA_non_si_scrive(archivio):
    """Senza impronta l'anti-ripetizione non puo' funzionare, e la stessa
    proposta tornerebbe ogni giorno.

    Mutazione: rendere l'impronta facoltativa -- rossa."""
    with pytest.raises(ValueError):
        archivio.add_proposal(text="x", perche="y", fingerprint="", prova={},
                              stakes=None, now_ts=100.0)


#: La tabella com'era fino alla versione 11 dello schema (06/10/2026), con
#: le tre colonne che il censimento del 01/10/2026 ha trovato inutili
#: (`attori/censimento-database-2026-10-01.md`, punti 6 e 7).
_PROPOSTE_V11 = """
CREATE TABLE proposte (
    id TEXT PRIMARY KEY, creata_ts REAL NOT NULL, aggiornata_ts REAL NOT NULL,
    stato TEXT NOT NULL, testo TEXT NOT NULL, perche TEXT NOT NULL,
    chi_applica TEXT NOT NULL, impronta TEXT NOT NULL, prova_json TEXT NOT NULL,
    giri_json TEXT NOT NULL, esito_ts REAL, esito_nota TEXT, stakes TEXT);
INSERT INTO proposte VALUES ('p1', 100.0, 300.0, 'fatta_fuori', 'Sposta la
lavatrice', 'il prelievo', 'tu', 'dev1|prelievo|None|1', '{"base": 19}', '[]',
300.0, 'fatto ieri sera', NULL);
PRAGMA user_version = 11;
"""


def test_le_tre_colonne_MAI_LETTE_escono_e_le_righe_restano(tmp_path):
    """Attori, strato 4, Task 4.6. `chi_applica` era una costante salvata (si
    scriveva sempre «tu», e la porta delle Proposte la sovrascrive con la
    sua, `handlers_constructions._both_queues`); `aggiornata_ts` ed
    `esito_ts` si scrivevano e nessuno le leggeva. Escono con la tabella
    ricostruita, non con `DROP COLUMN`: la versione di SQLite dell'immagine
    non e' stata misurata, e la ricostruzione funziona su tutte.

    Mutazione ESEGUITA: la migrazione che ricopia le righe senza `esito_nota`
    -- rossa sulla nota."""
    import sqlite3

    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(_PROPOSTE_V11)
    conn.close()

    store = ObservationsStore(path)
    try:
        colonne = {r[1] for r in store._conn.execute("PRAGMA table_info(proposte)")}
        righe = store.proposals()
    finally:
        store.close()

    assert not colonne & {"chi_applica", "aggiornata_ts", "esito_ts"}, colonne
    assert len(righe) == 1
    assert righe[0]["id"] == "p1" and righe[0]["stato"] == "fatta_fuori"
    assert righe[0]["esito_nota"] == "fatto ieri sera"
    assert righe[0]["prova"] == {"base": 19}
    assert righe[0]["creata_ts"] == 100.0


def test_una_ricostruzione_INTERROTTA_non_perde_le_proposte(tmp_path, monkeypatch):
    """Revisione indipendente, giro 14 (G14-1). La ricostruzione si ferma a
    meta' -- qui la copia delle righe fallisce, perche' chiede una colonna che
    la tabella vecchia non ha -- e l'archivio deve restare com'era: alla
    versione 11, con le sue righe in `proposte`, senza `proposte_v11`. Al
    prossimo avvio la migrazione si rifa' e riesce.

    Mutazione ESEGUITA (06/10/2026): tolti `BEGIN` e `rollback` dalla
    migrazione -- rossa, perche' `proposte` resta vuota e le righe stanno in
    `proposte_v11`."""
    import sqlite3

    from hiris.app.mind import store as store_module

    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(_PROPOSTE_V11)
    conn.close()

    monkeypatch.setattr(store_module, "_PROPOSAL_COLUMNS",
                        store_module._PROPOSAL_COLUMNS + ("colonna_fantasma",))
    with pytest.raises(sqlite3.OperationalError, match="colonna_fantasma"):
        ObservationsStore(path)

    conn = sqlite3.connect(path)
    try:
        tabelle = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        versione = conn.execute("PRAGMA user_version").fetchone()[0]
        righe = conn.execute("SELECT id, chi_applica FROM proposte").fetchall()
    finally:
        conn.close()
    assert "proposte_v11" not in tabelle, tabelle
    assert versione == 11
    assert righe == [("p1", "tu")]

    monkeypatch.undo()
    store = ObservationsStore(path)
    try:
        assert [p["id"] for p in store.proposals()] == ["p1"]
    finally:
        store.close()
