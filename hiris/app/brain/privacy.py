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
    """Tokenizes/detokenizes PII for the outbound-to-cloud-LLM path.

    SECURITY (review B/#7 — confirmed HIGH, PII cross-leak): the vault
    (``VaultStore``) is a single home-global, sequentially-named, forever-
    growing token store with NO owner/conversation scoping. Looking a token
    up directly in the vault from ``detokenize`` — as this class used to do —
    means ANY ``[TYPE_N]`` pattern appearing in ANY model output (user-typed,
    model-hallucinated, or prompt-injected from a poisoned document) gets
    blindly expanded to real PII, including PII pseudonymized in a
    *different* conversation by a *different* user.

    Fix: ``detokenize`` never consults the vault. It only expands tokens
    present in the caller-supplied per-request/per-exchange ``mapping`` —
    the exact ``token -> value`` pairs ``pseudonymize`` produced for THIS
    outbound request. A token missing from ``mapping`` (hallucinated,
    injected, or minted by a different request) is left verbatim: it can
    never resolve to real PII. Callers must thread the SAME dict returned/
    populated by their ``pseudonymize`` call into the matching ``detokenize``
    call — never share it across requests/conversations. See
    docs/archive/reviews/2026-07-25-fable-whole-codebase-review.md finding #7 and
    .superpowers/sdd/task-B3-report.md for the full design rationale.
    """

    def __init__(self, vault: VaultStore) -> None:
        self._vault = vault

    def pseudonymize(self, text: str, mapping: dict[str, str] | None = None) -> str:
        """Replace detected PII with vault tokens.

        If ``mapping`` is provided, every ``token -> original_value`` pair
        minted or reused for THIS call is recorded into it (in place). Pass
        the SAME dict to ``detokenize`` for the matching outbound request so
        only tokens this request actually created can be expanded back.
        """
        spans = detect_pii(text)
        if not spans:
            return text
        out = []
        last = 0
        for s, e, pii_type, value in spans:
            out.append(text[last:s])
            token = self._vault.token_for(pii_type, value)
            if mapping is not None:
                mapping[token] = value
            out.append(token)
            last = e
        out.append(text[last:])
        return "".join(out)

    def detokenize(self, text: str, mapping: dict[str, str] | None = None) -> str:
        """Expand ONLY tokens present in ``mapping`` (this request's own
        pseudonymize output) — never falls back to a global/vault lookup.

        ``mapping`` defaults to "no tokens known" (safe default: nothing is
        expanded) rather than to the shared vault, so a caller that forgets
        to thread its per-request mapping fails safe instead of leaking
        cross-request PII.
        """
        m = mapping or {}

        def repl(match: re.Match) -> str:
            return m.get(match.group(), match.group())
        return _TOKEN_RE.sub(repl, text)
