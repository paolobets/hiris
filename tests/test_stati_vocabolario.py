"""Il vocabolario degli stati (Tappa 8, G-19, C-54, M-76; D4 (a), decisa dal
proprietario l'08/10/2026).

Le tre code -- promesse, costruzioni, proposte da fare a mano -- dicono a che
punto e' una cosa con le parole di `hiris/app/states.py`, e ognuna ha la sua
frase leggibile. Queste prove **chiedono gli stati agli archivi**: li fanno
lavorare, transizione per transizione, e leggono dal disco cosa hanno
scritto. Un archivio che scrivesse una parola fuori dal vocabolario -- la
vecchia `attesa`, rimessa in una scrittura -- arrossisce qui, qualunque
costante abbia usato per farlo.

Le migrazioni portano le parole vecchie alle nuove, e si provano due volte:
un archivio alla versione di prima, con le righe come le scriveva allora, si
riapre migrato; una seconda apertura non cambia niente.
"""
import os
import sqlite3

import pytest

from hiris.app import states
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.chat_thread import ChatThread
from hiris.app.keeper.promise import STATES_CONCLUSI, STATES_ESITO
from hiris.app.keeper.store import AgendaStore
from hiris.app.mind.store import ObservationsStore
from hiris.app.steering import REFUSED
from hiris.app.usage.store import UsageStore

ADESSO = 1_791_400_000.0   # 07/10/2026: dopo la nascita del proponente
PAOLO = ChatThread("persona:paolo", "pannello")


def _distinct(path: str, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute(f"SELECT DISTINCT stato FROM {table}")}
    finally:
        conn.close()


def _dump(path: str) -> list:
    conn = sqlite3.connect(path)
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


# -- il vocabolario e' completo ------------------------------------------------

def test_ogni_stato_di_ogni_coda_ha_la_sua_frase():
    """Mutazione ESEGUITA (08/10/2026): uno stato nuovo aggiunto a
    `STATES_CONCLUSI` (e a `PROMISE_STATES`) senza la sua frase in `READABLE`
    -- rossa qui."""
    every = (set(states.PROMISE_STATES) | set(states.CONSTRUCTION_STATES)
             | set(states.PROPOSAL_STATES))
    for state in every:
        assert states.READABLE.get(state), f"«{state}» non ha la sua frase"
        assert states.readable(state) != state or " " not in state
    # E non ci sono frasi per stati che nessuna coda scrive.
    assert set(states.READABLE) == every


def test_le_costanti_delle_code_stanno_nel_vocabolario():
    assert set(STATES_CONCLUSI) | set(states.SUSPENDED) == set(states.PROMISE_STATES)
    assert set(STATES_ESITO) < set(STATES_CONCLUSI)
    proposals = (set(ObservationsStore.PROPOSAL_OUTCOMES)
                 | {ObservationsStore.PROPOSAL_AUTOMATED, states.PENDING})
    assert proposals == set(states.PROPOSAL_STATES)


def test_le_tre_tabelle_non_hanno_un_check_sullo_stato_che_il_vocabolario_non_veda(tmp_path):
    """Se uno schema vincolasse lo stato con un `CHECK`, i valori dovrebbero
    essere quelli del vocabolario. Oggi nessuna delle tre tabelle ne ha uno:
    lo si chiede allo schema, e il giorno che arriva questa prova lo vede."""
    tables = {"promesse": (AgendaStore, "promesse.db"),
              "costruzioni": (ConstructionStore, "costruzioni.db"),
              "proposte": (ObservationsStore, "osservazioni.db")}
    for table, (store_class, name) in tables.items():
        path = str(tmp_path / name)
        store_class(path).close()
        conn = sqlite3.connect(path)
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        conn.close()
        assert "stato" in sql
        assert "CHECK" not in sql.upper().split("STATO", 1)[1].split(",", 1)[0], (
            f"{table}: un CHECK sullo stato va legato al vocabolario")


# -- gli archivi scrivono solo parole del vocabolario -----------------------------

def test_le_promesse_scrivono_solo_parole_del_vocabolario(tmp_path):
    path = str(tmp_path / "promesse.db")
    store = AgendaStore(path)
    try:
        def nuova(n):
            return store.create({"specie": "fai", "frase": f"accendi {n}",
                                 "quando_ts": ADESSO + 3600 + n, "fuso": "Europe/Rome",
                                 "chiamata": {"servizio": "light.turn_on", "bersaglio": {}}},
                                thread=PAOLO, now=ADESSO)["promessa"]["id"]
        for n, state in enumerate(STATES_CONCLUSI):
            ident = nuova(n)
            assert store.prendi(ident, now=ADESSO + 1)
            assert store.concludi(ident, state=state, now=ADESSO + 2)
        store.cancel(nuova(10), thread=PAOLO, now=ADESSO)
        store.prendi(nuova(11), now=ADESSO)
        nuova(12)
        written = _distinct(path, "promesse")
        store.risana(now=ADESSO + 3)
        written |= _distinct(path, "promesse")
    finally:
        store.close()
    assert written == set(states.PROMISE_STATES), written


def test_le_costruzioni_scrivono_solo_parole_del_vocabolario(tmp_path):
    path = str(tmp_path / "costruzioni.db")
    store = ConstructionStore(path)

    def nuova(key, now=ADESSO):
        return store.propose(operation="crea", domain="automation", key=key, actor="chat",
                             exchange=None, phrase=None, prima=None, dopo={"alias": key},
                             helper=[], preview="", stakes=None, now=now)["id"]
    try:
        for key, mark in (("a", store.mark_applied), ("f", store.mark_failed),
                          ("u", store.mark_uncertain)):
            ident = nuova(key)
            store.claim(ident, now=ADESSO + 1)
            mark(ident, now=ADESSO + 2, execution_id=None)
        store.mark_cancelled(nuova("d"), now=ADESSO + 1)
        store.claim(nuova("c"), now=ADESSO + 1)
        written = _distinct(path, "costruzioni")
        store.risana(now=ADESSO + 3)
        # Una scaduta si segna alla prossima proposta.
        nuova("p", now=ADESSO)
        nuova("x", now=ADESSO + ConstructionStore.DEADLINE_S + 10)
        written |= _distinct(path, "costruzioni")
    finally:
        store.close()
    assert written == set(states.CONSTRUCTION_STATES), written


def test_le_proposte_scrivono_solo_parole_del_vocabolario(tmp_path):
    """Mutazione ESEGUITA (08/10/2026): `add_proposal` che scrive `'attesa'`
    al posto di `PENDING` -- rossa qui, gia' su `close_proposal`, che chiude
    solo cio' che e' `in_attesa` e trova la parola vecchia."""
    path = str(tmp_path / "osservazioni.db")
    store = ObservationsStore(path)
    try:
        def nuova(n):
            return store.add_proposal(text=f"t{n}", perche="p", fingerprint=f"f{n}",
                                      prova={}, stakes=None, now_ts=ADESSO + n)
        for n, outcome in enumerate(store.PROPOSAL_OUTCOMES):
            assert store.close_proposal(nuova(n), outcome)
        assert store.automate_proposal(nuova(7), "c1")
        nuova(8)
    finally:
        store.close()
    assert _distinct(path, "proposte") == set(states.PROPOSAL_STATES)


def test_il_no_su_una_proposta_e_la_disdetta_delle_altre_code(tmp_path):
    """D4 (a): la proposta che hai rifiutato si legge con la frase di
    `disdetta`, come la costruzione che hai declinato. `rifiutata` non e' piu'
    un esito ammesso: arriverebbe da una rotta come uno stato che nessuna
    pagina sa disegnare."""
    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        ident = store.add_proposal(text="t", perche="p", fingerprint="f", prova={},
                                   stakes=None, now_ts=ADESSO)
        with pytest.raises(ValueError):
            store.close_proposal(ident, "rifiutata")
        assert store.close_proposal(ident, states.CANCELLED)
        row = store.proposal(ident)
    finally:
        store.close()
    assert row["stato"] == "disdetta"
    assert row["stato_leggibile"] == states.readable("disdetta")


# -- le frasi arrivano a chi legge -------------------------------------------------

def test_disdire_una_promessa_gia_presa_dice_la_frase_non_la_parola(tmp_path):
    """C-54: fino all'08/10/2026 il modello riceveva «quella promessa e' gia'
    in_corso», e da li' una persona. Mutazione ESEGUITA (08/10/2026):
    `row["stato"]` al posto di `readable(row["stato"])` -- rossa."""
    store = AgendaStore(str(tmp_path / "promesse.db"))
    try:
        ident = store.create({"specie": "fai", "frase": "accendi", "quando_ts": ADESSO + 3600,
                              "fuso": "Europe/Rome",
                              "chiamata": {"servizio": "light.turn_on", "bersaglio": {}}},
                             thread=PAOLO, now=ADESSO)["promessa"]["id"]
        store.prendi(ident, now=ADESSO + 1)
        esito = store.cancel(ident, thread=PAOLO, now=ADESSO + 2)
    finally:
        store.close()
    assert "in_corso" not in esito["errore"]
    assert states.readable("in_corso") in esito["errore"]


def test_ogni_riga_porta_la_frase_del_suo_stato(tmp_path):
    """C-10: la pagina riceve la frase dalla rotta. Le tre code la portano
    con la stessa chiave, `stato_leggibile`, anche per una costruzione
    scaduta che nessuno ha ancora segnato (lo stato si calcola in lettura)."""
    agenda = AgendaStore(str(tmp_path / "promesse.db"))
    built = ConstructionStore(str(tmp_path / "costruzioni.db"))
    obs = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        promise = agenda.create({"specie": "fai", "frase": "x", "quando_ts": ADESSO + 60,
                                 "fuso": "Europe/Rome",
                                 "chiamata": {"servizio": "light.turn_on", "bersaglio": {}}},
                                thread=PAOLO, now=ADESSO)["promessa"]
        ident = built.propose(operation="crea", domain="automation", key="k", actor="chat",
                              exchange=None, phrase=None, prima=None, dopo={}, helper=[],
                              preview="", stakes=None, now=ADESSO)["id"]
        late = built.read(ident, now=ADESSO + ConstructionStore.DEADLINE_S + 1)
        obs.add_proposal(text="t", perche="p", fingerprint="f", prova={}, stakes=None,
                         now_ts=ADESSO)
        proposal = obs.proposals()[0]
    finally:
        agenda.close()
        built.close()
        obs.close()
    assert promise["stato_leggibile"] == states.readable("in_attesa")
    assert (late["stato"], late["stato_leggibile"]) == ("scaduta", states.readable("scaduta"))
    assert proposal["stato_leggibile"] == states.readable("in_attesa")


# -- le migrazioni ------------------------------------------------------------------

def test_la_migrazione_15_porta_le_parole_delle_proposte(tmp_path):
    """Un archivio alla 14 con le parole di allora (`attesa`, `rifiutata`)
    su proposte del proponente -- quelle dell'attuatore escono col passo
    prima -- si riapre con `in_attesa` e `disdetta`; la seconda apertura non
    cambia niente.

    Mutazione ESEGUITA (08/10/2026): il passo tolto da `_MIGRATION_15_STEPS`
    -- rossa: `attesa` resta, e la proposta non conta piu' fra quelle in
    attesa (`pending_proposals_count() == 0`)."""
    path = str(tmp_path / "osservazioni.db")
    store = ObservationsStore(path)
    waiting = store.add_proposal(text="a", perche="p", fingerprint="f1", prova={},
                                 stakes=None, now_ts=ADESSO)
    said_no = store.add_proposal(text="b", perche="p", fingerprint="f2", prova={},
                                 stakes=None, now_ts=ADESSO + 1)
    done = store.add_proposal(text="c", perche="p", fingerprint="f3", prova={},
                              stakes=None, now_ts=ADESSO + 2)
    store.close_proposal(done, states.DONE_ELSEWHERE)
    store._conn.execute("UPDATE proposte SET stato='attesa' WHERE id=?", (waiting,))
    store._conn.execute("UPDATE proposte SET stato='rifiutata' WHERE id=?", (said_no,))
    store._conn.execute("PRAGMA user_version = 14")
    store._conn.commit()
    store.close()

    store = ObservationsStore(path)
    try:
        by_id = {p["id"]: p["stato"] for p in store.proposals()}
        assert store.pending_proposals_count() == 1
    finally:
        store.close()
    assert by_id == {waiting: "in_attesa", said_no: "disdetta", done: "fatta_fuori"}
    first = _dump(path)
    ObservationsStore(path).close()
    assert _dump(path) == first


#: La forma di `costruzioni` e `avvisi` alla versione 6, com'era sul disco
#: fino all'08/10/2026: e' il fatto da riprodurre, non una copia di qualcosa
#: che vive altrove.
_V6 = """
CREATE TABLE costruzioni (
    id TEXT PRIMARY KEY, creata_ts REAL NOT NULL, aggiornata_ts REAL NOT NULL,
    stato TEXT NOT NULL, gesto TEXT NOT NULL, dominio TEXT NOT NULL,
    chiave TEXT NOT NULL, origine TEXT NOT NULL, turno TEXT, frase TEXT,
    prima_json TEXT, dopo_json TEXT, helper_json TEXT, anteprima TEXT,
    esecuzione_id TEXT, motivo TEXT, subject_key TEXT, entry_point TEXT,
    stakes TEXT, impronta TEXT, prova_json TEXT);
CREATE INDEX idx_costruzioni_stato ON costruzioni(stato, creata_ts DESC);
CREATE INDEX idx_costruzioni_oggetto ON costruzioni(dominio, chiave, creata_ts DESC);
CREATE TABLE avvisi (proposta_id TEXT PRIMARY KEY, avvisata_ts REAL NOT NULL);
PRAGMA user_version = 6;
"""


def _v6_row(conn, ident, state, reason=None, ts=ADESSO):
    conn.execute(
        "INSERT INTO costruzioni(id,creata_ts,aggiornata_ts,stato,gesto,dominio,chiave,"
        "origine,turno,frase,prima_json,dopo_json,helper_json,anteprima,esecuzione_id,"
        "motivo,subject_key,entry_point,stakes,impronta,prova_json) "
        "VALUES(?,?,?,?,'crea','automation',?,'chat',NULL,'apri',NULL,'{}','[]','x',"
        "'e1',?,'persona:paolo','pannello','alto','imp','{}')",
        (ident, ts, ts + 5, state, ident, reason))


def test_la_migrazione_7_delle_costruzioni(tmp_path):
    """v6 -> v7: `rifiutata` (il guasto) diventa `fallita`, `incerta` resta;
    le disdette perdono i due motivi di allora, e solo quei due; escono
    `costruzioni.aggiornata_ts` e `avvisi.avvisata_ts`, con ogni riga e ogni
    altra colonna intatte. La seconda apertura non cambia niente.

    Mutazioni ESEGUITE (08/10/2026): senza l'`UPDATE` delle parole -- rossa
    su `rifiutata`; senza la ricostruzione -- rossa sulle colonne; senza
    `stato=?` nella pulizia dei motivi -- rossa su `guasto2` (N100-1)."""
    path = str(tmp_path / "costruzioni.db")
    conn = sqlite3.connect(path)
    conn.executescript(_V6)
    _v6_row(conn, "guasto", "rifiutata")
    _v6_row(conn, "dubbio", "incerta", "non so")
    _v6_row(conn, "no1", "disdetta", "rifiutata dalla pagina")
    _v6_row(conn, "no2", "disdetta", "rifiutata dal proprietario")
    _v6_row(conn, "no3", "disdetta", "un altro testo")
    # Uno dei due testi su una riga che NON e' una disdetta: resta (N100-1).
    _v6_row(conn, "guasto2", "fallita", "rifiutata dalla pagina")
    _v6_row(conn, "fatta", "applicata")
    _v6_row(conn, "aspetta", "in_attesa", ts=ADESSO + 9)
    conn.execute("INSERT INTO avvisi VALUES('aspetta', ?)", (ADESSO,))
    conn.commit()
    conn.close()

    store = ConstructionStore(path)
    try:
        rows = {r["id"]: r for r in store.list(now=ADESSO + 10)}
        alerted = store.to_alert(actor="chat", stakes="alto", now=ADESSO + 10)
    finally:
        store.close()
    assert {k: r["stato"] for k, r in rows.items()} == {
        "guasto": "fallita", "dubbio": "incerta", "no1": "disdetta", "no2": "disdetta",
        "no3": "disdetta", "guasto2": "fallita", "fatta": "applicata",
        "aspetta": "in_attesa"}
    assert [rows[k]["motivo"] for k in ("dubbio", "no1", "no2", "no3", "guasto2")] == [
        "non so", None, None, "un altro testo", "rifiutata dalla pagina"]
    assert rows["fatta"]["thread"] == PAOLO and rows["fatta"]["livello"] == "alto"
    assert alerted == [], "l'avviso gia' arrivato non si ripete"
    conn = sqlite3.connect(path)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(costruzioni)")}
    alerts = [r[1] for r in conn.execute("PRAGMA table_info(avvisi)")]
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='costruzioni'")}
    conn.close()
    assert "aggiornata_ts" not in columns and "stato" in columns
    assert alerts == ["proposta_id"]
    assert {"idx_costruzioni_stato", "idx_costruzioni_oggetto"} <= indexes
    first = _dump(path)
    ConstructionStore(path).close()
    assert _dump(path) == first


def _user_version(path: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_la_migrazione_7_delle_costruzioni_e_tutto_o_niente(tmp_path, monkeypatch):
    """Un guasto dopo il `RENAME`: l'archivio resta alla 6 con le sue righe
    in `costruzioni`, e senza guasto la migrazione si rifa' fino alla 7
    (rilievo G100-1, giro 100; lo stesso di G94-1 sulla 15 delle
    osservazioni). Il guasto e' l'`INSERT ... SELECT` che chiede una colonna
    che `costruzioni_v6` non ha: solleva dopo il `RENAME` e il `CREATE`.

    Mutazioni ESEGUITE (08/10/2026): senza il `rollback` -- rossa (la
    ricostruzione resta a meta' in una transazione aperta, e l'archivio e'
    bloccato: «database is locked»); senza il `BEGIN` e
    con la ricostruzione spostata prima degli `UPDATE` -- rossa, il DDL va in
    autocommit. Senza il solo `BEGIN` resta verde, ed e' giusto: l'`UPDATE`
    in testa apre gia' la transazione (il modulo `sqlite3` la apre prima di
    ogni DML), ed e' questa prova a fermare chi spostasse l'ordine."""
    from hiris.app.action.construction import revisions as modulo

    path = str(tmp_path / "costruzioni.db")
    conn = sqlite3.connect(path)
    conn.executescript(_V6)
    _v6_row(conn, "guasto", "rifiutata")
    _v6_row(conn, "fatta", "applicata")
    conn.execute("INSERT INTO avvisi VALUES('fatta', ?)", (ADESSO,))
    conn.commit()
    conn.close()
    before = _dump(path)

    monkeypatch.setattr(modulo, "_CONSTRUCTION_COLUMNS",
                        (*modulo._CONSTRUCTION_COLUMNS, "colonna_fantasma"))
    with pytest.raises(sqlite3.OperationalError, match="colonna_fantasma"):
        ConstructionStore(path)
    assert _dump(path) == before
    assert _user_version(path) == 6

    monkeypatch.undo()
    store = ConstructionStore(path)
    try:
        states_by_id = {r["id"]: r["stato"] for r in store.list(now=ADESSO + 10)}
    finally:
        store.close()
    assert states_by_id == {"guasto": "fallita", "fatta": "applicata"}
    assert _user_version(path) == 7


def test_la_migrazione_6_dei_consumi_porta_l_esito_scartato(tmp_path):
    """L'esito di un turno che il mestiere ha scartato: «rifiutata» fino
    all'08/10/2026, `steering.REFUSED` («scartato») dopo. Il giro dopo lo
    rilegge (`steering.refused_problems`): una riga con la parola vecchia
    sarebbe un turno scartato che nessuno riconosce."""
    path = str(tmp_path / "consumi.db")
    store = UsageStore(path)
    kept = store.log_turn(species="analista", provider="claude", model="m", channel="catena",
                          duration_ms=1, iterations=1, tools=[], outcome="riuscito",
                          now=ADESSO)
    old = store.log_turn(species="analista", provider="claude", model="m", channel="catena",
                         duration_ms=1, iterations=1, tools=[], outcome="riuscito",
                         now=ADESSO + 1)
    store._conn.execute("UPDATE turn SET outcome='rifiutata' WHERE id=?", (old,))
    store._conn.execute("PRAGMA user_version = 5")
    store._conn.commit()
    store.close()

    store = UsageStore(path)
    try:
        outcomes = {t["id"]: t["outcome"] for t in store.turns()}
    finally:
        store.close()
    assert outcomes == {kept: "riuscito", old: REFUSED}
    assert REFUSED == "scartato"
    first = _dump(path)
    UsageStore(path).close()
    assert _dump(path) == first


def test_un_archivio_nuovo_nasce_alla_versione_delle_migrazioni(tmp_path):
    for store_class, name, version in ((ConstructionStore, "c.db", 7),
                                       (UsageStore, "u.db", 6)):
        path = os.path.join(str(tmp_path), name)
        store_class(path).close()
        conn = sqlite3.connect(path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
        conn.close()
