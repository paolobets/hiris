"""La regola della degradazione: significati quando si puo', recenti quando no.

Vive DENTRO lo store apposta: nessun chiamante deve crescere un ramo, e i
filtri di riservatezza devono essere gli stessi identici su entrambi i
percorsi -- un percorso che ne perde uno non e' una degradazione, e' una falla.
"""
from datetime import datetime, timedelta, timezone

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _store(tmp_path):
    return KnowledgeStore(str(tmp_path / "k.db"))


def _add(s, content, **kw):
    return s.add_item(kind=kw.pop("kind", "note"), content=content, **kw)


def test_recent_returns_newest_first(tmp_path):
    s = _store(tmp_path)
    _add(s, "primo")
    _add(s, "secondo")
    _add(s, "terzo")
    got = [r["content"] for r in s.recent(k=3)]
    assert got == ["terzo", "secondo", "primo"]
    s.close()


def test_recent_honours_k(tmp_path):
    s = _store(tmp_path)
    for i in range(5):
        _add(s, f"n{i}")
    assert len(s.recent(k=2)) == 2
    s.close()


def test_recent_hides_sensitive_unless_allowed(tmp_path):
    s = _store(tmp_path)
    _add(s, "normale", sensitivity="normal")
    _add(s, "riservato", sensitivity="sensitive")
    assert [r["content"] for r in s.recent(k=5)] == ["normale"]
    assert set(r["content"] for r in s.recent(k=5, allow_sensitive=True)) == {
        "normale", "riservato"
    }
    s.close()


def test_recent_filters_kinds_and_treats_empty_list_as_deny_all(tmp_path):
    s = _store(tmp_path)
    _add(s, "un fatto", kind="fact")
    _add(s, "una nota", kind="note")
    assert [r["content"] for r in s.recent(k=5, kinds=["fact"])] == ["un fatto"]
    assert s.recent(k=5, kinds=[]) == []
    assert len(s.recent(k=5, kinds="all")) == 2
    s.close()


def test_recent_scopes_by_owner_and_chatbot(tmp_path):
    s = _store(tmp_path)
    _add(s, "di casa", owner="home")
    _add(s, "di paolo", owner="paolo")
    _add(s, "del bot", owner="home", chatbot_id="bot-1")
    got = set(r["content"] for r in s.recent(k=9, owner="paolo"))
    assert "di paolo" in got and "di casa" in got
    assert "del bot" not in got
    s.close()


def test_recent_only_approved(tmp_path):
    s = _store(tmp_path)
    _add(s, "approvato", status="approved")
    _add(s, "in attesa", status="pending")
    assert [r["content"] for r in s.recent(k=5)] == ["approvato"]
    s.close()


def test_recent_includes_rows_without_embedding(tmp_path):
    """E' il punto di tutto: la ricerca vettoriale le esclude per costruzione."""
    s = _store(tmp_path)
    _add(s, "senza vettore")
    assert [r["content"] for r in s.recent(k=5)] == ["senza vettore"]
    s.close()


def test_recent_never_returns_the_embedding_blob(tmp_path):
    s = _store(tmp_path)
    _add(s, "x", embedding=[1.0, 0.0])
    assert "embedding" not in s.recent(k=1)[0]
    s.close()


def test_search_without_a_query_vector_degrades_to_recent(tmp_path):
    """Il NullEmbedder ritorna [] -- questo e' il caso di fabbrica."""
    s = _store(tmp_path)
    _add(s, "vecchio")
    _add(s, "nuovo")
    assert [r["content"] for r in s.search(query_vec=[], k=2)] == ["nuovo", "vecchio"]
    s.close()


def test_search_with_a_query_vector_still_ranks_by_meaning(tmp_path):
    """Chi HA un embedder non deve perdere niente."""
    s = _store(tmp_path)
    _add(s, "lontano", embedding=[0.0, 1.0])
    _add(s, "vicino", embedding=[1.0, 0.0])
    got = [r["content"] for r in s.search(query_vec=[1.0, 0.0], k=2)]
    assert got[0] == "vicino"
    s.close()


def test_recent_excludes_expired_valid_until(tmp_path):
    """`valid_until` was folded into `_clausole_di_scope` by inference, not
    because a task named it -- and recency (`recent()`) is now the
    factory-default path (NullEmbedder -> search() degrades to recent()), so
    an expired row leaking through here would leak a stale fact straight
    into the default install."""
    s = _store(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(_TS_FMT)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(_TS_FMT)
    _add(s, "scaduto", valid_until=past)
    _add(s, "valido con scadenza futura", valid_until=future)
    _add(s, "valido senza scadenza")
    got = set(r["content"] for r in s.recent(k=5))
    assert got == {"valido con scadenza futura", "valido senza scadenza"}
    s.close()


def test_degraded_search_applies_the_same_filters(tmp_path):
    """Una degradazione che perde un filtro di riservatezza e' una falla."""
    s = _store(tmp_path)
    _add(s, "normale", sensitivity="normal")
    _add(s, "riservato", sensitivity="sensitive")
    assert [r["content"] for r in s.search(query_vec=[], k=5)] == ["normale"]
    s.close()
