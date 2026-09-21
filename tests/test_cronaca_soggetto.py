"""La cronaca impara a dire CHI (spec 2026-09-21 §11).

`origine` dice da quale **porta** e' passato un atto -- «chat», «pagina»,
«schedulatore» -- e sono nomi di pezzi di codice, non di persone. Con questa
colonna accanto, «chi ha spento la luce» ha una risposta: prima non ce l'aveva
ne' in HIRIS ne' nel registro di Home Assistant, che vede tutte le azioni
dell'add-on come lo stesso soggetto di sistema.

**Una colonna sola per tutte e quattro le specie.** Una persona di HA, un luogo
(un pannello, un altoparlante), un'integrazione, o nessuno: se avessero una
colonna per specie, la prima domanda di ogni lettore sarebbe «in quale guardo?»
-- e la seconda sarebbe sbagliata.
"""
import pytest

from hiris.app.action.journal import Journal

_PERSONA = {"specie": "persona", "id": "u-42", "nome": "Paolo",
            "ruolo": "amministratore"}
_LUOGO = {"specie": "luogo", "id": "retropanel", "nome": "Retro Panel",
          "ruolo": "utente"}


@pytest.fixture()
def cronaca(tmp_path):
    archivio = Journal(str(tmp_path / "atti.db"))
    try:
        yield archivio
    finally:
        archivio.close()


def test_un_comando_registra_chi_lo_ha_chiesto(cronaca):
    """Mutazione: scrivere solo `origine` -- rossa (la cronaca tornerebbe a
    dire da quale porta e non chi)."""
    cronaca.log(actor="chat", service="light.turn_on", entity=["light.cucina"],
                executed=True, now=100.0, subject=_PERSONA)

    riga = cronaca.list(from_ts=0, to_ts=200)[0]
    assert riga["origine"] == "chat"
    assert riga["soggetto"]["id"] == "u-42"
    assert riga["soggetto"]["nome"] == "Paolo"


def test_anche_un_LUOGO_si_registra(cronaca):
    """Un pannello in corridoio non e' una persona e non e' una macchina: se la
    cronaca sapesse registrare solo le persone, ogni atto da un pannello
    risulterebbe «di nessuno».

    Mutazione: tenere solo l'identificatore e perdere la specie -- rossa."""
    cronaca.log(actor="chat", service="light.turn_off", entity=["light.x"],
                executed=True, now=100.0, subject=_LUOGO)

    assert cronaca.list(from_ts=0, to_ts=200)[0]["soggetto"]["specie"] == "luogo"


def test_un_atto_SENZA_soggetto_si_distingue_da_uno_con_soggetto_ignoto(cronaca):
    """Lo schedulatore agisce per conto di HIRIS: non c'e' nessuno, ed e'
    diverso da «c'era qualcuno e non so chi».

    Mutazione: scrivere un dizionario vuoto invece di niente -- rossa (chi
    legge non distinguerebbe i due casi)."""
    cronaca.log(actor="schedulatore", service="cover.close_cover",
                entity=["cover.x"], executed=True, now=100.0)

    assert cronaca.list(from_ts=0, to_ts=200)[0]["soggetto"] is None


def test_anche_una_COSTRUZIONE_registra_il_soggetto(cronaca):
    """Costruire e' l'atto piu' delicato del prodotto: se la cronaca dicesse
    chi ha acceso una luce ma non chi ha scritto un'automazione, direbbe il
    meno e tacerebbe il piu'.

    Mutazione: passare il soggetto solo ai comandi -- rossa."""
    cronaca.log_construction(actor="pagina", operation="create",
                             domain="automation", key="a1", entity=[],
                             executed=True, now=100.0, subject=_PERSONA)

    assert cronaca.list(from_ts=0, to_ts=200)[0]["soggetto"]["id"] == "u-42"


def test_le_righe_gia_scritte_restano_leggibili(tmp_path):
    """La migrazione aggiunge una colonna e non riscrive niente: una cronaca
    vera non si perde per un guadagno di forma. Le righe di ieri hanno
    `soggetto` a `None`, che e' cio' che sono: atti di cui non si sapeva chi.

    Mutazione ESEGUITA: ricostruire la tabella invece di aggiungere la colonna
    -- rossa (le righe scritte prima spariscono)."""
    percorso = str(tmp_path / "atti.db")
    vecchia = Journal(percorso)
    vecchia.log(actor="chat", service="light.turn_on", entity=["light.x"],
                executed=True, now=100.0)
    vecchia.close()

    riaperta = Journal(percorso)
    try:
        righe = riaperta.list(from_ts=0, to_ts=200)
        assert len(righe) == 1
        assert righe[0]["soggetto"] is None
    finally:
        riaperta.close()
