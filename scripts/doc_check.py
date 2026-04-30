#!/usr/bin/env python3
"""HIRIS doc-check — static documentation consistency checker.

Detects stale config key names, broken cross-links, missing version headers,
and documentation coverage gaps.  Run before every release.

Exit codes:
  0 — all checks passed (or all errors were auto-fixed with --fix)
  1 — one or more hard errors remain

Usage:
  python scripts/doc_check.py          # check only, print findings
  python scripts/doc_check.py --fix    # auto-fix stale key names, then check
"""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
README = ROOT / "README.md"

_GREEN = "\033[32m"
_RED   = "\033[31m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"

# ── Stale config key names introduced before v0.6.6 ─────────────────────────
# Maps the old (wrong) name to the correct nested name.
# Add new entries here whenever a config key is renamed.
_STALE_KEYS: dict[str, str] = {
    "local_model_url":          "local_model.url",
    "local_model_name":         "local_model.model",
    "mqtt_host":                "mqtt.host",
    "mqtt_port":                "mqtt.port",
    "mqtt_user":                "mqtt.user",
    "mqtt_password":            "mqtt.password",
    "memory_embedding_provider":"memory.embedding_provider",
    "memory_embedding_model":   "memory.embedding_model",
    "memory_rag_k":             "memory.rag_k",
    "memory_retention_days":    "memory.retention_days",
}

# ── Docs that must carry a version header ───────────────────────────────────
# Keep in sync with _VERSIONED_DOCS in scripts/release.py.
_VERSIONED_NAMES: frozenset[str] = frozenset({
    "architecture.md",
    "architettura.md",
    "how-it-works.md",
    "come-funziona.md",
    "use-cases.md",
    "casi-duso.md",
    "configuration-guide.md",
    "guida-configurazione.md",
    "full-local-mode.md",
    "full-local-mode-it.md",
    "mqtt-integration.md",
})

# ── Internal / gitignored docs — not tracked, not linked from README ─────────
# These files exist only on local dev machines; the checker must not warn about
# them being absent from README or from _VERSIONED_NAMES.
_INTERNAL_DOCS: frozenset[str] = frozenset({
    "roadmap.md",
    "ROADMAP.md",
    "HIRIS_CLAUDE_CODE_PROMPT.md",
})


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ok(msg: str)   -> None: print(f"{_GREEN}✓{_RESET} {msg}")
def _warn(msg: str) -> None: print(f"{_YELLOW}⚠{_RESET} {msg}")
def _err(msg: str)  -> None: print(f"{_RED}✗{_RESET} {msg}")


def _doc_files() -> list[Path]:
    """All files to scan: README.md + docs/*.md (never CHANGELOG.md)."""
    return [README, *sorted(DOCS.glob("*.md"))]


# ── Check 1: stale config key names ─────────────────────────────────────────

# Match `` `key` `` in markdown prose, and bare `key:` lines inside YAML fences.
# Exclude lines that contain contextual words marking historical references
# ("renamed", "stale", "was", "old", "deprecated", "→", "->").
_HISTORY_LINE = re.compile(r"renamed|stale|\bwas\b|old\b|deprecated|→|->", re.IGNORECASE)


def _stale_occurrences(text: str, stale: str) -> list[int]:
    """Return list of 1-based line numbers where `stale` appears as a live key."""
    lines = text.splitlines()
    hits: list[int] = []
    for n, line in enumerate(lines, 1):
        if _HISTORY_LINE.search(line):
            continue
        # backtick form: `stale_key`
        if re.search(rf"(?<![.\w])`{re.escape(stale)}`", line):
            hits.append(n)
            continue
        # YAML code-block form: leading whitespace + key:
        if re.search(rf"^[ \t]*{re.escape(stale)}\s*:", line):
            hits.append(n)
    return hits


def check_stale_keys(files: list[Path], fix: bool) -> int:
    errors = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for stale, correct in _STALE_KEYS.items():
            hits = _stale_occurrences(text, stale)
            if not hits:
                continue
            rel = path.relative_to(ROOT)
            errors += len(hits)
            if fix:
                # Replace backtick form
                text = re.sub(
                    rf"(?<![.\w])`{re.escape(stale)}`",
                    f"`{correct}`",
                    text,
                )
                # Replace YAML key form
                text = re.sub(
                    rf"(?m)^([ \t]*){re.escape(stale)}(\s*:)",
                    rf"\g<1>{correct}\g<2>",
                    text,
                )
                path.write_text(text, encoding="utf-8")
                _warn(f"[fixed] {rel}: `{stale}` → `{correct}` (lines {hits})")
                errors -= len(hits)  # fixed, no longer an error
            else:
                _err(f"{rel}:{hits[0]}: stale key `{stale}` — should be `{correct}`"
                     + (f" (+{len(hits)-1} more)" if len(hits) > 1 else ""))
    if errors == 0 and not fix:
        _ok("No stale config key names found")
    elif fix:
        _ok("Stale key names fixed")
    return errors


# ── Check 2: broken cross-links ─────────────────────────────────────────────

_LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')


def check_crosslinks(files: list[Path]) -> int:
    errors = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for m in _LINK_RE.finditer(text):
            href = m.group(2).split("#")[0].strip()
            if not href or href.startswith(("http", "mailto", "#")):
                continue
            target = (path.parent / href).resolve()
            if not target.exists():
                rel = path.relative_to(ROOT)
                line = text[: m.start()].count("\n") + 1
                _err(f"{rel}:{line}: broken link → {href}")
                errors += 1
    if not errors:
        _ok("All cross-links resolve to existing files")
    return errors


# ── Check 3: version header presence ────────────────────────────────────────

# roadmap.md uses "> Last updated: DATE | Current version: **vX.Y.Z**"
_HEADER_RE = re.compile(
    r"^> (?:Version[e]?:\s*\d|Last updated:\s*\d)",
    re.MULTILINE,
)


def check_version_headers() -> int:
    warnings = 0
    for name in sorted(_VERSIONED_NAMES):
        path = DOCS / name
        if not path.exists():
            continue
        if not _HEADER_RE.search(path.read_text(encoding="utf-8")):
            _warn(f"docs/{name}: missing version header  (> Version: X.Y.Z ...)")
            warnings += 1
    if not warnings:
        _ok("All versioned docs have a version header")
    return 0  # version headers are warnings, not release-blockers


# ── Check 4: untracked docs ─────────────────────────────────────────────────

def check_untracked_docs() -> int:
    for path in sorted(DOCS.glob("*.md")):
        if path.name in _INTERNAL_DOCS:
            continue  # gitignored internal files — expected to be missing from README
        if path.name not in _VERSIONED_NAMES:
            _warn(f"docs/{path.name}: not in _VERSIONED_DOCS — won't get version "
                  "header on release; add it to scripts/release.py and scripts/doc_check.py")
    return 0  # informational only


# ── Check 5: README doc table completeness ───────────────────────────────────

def check_readme_coverage() -> int:
    if not README.exists():
        return 0
    readme = README.read_text(encoding="utf-8")
    for name in sorted(_VERSIONED_NAMES):
        ref = f"docs/{name}"
        ref_lower = f"docs/{name.lower()}"
        if ref not in readme and ref_lower not in readme:
            _warn(f"README.md: no link to {ref} in the Documentation table")
    return 0  # informational only


# ── Main ─────────────────────────────────────────────────────────────────────

def run(fix: bool = False) -> int:
    """Run all checks. Returns number of hard errors (0 = release OK)."""
    files = _doc_files()
    errors = 0
    errors += check_stale_keys(files, fix)
    errors += check_crosslinks(files)
    check_version_headers()    # warnings only
    check_untracked_docs()     # warnings only
    check_readme_coverage()    # warnings only
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HIRIS documentation consistency checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Auto-fix stale config key names in-place, then re-check",
    )
    args = parser.parse_args()
    errors = run(fix=args.fix)
    if errors:
        print(
            f"\n{_RED}{errors} hard error(s) found.{_RESET}  "
            f"Run with --fix to auto-repair stale key names, or fix manually."
        )
        sys.exit(1)
    label = "fixed and checked" if args.fix else "passed"
    print(f"\n{_GREEN}Doc check {label}.{_RESET}")


if __name__ == "__main__":
    main()
