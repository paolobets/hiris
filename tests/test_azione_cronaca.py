"""Il registro delle esecuzioni: una riga leggibile, per ogni origine."""
import os

import pytest

from hiris.app.azione.cronaca import Journal

ADESSO = 1_755_600_000.0


@pytest.fixture()
def cronaca(tmp_path):
    c = Journal(os.path.join(str(tmp_path), "azioni.db"))
    yield c
    c.close()


def test_una_riga_riuscita_si_rilegge_intera(cronaca):
    ident = cronaca.log(
        actor="chat", service="light.turn_on", entity=["light.studio"],
        eseguito=True, cambiato=["light.studio"], now=ADESSO)
    riga = cronaca.read(ident)
    assert riga["origine"] == "chat"
    assert riga["servizio"] == "light.turn_on"
    assert riga["entita"] == ["light.studio"]
    assert riga["eseguito"] is True
    assert riga["cambiato"] == ["light.studio"]


def test_una_riga_fallita_porta_il_motivo(cronaca):
    ident = cronaca.log(
        actor="schedulatore", service="cover.open_cover", entity=["cover.x"],
        eseguito=False, error="Home Assistant ha rifiutato la chiamata: 500",
        now=ADESSO)
    riga = cronaca.read(ident)
    assert riga["eseguito"] is False
    assert "500" in riga["errore"]


def test_le_righe_vecchie_si_potano_alla_scrittura(cronaca):
    vecchia = cronaca.log(actor="chat", service="a.b", entity=[],
                               eseguito=True, now=ADESSO)
    cronaca.log(actor="chat", service="c.d", entity=[], eseguito=True,
                     now=ADESSO + 91 * 86400)
    assert cronaca.read(vecchia) is None


# -- le costruzioni: stessa tabella, `genere` a dire come si legge la riga ----

def test_una_costruzione_si_registra_nella_stessa_cronaca(cronaca):
    ident = cronaca.log_construction(
        actor="chat", operation="crea", domain="automation", key="1771",
        entity=["automation.tapparelle_all_alba"], eseguito=True, now=ADESSO)
    riga = cronaca.read(ident)
    assert riga["genere"] == "costruzione"
    assert riga["oggetto"] == "automation.1771"
    assert riga["servizio"] == "automation.crea"
    assert riga["entita"] == ["automation.tapparelle_all_alba"]
    assert riga["eseguito"] is True


def test_un_comando_resta_di_genere_comando(cronaca):
    ident = cronaca.log(actor="chat", service="light.turn_on",
                             entity=["light.studio"], eseguito=True, now=ADESSO)
    riga = cronaca.read(ident)
    assert riga["genere"] == "comando"
    assert riga["oggetto"] is None


def test_una_costruzione_fallita_porta_il_motivo_di_home_assistant(cronaca):
    ident = cronaca.log_construction(
        actor="chat", operation="modifica", domain="script", key="buonanotte",
        entity=[], eseguito=False, now=ADESSO,
        error="Message malformed: extra keys not allowed @ data['azioni']")
    assert cronaca.read(ident)["eseguito"] is False
    assert "malformed" in cronaca.read(ident)["errore"]


def test_un_archivio_vecchio_si_migra_senza_perdere_le_righe(tmp_path):
    """Una cronaca gia' scritta dalla versione precedente deve continuare a
    rileggersi: la migrazione aggiunge colonne, non riscrive la tabella."""
    import sqlite3
    percorso = os.path.join(str(tmp_path), "azioni.db")
    conn = sqlite3.connect(percorso)
    conn.executescript(
        "CREATE TABLE esecuzioni (id TEXT PRIMARY KEY, quando_ts REAL NOT NULL,"
        " origine TEXT NOT NULL, servizio TEXT NOT NULL, entita_json TEXT NOT NULL,"
        " eseguito INTEGER NOT NULL, cambiato_json TEXT, errore TEXT, avviso TEXT);")
    conn.execute("INSERT INTO esecuzioni VALUES('vecchia',?,'chat','light.turn_on',"
                 "'[\"light.x\"]',1,NULL,NULL,NULL)", (ADESSO,))
    conn.commit()
    conn.close()

    c = Journal(percorso)
    try:
        riga = c.read("vecchia")
        assert riga is not None
        assert riga["genere"] == "comando"
        assert riga["servizio"] == "light.turn_on"
    finally:
        c.close()


# -- elenca: la cronaca diventa interrogabile nel tempo ---------------------

def test_elenca_restituisce_solo_la_finestra_chiesta(cronaca):
    cronaca.log(actor="chat", service="light.turn_on",
                     entity=["light.cucina"], eseguito=True, now=1000.0)
    cronaca.log(actor="chat", service="light.turn_off",
                     entity=["light.cucina"], eseguito=True, now=5000.0)
    righe = cronaca.list(da_ts=4000.0, a_ts=6000.0)
    assert [r["servizio"] for r in righe] == ["light.turn_off"]


def test_elenca_torna_dalla_piu_recente(cronaca):
    for ts in (1000.0, 2000.0, 3000.0):
        cronaca.log(actor="chat", service=f"light.s{int(ts)}",
                         entity=["light.cucina"], eseguito=True, now=ts)
    righe = cronaca.list(da_ts=0.0, a_ts=9999.0)
    assert [r["quando_ts"] for r in righe] == [3000.0, 2000.0, 1000.0]


def test_elenca_filtra_per_entita_senza_confondere_i_prefissi(cronaca):
    """`light.cucina` e `light.cucina_2` sono due entita' diverse. Un filtro
    per sottostringa le confonderebbe -- ed e' il motivo per cui il confronto
    avviene sulla lista DECODIFICATA, non sul JSON grezzo."""
    cronaca.log(actor="chat", service="light.turn_on",
                     entity=["light.cucina"], eseguito=True, now=1000.0)
    cronaca.log(actor="chat", service="light.turn_on",
                     entity=["light.cucina_2"], eseguito=True, now=2000.0)
    righe = cronaca.list(da_ts=0.0, a_ts=9999.0, entity="light.cucina")
    assert len(righe) == 1
    assert righe[0]["entita"] == ["light.cucina"]


def test_elenca_vede_anche_le_costruzioni(cronaca):
    """Una tabella sola perche' la domanda dell'utente e' una sola -- «cosa hai
    fatto?». Un `elenca` che vedesse solo i comandi avrebbe reintrodotto la
    divisione che `registra_costruzione` ha evitato."""
    cronaca.log_construction(actor="chat", operation="crea", domain="automation",
                                 key="abc", entity=["automation.sveglia"],
                                 eseguito=True, now=1000.0)
    righe = cronaca.list(da_ts=0.0, a_ts=9999.0)
    assert righe[0]["genere"] == "costruzione"
    assert righe[0]["oggetto"] == "automation.abc"


def test_elenca_ha_un_tetto(cronaca):
    for i in range(300):
        cronaca.log(actor="chat", service="light.turn_on",
                         entity=["light.cucina"], eseguito=True, now=float(i))
    assert len(cronaca.list(da_ts=0.0, a_ts=9999.0)) == 200
    assert len(cronaca.list(da_ts=0.0, a_ts=9999.0, limit=10)) == 10


def test_elenca_moltiplica_il_limite_per_10_con_filtro_entita(cronaca):
    """Il LIMIT di SQL non puo' essere il risultato finale quando filtra per
    entita'. Registriamo piu' di `limite` righe ma meno di `limite*10` di
    un'altra entita' (tutte piu' recenti), poi una riga dell'entita' cercata
    piu' indietro. Senza il moltiplicatore per 10, la query leggerebbe solo
    `limite` righe e non vedrebbe la riga che cerchiamo."""
    # Registra 99 righe di light.cucina_2 con timestamp 1000-1098
    for i in range(99):
        cronaca.log(actor="chat", service="light.turn_on",
                         entity=["light.cucina_2"], eseguito=True, now=float(1000 + i))
    # Registra una riga di light.cucina con timestamp 999 (piu' indietro ma
    # entro i 100 risultati del LIMIT moltiplicato per 10)
    cronaca.log(actor="chat", service="light.turn_on",
                     entity=["light.cucina"], eseguito=True, now=999.0)
    # Con limit=10 e moltiplicazione per 10, leggiamo 100 righe e troviamo
    # la riga di light.cucina. Senza il moltiplicatore (solo 10 righe),
    # vedremmo solo le ultime 10 di light.cucina_2.
    righe = cronaca.list(da_ts=0.0, a_ts=9999.0, entity="light.cucina", limit=10)
    assert len(righe) == 1
    assert righe[0]["quando_ts"] == 999.0


def test_elenca_il_moltiplicatore_ha_un_confine(cronaca):
    """Il moltiplicatore per 10 NON risolve il problema, lo sposta. Se piu'
    di `limite*10` righe piu' recenti nella finestra non appartengono
    all'entita' richiesta, il risultato puo' essere ancora vuoto pur
    avendone. Questo test documenta il confine: con 2100 righe di un'altra
    entita' e limit=10 (tetto 100), la riga cercata resta fuori."""
    # Registra 2100 righe di light.cucina_2 con timestamp 100-2199
    for i in range(2100):
        cronaca.log(actor="chat", service="light.turn_on",
                         entity=["light.cucina_2"], eseguito=True, now=float(100 + i))
    # Registra una riga di light.cucina con timestamp 50 (piu' indietro)
    cronaca.log(actor="chat", service="light.turn_on",
                     entity=["light.cucina"], eseguito=True, now=50.0)
    # Con limit=10 e moltiplicazione per 10, leggiamo 100 righe, tutte di
    # light.cucina_2. La riga di light.cucina non entra nel risultato.
    righe = cronaca.list(da_ts=0.0, a_ts=9999.0, entity="light.cucina", limit=10)
    assert len(righe) == 0  # La riga e' fuori dal tetto di lettura
