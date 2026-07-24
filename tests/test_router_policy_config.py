# tests/test_router_policy_config.py — helper di parsing CSV → lista, riusabile
from hiris.app.server import _parse_policy_csv  # nuova funzione modulo-livello


def test_parse_policy_csv_valid():
    assert _parse_policy_csv("claude, ollama") == ["claude", "ollama"]


def test_parse_policy_csv_empty_is_none():
    assert _parse_policy_csv("") is None
    assert _parse_policy_csv(None) is None


def test_parse_policy_csv_drops_unknown():
    assert _parse_policy_csv("claude,foo,ollama") == ["claude", "ollama"]


def test_parse_policy_csv_all_invalid_is_none():
    assert _parse_policy_csv("foo,bar") is None
