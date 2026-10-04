"""Il fuso della casa, la lettura di un istante e il vocabolario di Home
Assistant che la storia usa: puri, provabili senza rete.

Fino al 30/09/2026 questo file provava anche la scelta della superficie e la
finestra dei due strumenti del tempo (`choose_surface`, `window`,
`normalize_hours`): usciti con gli strumenti, la scelta vive in
`house_history.value_surface` e si prova in `tests/test_house_history.py`."""
from datetime import UTC

from hiris.app.home_space import historian
from hiris.app.home_space.ha_vocabulary import bands_are_arithmetic, produces_statistics
from hiris.app.home_space.historian import home_space_zone, instant_epoch
from hiris.app.proxy.ha_client import HAClient


def test_senza_un_fuso_noto_si_resta_in_utc_e_non_si_inventa_niente():
    """Un fuso inventato sposterebbe le ore di una risposta senza dirlo.

    Mutazione ESEGUITA: `home_space_zone` senza il `try` -- rossa sul fuso
    inesistente (`ZoneInfoNotFoundError`)."""
    assert home_space_zone(None) is UTC
    assert home_space_zone("Marte/Olympus") is UTC
    assert str(home_space_zone("Europe/Rome")) == "Europe/Rome"


def test_un_istante_senza_fuso_non_si_legge():
    """«Alle 8» di quale fuso? Un istante senza fuso e' rifiutato, non letto
    come locale.

    Mutazione ESEGUITA: `instant_epoch` che tratta un istante senza fuso come
    UTC (`moment.replace(tzinfo=UTC)`) invece di rifiutarlo -- rossa sul
    primo `assert ... is None`."""
    assert instant_epoch("2026-09-29T08:00:00") is None
    assert instant_epoch("2026-09-29T08:00:00+00:00") == 1_790_668_800.0
    assert instant_epoch(None) is None


def test_i_lettori_usciti_con_i_quattro_strumenti_non_esistono_piu():
    """Codice morto via nella stessa fetta (regola del proprietario).

    Mutazione ESEGUITA: rimettere `HAClient.statistics` -- rossa."""
    for nome in ("trend", "logbook", "choose_surface", "window", "normalize_hours"):
        assert not hasattr(historian, nome), nome
    for nome in ("logbook", "statistics", "automation_trace"):
        assert not hasattr(HAClient, nome), nome


def test_measurement_angle_has_statistics_but_not_arithmetic_bands():
    """`measurement_angle` (angoli, es. la direzione del vento) PRODUCE
    statistiche -- la media circolare: `DEFAULT_STATISTICS` in
    `components/sensor/recorder.py`, tag 2026.9.1, letto il 04/10/2026 (B-12).
    Fino a quel giorno l'insieme la lasciava fuori. Le sue fasce non portano
    ne' minimo ne' massimo, e una media di angoli che i conti di HIRIS non
    sanno leggere: la storia la tiene sul dettaglio (`bands_are_arithmetic`,
    il consumatore e' `house_history.value_surface`).

    Mutazione ESEGUITA: `bands_are_arithmetic` ridotta a
    `produces_statistics` -- rossa sull'ultimo `assert ... is False`."""
    assert produces_statistics("measurement_angle") is True
    assert produces_statistics("measurement") is True
    assert produces_statistics("total") is True
    assert produces_statistics("total_increasing") is True
    assert produces_statistics(None) is False
    assert produces_statistics("") is False
    assert bands_are_arithmetic("measurement") is True
    assert bands_are_arithmetic("total_increasing") is True
    assert bands_are_arithmetic(None) is False
    assert bands_are_arithmetic("measurement_angle") is False
