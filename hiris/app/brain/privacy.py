from __future__ import annotations
import hashlib
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from ..storage import connect, init_schema

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_VAULT_SCHEMA = """
CREATE TABLE IF NOT EXISTS pseudonym_vault (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT NOT NULL UNIQUE,
    value_hash  TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    pii_type    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_type ON pseudonym_vault(pii_type);
"""


class VaultStore:
    """Mappa locale, reversibile, PII<->token. NB: `value` è in chiaro
    (la cifratura at-rest è differita, uniforme con la cifratura whole-DB)."""

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._mu = threading.Lock()
        init_schema(self._conn, _VAULT_SCHEMA, version=1)

    @staticmethod
    def _hash(pii_type: str, value: str) -> str:
        return hashlib.sha256(f"{pii_type}:{value}".encode("utf-8")).hexdigest()

    def token_for(self, pii_type: str, value: str) -> str:
        h = self._hash(pii_type, value)
        with self._mu:
            row = self._conn.execute(
                "SELECT token FROM pseudonym_vault WHERE value_hash=?", (h,)
            ).fetchone()
            if row:
                return row["token"]
            n = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pseudonym_vault WHERE pii_type=?",
                (pii_type,),
            ).fetchone()["c"] + 1
            token = f"[{pii_type.upper()}_{n}]"
            self._conn.execute(
                "INSERT INTO pseudonym_vault(token, value_hash, value, pii_type, created_at)"
                " VALUES(?,?,?,?,?)",
                (token, h, value, pii_type, datetime.now(timezone.utc).strftime(_TS_FMT)),
            )
            self._conn.commit()
            return token

    def value_for(self, token: str) -> str | None:
        with self._mu:
            row = self._conn.execute(
                "SELECT value FROM pseudonym_vault WHERE token=?", (token,)
            ).fetchone()
        return row["value"] if row else None

    def close(self) -> None:
        with self._mu:
            self._conn.close()


# ---------------------------------------------------------------------------
# PII recognizers — Italian, ordered specific-first to avoid overlaps
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("iban", re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Za-z]{12}\b")),
    ("codice_fiscale", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){12,15}\d\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", re.compile(r"(?:\+39\s?)?\b3\d{2}[\s.-]?\d{6,7}\b")),
]


def detect_pii(text: str) -> list[tuple[int, int, str, str]]:
    """Ritorna [(start, end, pii_type, value)] senza sovrapposizioni,
    privilegiando i match più a sinistra e i tipi più specifici."""
    spans: list[tuple[int, int, str, str]] = []
    taken: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(s < te and e > ts for ts, te in taken)

    for pii_type, pat in _PII_PATTERNS:
        for m in pat.finditer(text):
            s, e = m.start(), m.end()
            if overlaps(s, e):
                continue
            taken.append((s, e))
            spans.append((s, e, pii_type, m.group()))
    spans.sort(key=lambda x: x[0])
    return spans


# ---------------------------------------------------------------------------
# Pseudonymizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")


class Pseudonymizer:
    def __init__(self, vault: VaultStore) -> None:
        self._vault = vault

    def pseudonymize(self, text: str) -> str:
        spans = detect_pii(text)
        if not spans:
            return text
        out = []
        last = 0
        for s, e, pii_type, value in spans:
            out.append(text[last:s])
            out.append(self._vault.token_for(pii_type, value))
            last = e
        out.append(text[last:])
        return "".join(out)

    def detokenize(self, text: str) -> str:
        def repl(m: re.Match) -> str:
            val = self._vault.value_for(m.group())
            return val if val is not None else m.group()
        return _TOKEN_RE.sub(repl, text)
