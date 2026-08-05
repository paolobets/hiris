"""Task 4 of "memoria unica 3a": cio' che una PERSONA ha dichiarato entra
SEMPRE nel contesto, cio' che HIRIS ha dedotto si richiama.

`KnowledgeStore.declared()` e' l'unica lettura dei dichiarati (source in
DECLARED_SOURCES). Vive dentro lo store, come `recent()`/`search()`, e RIUSA
`_clausole_di_scope` -- nessuna seconda copia dei filtri di riservatezza (vedi
test_degraded_search_applies_the_same_filters in
test_knowledge_store_recent.py per il precedente di questa disciplina).
"""
from datetime import datetime, timedelta, timezone

import pytest

from hiris.app.brain.knowledge_store import DECLARED_MAX, DECLARED_SOURCES, KnowledgeStore

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _store(tmp_path):
    return KnowledgeStore(str(tmp_path / "k.db"))


def _add(s, content, **kw):
    return s.add_item(kind=kw.pop("kind", "note"), content=content, **kw)


def test_declared_sources_are_exactly_chat_manual_migrated():
    # Pin the classification the brief asks for: chat/manual (declared
    # directly) plus migrated (legacy per-agent memories -- also a person's
    # own words, just carrying different provenance after the Slice-3
    # migration). Everything HIRIS produced on its own (history-digest,
    # brain, mayan) must NOT be in this tuple.
    assert set(DECLARED_SOURCES) == {"chat", "manual", "migrated"}
    assert "history-digest" not in DECLARED_SOURCES
    assert "brain" not in DECLARED_SOURCES
    assert "mayan" not in DECLARED_SOURCES


def test_declared_max_is_thirty():
    # Named constant, chosen and pinned (see report for the "why 30").
    assert DECLARED_MAX == 30


def test_declared_includes_chat_manual_migrated_sources(tmp_path):
    s = _store(tmp_path)
    _add(s, "detto in chat", source="chat")
    _add(s, "aggiunto a mano", source="manual")
    _add(s, "memoria legacy migrata", source="migrated")
    got = set(r["content"] for r in s.declared()[0])
    assert got == {"detto in chat", "aggiunto a mano", "memoria legacy migrata"}
    s.close()


def test_declared_excludes_deduced_sources(tmp_path):
    """The behaviour that matters: an insight HIRIS produced itself
    (history-digest), a brain trace, or a mayan document must never appear
    in the declared block -- no matter how many of them there are."""
    s = _store(tmp_path)
    _add(s, "il modulo meteo esterno e' guasto", source="chat")
    _add(s, "media settimanale della temperatura", kind="insight", source="history-digest")
    _add(s, "traccia del brain", source="brain")
    _add(s, "documento mayan", kind="document", source="mayan", source_ref="42")
    items, total = s.declared()
    contents = set(r["content"] for r in items)
    assert contents == {"il modulo meteo esterno e' guasto"}
    assert total == 1
    s.close()


def test_declared_default_source_manual_is_declared(tmp_path):
    """add_item()'s default source ('manual') is itself a declared source --
    an item saved without an explicit `source=` must still surface here."""
    s = _store(tmp_path)
    _add(s, "aggiunto senza specificare source")
    assert [r["content"] for r in s.declared()[0]] == ["aggiunto senza specificare source"]
    s.close()


def test_declared_hides_sensitive_unless_allowed(tmp_path):
    s = _store(tmp_path)
    _add(s, "normale", source="chat", sensitivity="normal")
    _add(s, "riservato", source="chat", sensitivity="sensitive")
    assert [r["content"] for r in s.declared()[0]] == ["normale"]
    got_allowed = set(r["content"] for r in s.declared(allow_sensitive=True)[0])
    assert got_allowed == {"normale", "riservato"}
    s.close()


def test_declared_cross_owner_sensitive_item_never_appears():
    """The case the brief calls out by name: an item belonging to a
    DIFFERENT owner, marked sensitive, must not appear -- even with
    allow_sensitive=True. Owner is the one axis _clausole_di_scope never
    relaxes for sensitivity."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        s = KnowledgeStore(os.path.join(d, "k.db"))
        _add(s, "segreto di paolo", source="chat", owner="paolo", sensitivity="sensitive")
        _add(s, "di casa", source="chat", owner="home", sensitivity="normal")
        got = set(r["content"] for r in s.declared(owner="giulia", allow_sensitive=True)[0])
        assert got == {"di casa"}
        assert "segreto di paolo" not in got
        s.close()


def test_declared_scopes_by_owner_home_and_own(tmp_path):
    s = _store(tmp_path)
    _add(s, "di casa", source="manual", owner="home")
    _add(s, "di paolo", source="manual", owner="paolo")
    _add(s, "di giulia", source="manual", owner="giulia")
    got = set(r["content"] for r in s.declared(owner="paolo")[0])
    assert got == {"di casa", "di paolo"}
    s.close()


def test_declared_only_approved(tmp_path):
    s = _store(tmp_path)
    _add(s, "approvato", source="chat", status="approved")
    _add(s, "in attesa", source="chat", status="pending")
    assert [r["content"] for r in s.declared()[0]] == ["approvato"]
    s.close()


def test_declared_excludes_expired_valid_until(tmp_path):
    s = _store(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(_TS_FMT)
    _add(s, "scaduto", source="chat", valid_until=past)
    _add(s, "valido", source="chat")
    assert [r["content"] for r in s.declared()[0]] == ["valido"]
    s.close()


def test_declared_orders_by_recency(tmp_path):
    s = _store(tmp_path)
    _add(s, "primo", source="chat")
    _add(s, "secondo", source="chat")
    _add(s, "terzo", source="chat")
    got = [r["content"] for r in s.declared()[0]]
    assert got == ["terzo", "secondo", "primo"]
    s.close()


def test_declared_respects_limit_and_reports_true_total(tmp_path):
    """Requirement 3: the limit is respected, and overflow is never silent
    -- the second element of the returned tuple is the TOTAL count that
    matched scope, so a caller can say "+N older, not shown" instead of
    just dropping them."""
    s = _store(tmp_path)
    for i in range(5):
        _add(s, f"dichiarato {i}", source="chat")
    items, total = s.declared(limit=3)
    assert len(items) == 3
    assert total == 5
    # the ones kept are the 3 MOST RECENT (same recency convention as recent())
    assert [r["content"] for r in items] == ["dichiarato 4", "dichiarato 3", "dichiarato 2"]
    s.close()


def test_declared_default_limit_is_declared_max(tmp_path):
    s = _store(tmp_path)
    for i in range(DECLARED_MAX + 5):
        _add(s, f"n{i}", source="chat")
    items, total = s.declared()
    assert len(items) == DECLARED_MAX
    assert total == DECLARED_MAX + 5
    s.close()


def test_declared_never_returns_the_embedding_blob(tmp_path):
    s = _store(tmp_path)
    _add(s, "x", source="chat", embedding=[1.0, 0.0])
    assert "embedding" not in s.declared()[0][0]
    s.close()


def test_declared_reuses_clausole_di_scope_not_a_second_copy(tmp_path):
    """Not a behavioural test but a structural guard: declared() must call
    _clausole_di_scope rather than hand-rolling its own owner/sensitivity/
    kind/valid_until SQL -- the whole point of Task 4's brief is that reads
    cannot diverge on confidentiality. Verified by source inspection, same
    spirit as this codebase's other structural/wiring pins."""
    import inspect
    from hiris.app.brain import knowledge_store

    src = inspect.getsource(knowledge_store.KnowledgeStore.declared)
    assert "_clausole_di_scope(" in src
