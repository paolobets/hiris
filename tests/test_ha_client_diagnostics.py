"""Test per `_truncate`, il taglio che le letture di HAClient usano.

Qui stavano anche le prove di `render_template` (REST), uscito il 02/10/2026
senza chiamanti; il diario era uscito il 30/09/2026 con la storia, e con lei
`get_system_health` (WS).
"""
from hiris.app.proxy.ha_client import _truncate

# --------------------------------------------------------------------------
# _truncate
# --------------------------------------------------------------------------

def test_truncate_never_exceeds_cap():
    """Il contratto e' "marcatore incluso nel cap": con un cap troppo piccolo
    per ospitarlo si taglia e basta, ma il cap non si sfora mai."""
    assert _truncate("abc", 10) == "abc"
    for cap in (0, 1, 5, 10, 11, 12, 50):
        assert len(_truncate("x" * 5000, cap)) <= cap
    lungo = _truncate("x" * 5000, 100)
    assert len(lungo) == 100 and lungo.endswith("[troncato]")


def test_truncate_e_la_stessa_funzione_di_sanitize():
    """M1 (revisione di agosto 2026): `ha_client.py::_truncate` e
    `_sanitize.py`'s `sanitize_text` usavano due implementazioni duplicate
    (stesso algoritmo, stessa costante) del taglio con marcatore. Ora
    `_truncate` E' `_sanitize.truncate_with_marker` -- non solo si comporta
    allo stesso modo, e' letteralmente lo stesso oggetto funzione, come il
    test di identita' introdotto per N1 in FIX1-report.md."""
    from hiris.app.proxy import _sanitize, ha_client
    assert ha_client._truncate is _sanitize.truncate_with_marker
