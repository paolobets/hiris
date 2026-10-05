"""La coda del ponte: la chat passa avanti, lo scaduto non si serve.

Tappa 6, Task 2 (piano `piani/2026-10-tappa-6-un-turno.md`, D4 approvata da
Paolo il 05/10/2026). Fino a qui `claim` serviva chi era arrivato prima
(`ORDER BY created_ts ASC`): una domanda in chat accodata dietro a un turno
dell'osservatore aspettava che il cervello finisse il suo.

Le prove:
- con un turno dell'osservatore accodato prima e uno di chat dopo, `claim`
  da' la chat;
- fra pari precedenza resta l'ordine d'arrivo;
- un turno scaduto non si serve, e lo spazzino lo chiude 'expired';
- un archivio scritto PRIMA della colonna (versione 3) si apre, migra, e le
  righe vecchie restano servibili con la precedenza di fondo;
- ogni accodamento del prodotto DICHIARA la sua precedenza: l'elenco delle
  chiamate si chiede al sorgente, non si scrive qui.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from hiris.app.chat_thread import ChatThread
from hiris.app.reasoning.queue import (
    PRIORITY_BACKGROUND,
    PRIORITY_CHAT,
    ReasoningQueue,
)

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
PAOLO = ChatThread("persona:p", "pannello")


@pytest.fixture
def q(tmp_path):
    coda = ReasoningQueue(str(tmp_path / "r.db"))
    yield coda
    coda.close()


def test_la_chat_accodata_dopo_passa_avanti_all_osservatore(q):
    q.enqueue("scope", {}, {}, 100.0, job_id="osservatore", now=1.0,
              priority=PRIORITY_BACKGROUND)
    q.enqueue("chat", {}, {}, 100.0, job_id="chat", now=2.0, thread=PAOLO,
              priority=PRIORITY_CHAT)
    assert q.claim(now=10.0)["job_id"] == "chat"
    assert q.claim(now=10.0)["job_id"] == "osservatore"


def test_fra_pari_precedenza_resta_l_ordine_d_arrivo(q):
    for nome, nato in (("primo", 1.0), ("secondo", 2.0), ("terzo", 3.0)):
        q.enqueue("analisi", {}, {}, 100.0, job_id=nome, now=nato,
                  priority=PRIORITY_BACKGROUND)
    assert [q.claim(now=10.0)["job_id"] for _ in range(3)] == [
        "primo", "secondo", "terzo"]


def test_la_precedenza_viaggia_col_turno(q):
    """Un dato che c'e' e nessuno puo' chiedere non esiste (fondamenta 4)."""
    q.enqueue("chat", {}, {}, 100.0, job_id="c", now=1.0, thread=PAOLO,
              priority=PRIORITY_CHAT)
    assert q.get("c")["priority"] == PRIORITY_CHAT
    assert q.claim(now=2.0)["priority"] == PRIORITY_CHAT


def test_un_turno_scaduto_non_si_serve_e_si_chiude_scaduto(q):
    """Anche se e' una chat, anche se e' l'unico in coda."""
    q.enqueue("chat", {}, {}, 5.0, job_id="vecchia", now=1.0, thread=PAOLO,
              priority=PRIORITY_CHAT)
    q.enqueue("scope", {}, {}, 100.0, job_id="viva", now=2.0,
              priority=PRIORITY_BACKGROUND)
    assert q.claim(now=10.0)["job_id"] == "viva"
    assert q.claim(now=10.0) is None
    assert [j["job_id"] for j in q.sweep_expired(now=10.0)] == ["vecchia"]
    assert q.get("vecchia")["status"] == "expired"


def test_un_archivio_di_prima_della_colonna_si_apre_e_si_serve(tmp_path):
    """La migrazione su un archivio in produzione: versione 3, righe vive."""
    percorso = str(tmp_path / "v3.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE reasoning_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
            wake_json TEXT NOT NULL, context_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', nonce TEXT,
            deadline_ts REAL NOT NULL, created_ts REAL NOT NULL,
            claimed_ts REAL, decided_ts REAL, decision_json TEXT,
            delivered_ts REAL, subject_key TEXT, entry_point TEXT);
        CREATE INDEX idx_reasoning_status ON reasoning_jobs(status, created_ts);
    """)
    conn.execute(
        "INSERT INTO reasoning_jobs(job_id,kind,wake_json,context_json,"
        "status,deadline_ts,created_ts) VALUES('di-prima','scope','{}','{}',"
        "'pending', 100.0, 1.0)")
    conn.execute("PRAGMA user_version=3")
    conn.commit()
    conn.close()

    coda = ReasoningQueue(percorso)
    try:
        assert coda._conn.execute("PRAGMA user_version").fetchone()[0] == 4
        colonne = {r[1] for r in coda._conn.execute(
            "PRAGMA table_info(reasoning_jobs)").fetchall()}
        assert "priority" in colonne
        assert coda.get("di-prima")["priority"] == PRIORITY_BACKGROUND
        coda.enqueue("chat", {}, {}, 100.0, job_id="nuova", now=2.0,
                     thread=PAOLO, priority=PRIORITY_CHAT)
        assert coda.claim(now=10.0)["job_id"] == "nuova"
        assert coda.claim(now=10.0)["job_id"] == "di-prima"
    finally:
        coda.close()
    # Una seconda apertura dello stesso archivio non rifa' la migrazione.
    ReasoningQueue(percorso).close()


def test_solo_la_chat_ha_la_precedenza_piu_alta():
    assert PRIORITY_CHAT > PRIORITY_BACKGROUND


# -- Ogni accodamento del prodotto dichiara la sua precedenza ----------------
#
# La lista delle chiamate si chiede al sorgente (CLAUDE.md, «Un cancello CHIEDE
# il suo elenco»): un accodamento nuovo entra nella prova senza toccarla.


def _enqueue_calls() -> list[tuple[str, int, ast.Call]]:
    trovate = []
    for percorso in sorted(APP.rglob("*.py")):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "enqueue"):
                trovate.append((str(percorso.relative_to(APP)), nodo.lineno, nodo))
    return trovate


def test_la_ricerca_degli_accodamenti_trova_i_sei_del_ponte():
    """Prova della derivazione: un insieme improvvisamente piccolo e' un
    cancello che sembra vivo e non guarda piu' niente. Sei al 05/10/2026
    (piano della Tappa 6, «Gli accodamenti sul ponte»)."""
    assert len(_enqueue_calls()) >= 6


def test_ogni_accodamento_del_prodotto_dichiara_la_precedenza():
    senza = [f"{f}:{riga}" for f, riga, nodo in _enqueue_calls()
             if not any(k.arg == "priority" for k in nodo.keywords)]
    assert not senza, (
        "accodamenti senza `priority=`: la precedenza si dichiara a ogni "
        f"accodamento, non si eredita in silenzio: {senza}")
