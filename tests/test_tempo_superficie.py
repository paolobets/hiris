"""La scelta della superficie temporale: pura, e provabile senza rete.

E' la spec §3.1 resa eseguibile. Sceglie il CODICE perche' la scelta non e'
una questione di intenzione: dipende da quanto indietro si guarda e da che
tipo e' l'entita'. Chiederlo al modello significherebbe pretendere che
conosca la politica di conservazione del recorder di QUESTA casa.
"""
import pytest

from hiris.app.home_space.historian import (
    DEFAULT_HOURS,
    GRANULARITY_THRESHOLD_HOURS,
    MAX_WINDOW_HOURS,
    choose_surface,
    normalize_hours,
    produces_statistics,
    window,
)


def test_below_the_threshold_real_changes_are_seen():
    assert choose_surface(hours=6, has_statistics=True) == "dettaglio"
    assert choose_surface(hours=6, has_statistics=False) == "dettaglio"


def test_above_the_threshold_with_statistics_switches_to_bands():
    assert choose_surface(hours=48, has_statistics=True) == "statistiche"


def test_above_the_threshold_without_statistics_stays_on_detail():
    """Non e' una svista: per un'entita' senza `state_class` il dettaglio e'
    l'UNICA fonte che esista. Passare alle statistiche darebbe un elenco
    vuoto, cioe' «non e' mai cambiato»."""
    assert choose_surface(hours=48, has_statistics=False) == "dettaglio"


def test_the_threshold_is_inclusive_and_declared():
    assert GRANULARITY_THRESHOLD_HOURS == 24
    assert choose_surface(hours=GRANULARITY_THRESHOLD_HOURS, has_statistics=True) == "dettaglio"
    assert choose_surface(
        hours=GRANULARITY_THRESHOLD_HOURS + 0.1, has_statistics=True) == "statistiche"


@pytest.mark.parametrize("raw", [None, "molte", float("nan"), -3, 0, 10**12])
def test_impossible_hours_never_raise(raw):
    """`ore` arriva da una tool-call: puo' essere qualunque cosa. Un
    OverflowError dentro un timedelta spezzerebbe il turno del modello."""
    hours = normalize_hours(raw)
    assert 1.0 <= hours <= MAX_WINDOW_HOURS


def test_the_window_is_computed_in_the_home_space_timezone():
    """Le statistiche tornano in UTC, l'utente pensa in ora locale. La fetta
    dello schedulatore ha gia' pagato un difetto di orologi diversi: qui la
    finestra nasce nel fuso della casa e lo porta scritto (spec §3.4)."""
    # 24 agosto 2026, 12:00 UTC = 14:00 a Roma (CEST, +02:00).
    now = 1787572800.0
    da, a = window(hours=2, now_ts=now, timezone="Europe/Rome")
    assert a.startswith("2026-08-24T14:00:00")
    assert da.startswith("2026-08-24T12:00:00")
    assert a.endswith("+02:00") and da.endswith("+02:00")


def test_without_a_known_timezone_it_stays_in_utc_and_invents_nothing():
    """`sistema_di_riferimento()` puo' non aver mai letto la casa. Un fuso
    inventato sposterebbe le ore di una risposta senza dirlo a nessuno."""
    da, a = window(hours=2, now_ts=1787572800.0, timezone=None)
    assert a.endswith("+00:00") and da.endswith("+00:00")


def test_a_nonexistent_timezone_does_not_raise():
    _da, a = window(hours=2, now_ts=1787572800.0, timezone="Marte/Olympus")
    assert a.endswith("+00:00")


def test_impossible_huge_integers_do_not_raise():
    """`float(10**400)` solleva OverflowError, non TypeError o ValueError.
    E' la classe di input che una tool-call JSON senza punto decimale produce.
    normalize_hours deve catturare Exception, non un sottoinsieme, perche' il
    suo contratto e' «qualunque cosa → un numero fra 1 e il tetto»."""
    hours = normalize_hours(10**400)
    assert hours == DEFAULT_HOURS


# -- F4 (onda finale): measurement_angle NON produce statistiche -----------

def test_measurement_angle_does_not_produce_statistics():
    """Spec S1: `measurement_angle` esiste come `state_class` (angoli, es.
    la direzione del vento) ma NON produce statistiche -- va trattato come
    le entita' senza classe. Un'appartenenza al vero insieme di HA
    (`measurement`, `total`, `total_increasing`), non un `bool(state_class)`
    ne' un'esclusione della sola `measurement_angle`."""
    assert produces_statistics("measurement_angle") is False
    assert produces_statistics("measurement") is True
    assert produces_statistics("total") is True
    assert produces_statistics("total_increasing") is True
    assert produces_statistics(None) is False
    assert produces_statistics("") is False
