import pytest

from hiris.app.env_util import env_bool


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "Yes", "on", "ON"])
def test_truthy_values(monkeypatch, value):
    monkeypatch.setenv("HIRIS_TEST_FLAG", value)
    assert env_bool("HIRIS_TEST_FLAG") is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", "nope", "2"])
def test_falsey_values(monkeypatch, value):
    monkeypatch.setenv("HIRIS_TEST_FLAG", value)
    assert env_bool("HIRIS_TEST_FLAG") is False


def test_unset_returns_default_false(monkeypatch):
    monkeypatch.delenv("HIRIS_TEST_FLAG", raising=False)
    assert env_bool("HIRIS_TEST_FLAG") is False


def test_unset_returns_explicit_default_true(monkeypatch):
    monkeypatch.delenv("HIRIS_TEST_FLAG", raising=False)
    assert env_bool("HIRIS_TEST_FLAG", default=True) is True


def test_empty_string_returns_default(monkeypatch):
    monkeypatch.setenv("HIRIS_TEST_FLAG", "")
    assert env_bool("HIRIS_TEST_FLAG") is False
    assert env_bool("HIRIS_TEST_FLAG", default=True) is True


def test_whitespace_only_returns_default(monkeypatch):
    monkeypatch.setenv("HIRIS_TEST_FLAG", "   ")
    assert env_bool("HIRIS_TEST_FLAG") is False
    assert env_bool("HIRIS_TEST_FLAG", default=True) is True


def test_whitespace_padded_truthy(monkeypatch):
    monkeypatch.setenv("HIRIS_TEST_FLAG", "  true  ")
    assert env_bool("HIRIS_TEST_FLAG") is True


def test_case_insensitive_mixed(monkeypatch):
    monkeypatch.setenv("HIRIS_TEST_FLAG", "TrUe")
    assert env_bool("HIRIS_TEST_FLAG") is True
