"""La riga del comportamento nel nucleo dice «senza corpo» con la regola
dell'avviso e di `/api/home-space` (`behavior.without_body`, B-39).

F1 della Chiusura (13/10/2026), patch per F3a (padrone di `briefing.py`).
Rossa prima della correzione: la riga guardava il solo corpo `None`, e
un'automazione col corpo archiviato ma in `unread_bodies` non era segnata,
mentre l'avviso la contava.
"""
from hiris.app.home_space.render import BODY_UNKNOWN
from tests.test_briefing import _CASA, _COMPORTAMENTO, _RICORDI, _STATO, compose


def test_la_riga_e_l_avviso_contano_le_stesse_voci():
    testo, riepilogo = compose(
        _CASA, _COMPORTAMENTO, _RICORDI, _STATO,
        unread_bodies={"automation.sveglia": "configurazione non letta da Home Assistant"})
    avviso = next(a for a in riepilogo["notices"] if BODY_UNKNOWN in a)
    assert avviso.startswith("di 2 fra"), avviso
    righe = [r for r in testo.splitlines() if BODY_UNKNOWN in r and "(id: " in r]
    assert len(righe) == 2, righe
    assert any("Sveglia" in r for r in righe)
