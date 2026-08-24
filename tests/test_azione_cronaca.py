"""Il registro delle esecuzioni: una riga leggibile, per ogni origine."""
import os

import pytest

from hiris.app.azione.cronaca import Cronaca

ADESSO = 1_755_600_000.0


@pytest.fixture()
def cronaca(tmp_path):
    c = Cronaca(os.path.join(str(tmp_path), "azioni.db"))
    yield c
    c.close()


def test_una_riga_riuscita_si_rilegge_intera(cronaca):
    ident = cronaca.registra(
        origine="chat", servizio="light.turn_on", entita=["light.studio"],
        eseguito=True, cambiato=["light.studio"], adesso=ADESSO)
    riga = cronaca.leggi(ident)
    assert riga["origine"] == "chat"
    assert riga["servizio"] == "light.turn_on"
    assert riga["entita"] == ["light.studio"]
    assert riga["eseguito"] is True
    assert riga["cambiato"] == ["light.studio"]


def test_una_riga_fallita_porta_il_motivo(cronaca):
    ident = cronaca.registra(
        origine="schedulatore", servizio="cover.open_cover", entita=["cover.x"],
        eseguito=False, errore="Home Assistant ha rifiutato la chiamata: 500",
        adesso=ADESSO)
    riga = cronaca.leggi(ident)
    assert riga["eseguito"] is False
    assert "500" in riga["errore"]


def test_le_righe_vecchie_si_potano_alla_scrittura(cronaca):
    vecchia = cronaca.registra(origine="chat", servizio="a.b", entita=[],
                               eseguito=True, adesso=ADESSO)
    cronaca.registra(origine="chat", servizio="c.d", entita=[], eseguito=True,
                     adesso=ADESSO + 91 * 86400)
    assert cronaca.leggi(vecchia) is None


# -- le costruzioni: stessa tabella, `genere` a dire come si legge la riga ----

def test_una_costruzione_si_registra_nella_stessa_cronaca(cronaca):
    ident = cronaca.registra_costruzione(
        origine="chat", gesto="crea", dominio="automation", chiave="1771",
        entita=["automation.tapparelle_all_alba"], eseguito=True, adesso=ADESSO)
    riga = cronaca.leggi(ident)
    assert riga["genere"] == "costruzione"
    assert riga["oggetto"] == "automation.1771"
    assert riga["servizio"] == "automation.crea"
    assert riga["entita"] == ["automation.tapparelle_all_alba"]
    assert riga["eseguito"] is True


def test_un_comando_resta_di_genere_comando(cronaca):
    ident = cronaca.registra(origine="chat", servizio="light.turn_on",
                             entita=["light.studio"], eseguito=True, adesso=ADESSO)
    riga = cronaca.leggi(ident)
    assert riga["genere"] == "comando"
    assert riga["oggetto"] is None


def test_una_costruzione_fallita_porta_il_motivo_di_home_assistant(cronaca):
    ident = cronaca.registra_costruzione(
        origine="chat", gesto="modifica", dominio="script", chiave="buonanotte",
        entita=[], eseguito=False, adesso=ADESSO,
        errore="Message malformed: extra keys not allowed @ data['azioni']")
    assert cronaca.leggi(ident)["eseguito"] is False
    assert "malformed" in cronaca.leggi(ident)["errore"]


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

    c = Cronaca(percorso)
    try:
        riga = c.leggi("vecchia")
        assert riga is not None
        assert riga["genere"] == "comando"
        assert riga["servizio"] == "light.turn_on"
    finally:
        c.close()


# -- elenca: la cronaca diventa interrogabile nel tempo ---------------------

def test_elenca_restituisce_solo_la_finestra_chiesta(cronaca):
    cronaca.registra(origine="chat", servizio="light.turn_on",
                     entita=["light.cucina"], eseguito=True, adesso=1000.0)
    cronaca.registra(origine="chat", servizio="light.turn_off",
                     entita=["light.cucina"], eseguito=True, adesso=5000.0)
    righe = cronaca.elenca(da_ts=4000.0, a_ts=6000.0)
    assert [r["servizio"] for r in righe] == ["light.turn_off"]


def test_elenca_torna_dalla_piu_recente(cronaca):
    for ts in (1000.0, 2000.0, 3000.0):
        cronaca.registra(origine="chat", servizio=f"light.s{int(ts)}",
                         entita=["light.cucina"], eseguito=True, adesso=ts)
    righe = cronaca.elenca(da_ts=0.0, a_ts=9999.0)
    assert [r["quando_ts"] for r in righe] == [3000.0, 2000.0, 1000.0]


def test_elenca_filtra_per_entita_senza_confondere_i_prefissi(cronaca):
    """`light.cucina` e `light.cucina_2` sono due entita' diverse. Un filtro
    per sottostringa le confonderebbe -- ed e' il motivo per cui il confronto
    avviene sulla lista DECODIFICATA, non sul JSON grezzo."""
    cronaca.registra(origine="chat", servizio="light.turn_on",
                     entita=["light.cucina"], eseguito=True, adesso=1000.0)
    cronaca.registra(origine="chat", servizio="light.turn_on",
                     entita=["light.cucina_2"], eseguito=True, adesso=2000.0)
    righe = cronaca.elenca(da_ts=0.0, a_ts=9999.0, entita="light.cucina")
    assert len(righe) == 1
    assert righe[0]["entita"] == ["light.cucina"]


def test_elenca_vede_anche_le_costruzioni(cronaca):
    """Una tabella sola perche' la domanda dell'utente e' una sola -- «cosa hai
    fatto?». Un `elenca` che vedesse solo i comandi avrebbe reintrodotto la
    divisione che `registra_costruzione` ha evitato."""
    cronaca.registra_costruzione(origine="chat", gesto="crea", dominio="automation",
                                 chiave="abc", entita=["automation.sveglia"],
                                 eseguito=True, adesso=1000.0)
    righe = cronaca.elenca(da_ts=0.0, a_ts=9999.0)
    assert righe[0]["genere"] == "costruzione"
    assert righe[0]["oggetto"] == "automation.abc"


def test_elenca_ha_un_tetto(cronaca):
    for i in range(300):
        cronaca.registra(origine="chat", servizio="light.turn_on",
                         entita=["light.cucina"], eseguito=True, adesso=float(i))
    assert len(cronaca.elenca(da_ts=0.0, a_ts=9999.0)) == 200
    assert len(cronaca.elenca(da_ts=0.0, a_ts=9999.0, limite=10)) == 10
