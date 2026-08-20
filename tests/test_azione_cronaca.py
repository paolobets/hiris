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
