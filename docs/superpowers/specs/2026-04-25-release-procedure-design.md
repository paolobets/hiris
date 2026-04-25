# HIRIS Release Procedure — Design Spec

> **Date:** 2026-04-25
> **Status:** Approved
> **Scope:** Structured release procedure with single-source versioning, mechanical script, and Claude-driven changelog

---

## Goal

Eliminate version desync bugs and ensure every push to GitHub includes consistent version bumps, updated documentation, passing tests, a git tag, and a GitHub Release that HA Supervisor can detect as an update.

## Problem Statement

Current pain points:
- Version hardcoded in 3 files (`config.yaml`, `server.py`, `test_api.py`) — easy to forget one
- No formal release step → HA Supervisor may not detect updates (checks `config.yaml` version on GitHub)
- `CHANGELOG.md` last updated at `0.3.0`, currently at `0.5.0`
- No git tags → `git log` since last release is not trivial to scope
- No GitHub Releases → HA add-on store cannot surface update notifications

---

## Architecture

### 1. Single Source of Truth for Version

`config.yaml` is the **only file** where the version is changed during a release.

`server.py` reads the version at import time via a small helper that parses `config.yaml` with a regex (no extra dependency):

```python
def _read_version() -> str:
    import re, pathlib
    cfg = pathlib.Path(__file__).parent.parent / "config.yaml"
    try:
        m = re.search(r'^version:\s*"([^"]+)"', cfg.read_text(), re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"

_VERSION = _read_version()
```

`test_api.py` reads the expected version from `config.yaml` at collection time (same regex), removing the hardcoded `"0.5.0"` assertion.

**Result:** bumping `config.yaml` is sufficient — `server.py` and tests align automatically.

### 2. `scripts/release.py` — Mechanical Executor

A standalone Python script (no external deps beyond stdlib + `gh` CLI) that performs all mechanical release steps in order. Each step prints `✓` on success or `✗ <reason>` on failure and exits non-zero.

**Interface:**
```bash
python scripts/release.py --version X.Y.Z           # standard release
python scripts/release.py --version X.Y.Z --dry-run  # preview only, no git ops
python scripts/release.py --version X.Y.Z --skip-tests  # skip pytest (hotfix only)
```

**Steps (executed in order, abort on first failure):**

| # | Step | Abort condition |
|---|------|----------------|
| 1 | Validate semver format `X.Y.Z` | format invalid |
| 2 | Read version from `config.yaml` — must equal `--version` | mismatch → user must update config.yaml first |
| 3 | Verify `CHANGELOG.md` contains `## [X.Y.Z]` section | section missing → Claude must write it first |
| 4 | Check git working tree has no unexpected changes outside `config.yaml` and `CHANGELOG.md` | other dirty files present |
| 5 | Run `pytest` (unless `--skip-tests`) | any test fails |
| 6 | `git add config.yaml CHANGELOG.md` + commit `chore: release vX.Y.Z` via Bash subprocess | commit fails |
| 7 | `git tag vX.Y.Z` | tag already exists |
| 8 | `git push origin master --tags` via Bash subprocess | push fails |
| 9 | Extract changelog body for `X.Y.Z` from `CHANGELOG.md` | section not parseable |
| 10 | `gh release create vX.Y.Z --title "HIRIS vX.Y.Z" --notes <body>` | gh CLI missing or fails |

**Dry-run:** steps 1–5 execute normally; steps 6–10 are printed but not executed.

**Git subprocess policy:** all `git` and `gh` commands are run via `subprocess.run(["git", ...], ...)` (never `shell=True`, never PowerShell) to avoid antivirus interference.

### 3. Claude Release Checklist (appended to `CLAUDE.md`)

A dedicated section in `CLAUDE.md` that Claude follows whenever the user requests a release. This is the semantic layer that script cannot handle.

**Trigger phrases:** "fai il release", "prepara la X.Y.Z", "rilascia", "bump version", "nuova versione"

**Procedure:**

```
STEP 1 — SCOPE COMMITS
  Run: git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --oneline
  Collect all commits since the last tag (or since repo start if no tags yet).

STEP 2 — PROPOSE VERSION
  Determine bump type from commits:
    - Any "feat:" or "feat(...):" → at minimum minor bump
    - Any "BREAKING CHANGE" or "!:" → major bump
    - Only "fix:", "chore:", "docs:", "test:" → patch bump
  Show proposed version to user and wait for confirmation.
  User may override with a different version.

STEP 3 — DRAFT CHANGELOG SECTION
  Generate a Keep-a-Changelog section:
    ## [X.Y.Z] — YYYY-MM-DD
    ### Added       ← feat: commits
    ### Fixed       ← fix: commits
    ### Changed     ← refactor:, perf: commits
    ### Removed     ← remove/delete commits
  Show the draft to the user and wait for approval.
  Incorporate any user edits.

STEP 4 — UPDATE FILES (after user approves changelog)
  a. Insert the approved section at the top of CHANGELOG.md
     (immediately after the `# HIRIS — Changelog` heading line)
  b. Update version field in config.yaml:
     version: "OLD" → version: "X.Y.Z"

STEP 5 — RUN RELEASE SCRIPT (via Bash, never PowerShell)
  python scripts/release.py --version X.Y.Z

STEP 6 — REPORT
  Show full script output.
  If exit code 0: announce "Release vX.Y.Z completato ✓ — HA rileverà l'aggiornamento al prossimo check."
  If non-zero: show the failing step and stop. Do NOT retry automatically.
```

---

## File Map

| File | Change |
|------|--------|
| `hiris/app/server.py` | Replace hardcoded `"0.5.0"` with `_read_version()` helper |
| `tests/test_api.py` | Replace `== "0.5.0"` assertion with dynamic read from `config.yaml` |
| `scripts/release.py` | Create new file (standalone, stdlib only) |
| `CLAUDE.md` | Append `## Release Procedure` section |
| `CHANGELOG.md` | Backfill `0.4.0`, `0.4.2`, `0.5.0` entries (currently stops at `0.3.0`) |

---

## Error Handling

- **Script exits non-zero:** Claude reports the exact failing step. User decides whether to fix and retry or abort.
- **`gh` CLI not installed:** step 10 prints a manual command to run and exits non-zero. The tag and push (steps 7–8) are already done, so the GitHub Release can be created manually.
- **YAML-mode HA (no Lovelace API):** handled separately by the existing `_register_lovelace_card` startup function — not part of release scope.
- **Dirty git tree:** script aborts at step 4 with a list of unexpected files. Claude must commit or stash them before retrying.

---

## Testing

The `release.py` script is tested via `tests/test_release_script.py`:

| Test | Scenario |
|------|----------|
| `test_valid_semver` | `1.2.3` passes, `1.2`, `v1.2.3`, `abc` rejected |
| `test_version_mismatch_aborts` | `--version 9.9.9` when config.yaml has `0.5.0` → exit 1 |
| `test_missing_changelog_section_aborts` | no `## [X.Y.Z]` in CHANGELOG → exit 1 |
| `test_dry_run_no_git_calls` | `--dry-run` → subprocess never called with `git commit` |
| `test_extract_changelog_section` | correctly extracts body between two `## [` headings |

`server.py` and `test_api.py` changes are covered by the existing `test_api.py::test_health` test (now reads version dynamically).

---

## Out of Scope

- Automated version bump on PR merge (CI/CD pipeline) — Phase 2
- Semantic release tools (semantic-release, commitizen) — YAGNI for now
- Multiple release channels (beta, stable) — YAGNI for now
