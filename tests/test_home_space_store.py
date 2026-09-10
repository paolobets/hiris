"""Cio' che resta di `casa.db`: le plance e la cornice.

**Sette prove sono uscite il 10/09/2026 con cio' che difendevano**: il
comportamento non vive piu' qui. Quelle che difendevano una proprieta'
sopravvissuta l'hanno seguita invece di morire con la tabella -- la
sanificazione del nome e la distinzione fra «non ho il corpo» e «il corpo e'
vuoto» stanno ora in `tests/test_home_space_behavior.py`, dove sta il confine
che le applica; «i problemi e i corpi non letti si tengono accanto alle voci»
sta in `tests/test_home_space_reader.py`, dove sta la casa che li tiene.

Sono uscite invece, ciascuna con la sua ragione: il corpo illeggibile **su
disco** (di disco non ce n'e' piu') e l'id sintetico che si dichiarava non
reale (ogni id e' ora un `entity_id` vero, e `id_reale` non esiste).
"""
import pytest

from hiris.app.home_space.store import HomeSpaceStore


@pytest.fixture
def archivio(tmp_path):
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    yield a
    a.close()


def test_non_disponibili_delle_plance_si_conservano_accanto_ai_dati(archivio):
    archivio.replace_dashboards(
        [{"url_path": "cucina", "title": "Cucina", "mode": "storage", "config": {}}],
        unavailable=["camera (config illeggibile)"],
    )
    assert archivio.unavailable_dashboards() == ["camera (config illeggibile)"]
    archivio.replace_dashboards(
        [{"url_path": "cucina", "title": "Cucina", "mode": "storage", "config": {}}])
    assert archivio.unavailable_dashboards() == []


def test_la_data_delle_plance_e_la_loro(archivio):
    """Ogni sezione porta la propria data. `aggiornata_il` era un campo di
    primo livello letto anche per le plance, e una plancia congelata da
    settimane appariva «aggiornata a oggi» solo perche' l'anagrafe era stata
    riletta di recente.

    Dal 10/09/2026 la sezione qui dentro e' una sola -- anagrafe e
    comportamento si tengono a memoria, con le loro date (`reader.HomeSpace`)
    -- ma la proprieta' non cambia: leggere una sezione non deve far sembrare
    fresca l'altra."""
    assert archivio.dashboards_loaded_at() is None

    archivio.replace_dashboards(
        [{"url_path": "cucina", "title": "Cucina", "mode": "storage", "config": {}}])

    assert archivio.dashboards_loaded_at() is not None
