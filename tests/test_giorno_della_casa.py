"""I confini di un giorno nel fuso della casa, in un posto solo.

Spostati il 30/09/2026 da `mind/facts.py` a `home_space/historian.py`: la
storia («oggi», «ieri», spec `docs/design/2026-09-30-la-storia.md` §2) ne ha
bisogno in `home_space/`, e `home_space` non importa da `mind`."""
import inspect

from hiris.app.home_space.historian import day_boundaries
from hiris.app.mind import facts


def test_il_giorno_del_cambio_d_ora_dura_venticinque_ore():
    """25/10/2026, Roma: alle 03:00 si torna alle 02:00.

    Mutazione ESEGUITA: `replace(tzinfo=UTC)` al posto del fuso della casa
    -- rossa (24 ore)."""
    inizio, fine = day_boundaries("2026-10-25", "Europe/Rome")
    assert (fine - inizio) / 3600 == 25


def test_la_mezzanotte_e_quella_della_casa():
    """30/09/2026 00:00 a Roma sono le 22:00 UTC del 29.

    Mutazione ESEGUITA: `replace(tzinfo=UTC)` al posto del fuso della casa
    -- rossa (la mezzanotte UTC, due ore dopo)."""
    inizio, _fine = day_boundaries("2026-09-30", "Europe/Rome")
    assert inizio == 1_790_719_200.0


def test_i_confini_del_giorno_sono_scritti_una_volta_sola():
    """Nessun doppione (fondamenta 2): `facts` li importa, non li riscrive.

    Mutazione ESEGUITA: lasciare la vecchia `def day_boundaries` in
    `mind/facts.py` -- rossa."""
    assert "def day_boundaries" not in inspect.getsource(facts)
    assert facts.day_boundaries is day_boundaries
