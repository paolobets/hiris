import sqlite3

import pytest

from hiris.app.memory.store import MemoryStore

_PHRASE = "d'inverno la sala da pranzo la preferisco fra 19 e 20 gradi quando sono a casa"


@pytest.fixture
def memory(tmp_path):
    m = MemoryStore(str(tmp_path / "memoria.db"))
    yield m
    m.close()


def test_un_ricordo_nudo_si_salva_e_si_rilegge(memory):
    """Regola 3: la struttura e' opzionale. Una frase senza interpretazione
    resta un ricordo intero, non un ricordo a meta'."""
    memory.remember("il modulo meteo esterno e' guasto", detto_da="paolo")
    memories = memory.fetch()
    assert memories[0]["testo"] == "il modulo meteo esterno e' guasto"
    assert memories[0]["detto_da"] == "paolo"
    assert memories[0]["ancore"] == []
    assert memories[0]["condizioni"] == []
    assert memories[0]["forza"] is None


def test_said_by_si_scrive_e_si_rilegge_da_fetch_e_get(memory):
    """Task 6: `said_by` e' una colonna vera, non un derivato -- scritta da
    `remember()`, letta identica da `fetch()` E da `get()` (fondamenta 3)."""
    ident = memory.remember("ho freddo", detto_da="Paolo", said_by="persona:p")
    assert memory.fetch()[0]["said_by"] == "persona:p"
    assert memory.get(ident)["said_by"] == "persona:p"


def test_said_by_di_default_e_none_come_detto_da(memory):
    """Nessun soggetto -> nessuna identita' inventata."""
    ident = memory.remember("la caldaia fa rumore")
    ricordo = memory.get(ident)
    assert ricordo["detto_da"] is None
    assert ricordo["said_by"] is None


def test_migrazione_v1_aggiunge_said_by_e_conserva_le_righe(tmp_path):
    """Un archivio v1 vero (prima di questo task, senza `said_by`): la
    migrazione aggiunge la colonna con un `ALTER TABLE`, senza toccare le
    righe gia' scritte -- stessa disciplina di
    `test_chat_store.py::test_migrazione_v3_conserva_le_righe_come_orfane...`."""
    db = str(tmp_path / "m.db")
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE ricordi (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          testo TEXT NOT NULL,
          detto_da TEXT,
          detto_il TEXT NOT NULL,
          forza TEXT,
          grandezza TEXT,
          minimo REAL,
          massimo REAL,
          unita TEXT,
          corretto_da_utente INTEGER NOT NULL DEFAULT 0
      );
      INSERT INTO ricordi (testo, detto_da, detto_il) VALUES
          ('un ricordo di prima', 'paolo', '2026-09-01T00:00:00Z');
      PRAGMA user_version=1;
    """)
    c.close()

    m = MemoryStore(db)
    try:
        memories = m.fetch()
        assert memories[0]["testo"] == "un ricordo di prima"
        assert memories[0]["detto_da"] == "paolo"
        assert memories[0]["said_by"] is None
        assert m._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        m.close()


def test_migrazione_v1_con_said_by_gia_presente_si_apre(tmp_path):
    """Un archivio che dichiara v1 ma ha GIA' `said_by` (migrazione
    interrotta dopo l'ALTER, prima del bump): senza la guardia su
    `PRAGMA table_info` l'apertura fallirebbe con «duplicate column»."""
    db = str(tmp_path / "m.db")
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE ricordi (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          testo TEXT NOT NULL,
          detto_da TEXT,
          detto_il TEXT NOT NULL,
          forza TEXT,
          grandezza TEXT,
          minimo REAL,
          massimo REAL,
          unita TEXT,
          corretto_da_utente INTEGER NOT NULL DEFAULT 0,
          said_by TEXT
      );
      INSERT INTO ricordi (testo, detto_da, detto_il, said_by) VALUES
          ('un ricordo di prima', 'paolo', '2026-09-01T00:00:00Z', 'persona:p');
      PRAGMA user_version=1;
    """)
    c.close()

    m = MemoryStore(db)
    try:
        assert m.fetch()[0]["said_by"] == "persona:p"
        assert m._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        m.close()


def test_un_ricordo_interpretato_conserva_tutto(memory):
    memory.remember(
        _PHRASE, detto_da="paolo",
        ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala da pranzo"}],
        conditions=[{"tipo": "stagione", "valore": "inverno"},
                    {"tipo": "presenza", "valore": "casa"}],
        modality="preferenza", grandezza="temperature", minimum=19.0, maximum=20.0, unit="°C",
    )
    r = memory.fetch()[0]
    assert r["testo"] == _PHRASE                      # regola 1: il testo e' la verita'
    assert r["forza"] == "preferenza"
    assert (r["minimo"], r["massimo"], r["unita"]) == (19.0, 20.0, "°C")
    assert [a["riferimento"] for a in r["ancore"]] == ["sala_pranzo"]
    assert {c["tipo"] for c in r["condizioni"]} == {"stagione", "presenza"}


def test_si_trovano_i_ricordi_di_una_parte_della_casa(memory):
    """«Quali preferenze riguardano la sala da pranzo?» deve avere risposta:
    e' il punto per cui le ancore esistono."""
    memory.remember(_PHRASE, detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}])
    memory.remember("in cucina niente luci dopo le 23", detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "cucina", "nome_visto": "cucina"}])
    assert [r["testo"] for r in memory.per_tether("area", "sala_pranzo")] == [_PHRASE]


def test_correggere_l_interpretazione_non_tocca_il_testo(memory):
    """Regola 2: si corregge cio' che HIRIS ha capito, lasciando la frase
    intatta. Il testo e' la verita' e non lo riscrive nessuno."""
    ident = memory.remember(_PHRASE, detto_da="paolo", modality="fatto", maximum=25.0)
    memory.correggi(ident, forza="preferenza", massimo=20.0)
    r = memory.fetch()[0]
    assert r["testo"] == _PHRASE
    assert r["forza"] == "preferenza"
    assert r["massimo"] == 20.0
    assert r["corretto_da_utente"] == 1


def test_correggere_le_ancore_le_sostituisce_tutte(memory):
    ident = memory.remember(_PHRASE, detto_da="paolo",
                            ancore=[{"tipo": "area", "riferimento": "sbagliata",
                                     "nome_visto": "sala"}])
    memory.correggi(ident, ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                                     "nome_visto": "sala da pranzo"}])
    assert [a["riferimento"] for a in memory.fetch()[0]["ancore"]] == ["sala_pranzo"]


def test_dimenticare_toglie_anche_ancore_e_condizioni(memory):
    ident = memory.remember(_PHRASE, detto_da="paolo",
                            ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                                     "nome_visto": "sala"}],
                            conditions=[{"tipo": "stagione", "valore": "inverno"}])
    memory.dimentica(ident)
    assert memory.fetch() == []
    assert memory.per_tether("area", "sala_pranzo") == []


def test_la_memoria_non_evapora(memory):
    """Contratto §1: niente scadenza. Non esiste nessun campo che la faccia
    sparire, e questo test esiste perche' nella 1.x c'era e ha fatto danni.

    Negare due nomi di colonna esatti (`valid_until`, `scade_il`) lo
    lascerebbe passare una terza colonna di scadenza con un altro nome
    (`expires_at`, per esempio): qui si nega qualunque colonna il cui nome
    SUGGERISCA una scadenza, non solo le due gia' viste."""
    memory.remember("una cosa vecchissima", detto_da="paolo")
    colonne = {r[1] for r in memory._conn.execute("PRAGMA table_info(ricordi)")}
    parole_di_scadenza = ("scad", "expir", "ttl", "valid_until", "valid_from", "valid_to")
    sospette = {c for c in colonne if any(p in c.lower() for p in parole_di_scadenza)}
    assert not sospette, f"colonna che sa di scadenza: {sospette}"
    assert len(memory.fetch()) == 1


def test_correggere_un_id_inesistente_dice_di_no(memory):
    """`correggi()` deve poter distinguere "ho corretto" da "non c'era
    niente da correggere": il chiamante (handlers_memory.py) risponde 404
    su questo `False`, non 200 `ok: true` su un ricordo che non esiste."""
    assert memory.correggi(9999, forza="preferenza") is False


def test_correggere_un_id_esistente_dice_di_si(memory):
    ident = memory.remember("mi piace il caffe'", detto_da="paolo")
    assert memory.correggi(ident, forza="preferenza") is True


def test_ottieni_un_id_inesistente_e_none(memory):
    assert memory.get(9999) is None


def test_ottieni_restituisce_il_ricordo_intero(memory):
    ident = memory.remember(_PHRASE, detto_da="paolo",
                            ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                                     "nome_visto": "sala"}],
                            modality="fatto", minimum=19.0, maximum=20.0)
    r = memory.get(ident)
    assert r["testo"] == _PHRASE
    assert r["forza"] == "fatto"
    assert (r["minimo"], r["massimo"]) == (19.0, 20.0)
    assert [a["riferimento"] for a in r["ancore"]] == ["sala_pranzo"]


def test_conta_i_ricordi(memory):
    assert memory.count() == 0
    memory.remember("prima", detto_da="paolo")
    memory.remember("seconda", detto_da="paolo")
    assert memory.count() == 2
    assert memory.count() == len(memory.fetch(limit=200))


def test_per_ancora_distingue_il_tipo(memory):
    """Il contratto di un'ancora e' la coppia tipo+riferimento (stessa
    forma di `Lookup.verify()`): un riferimento identico con tipo
    diverso (un'entita' e un'area con lo stesso id letterale) non deve
    mescolarsi."""
    memory.remember("preferenza sull'area", detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "x", "nome_visto": "x"}])
    memory.remember("preferenza sull'entita'", detto_da="paolo",
                    ancore=[{"tipo": "entita", "riferimento": "x", "nome_visto": "x"}])
    assert [r["testo"] for r in memory.per_tether("area", "x")] == ["preferenza sull'area"]
    assert [r["testo"] for r in memory.per_tether("entita", "x")] == ["preferenza sull'entita'"]


def test_un_salvataggio_a_meta_non_lascia_un_ricordo_monco(memory):
    memory.remember("prima frase", detto_da="paolo")
    with pytest.raises(KeyError):
        memory.remember("seconda", detto_da="paolo",
                        ancore=[{"tipo": "area"}])       # manca `riferimento`
    assert [r["testo"] for r in memory.fetch()] == ["prima frase"]
