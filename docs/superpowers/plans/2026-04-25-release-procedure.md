# HIRIS Release Procedure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a structured HIRIS release procedure: single-source versioning from `config.yaml`, a `scripts/release.py` mechanical executor, and a Claude release checklist in `CLAUDE.md`.

**Architecture:** `config.yaml` is the only file where the version lives; a `hiris/app/version.py` helper reads it at runtime so `server.py` and `handlers_status.py` are always in sync. `scripts/release.py` runs 10 ordered checks before every push (validate semver → verify changelog → run tests → git tag → GitHub Release). `CLAUDE.md` gains a `## Release Procedure` section that Claude follows to write the changelog and invoke the script.

**Tech Stack:** Python 3.11+ stdlib only (`re`, `pathlib`, `subprocess`, `argparse`), `gh` CLI for GitHub Releases, `pytest` for tests, `git` via subprocess (never PowerShell — antivirus constraint).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `hiris/app/version.py` | **Create** | Single `read_version()` function, reads `config.yaml` via regex |
| `hiris/app/server.py` | **Modify** (line 298) | Import `read_version`, replace hardcoded `"0.5.0"` in `_handle_health` |
| `hiris/app/api/handlers_status.py` | **Modify** (line 9) | Import `read_version`, replace hardcoded `"0.0.8"` in `handle_status` |
| `tests/test_api.py` | **Modify** (line 55) | Replace `== "0.5.0"` with dynamic read from `config.yaml` |
| `scripts/release.py` | **Create** | 10-step release script (validate → test → git → gh release) |
| `tests/test_release_script.py` | **Create** | 9 unit tests covering all script logic branches |
| `CHANGELOG.md` | **Modify** | Backfill missing entries (0.4.0 → 0.5.1) |
| `CLAUDE.md` | **Modify** | Append `## Release Procedure` section |

---

## Task 1: Single-Source Version Helper

**Files:**
- Create: `hiris/app/version.py`
- Modify: `hiris/app/server.py` (line 298 — `_handle_health`)
- Modify: `hiris/app/api/handlers_status.py` (line 9 — `handle_status`)
- Modify: `tests/test_api.py` (line 55 — `test_health_endpoint`)

**Context:** Currently `"0.5.0"` is hardcoded in `server.py:298` and `"0.0.8"` (wrong!) is hardcoded in `handlers_status.py:9`. Both must read from `config.yaml` dynamically so bumping one file is enough.

- [ ] **Step 1: Write the failing test for `read_version()`**

Add to `tests/test_api.py` at the top (after the imports), replacing lines 54-55:

```python
import re
import pathlib

def _cfg_version() -> str:
    cfg = pathlib.Path(__file__).parent.parent / "hiris" / "config.yaml"
    m = re.search(r'^version:\s*"([^"]+)"', cfg.read_text(), re.MULTILINE)
    return m.group(1) if m else "unknown"
```

Then change the assertion on line 55 from:
```python
    assert data["version"] == "0.5.0"
```
to:
```python
    assert data["version"] == _cfg_version()
```

- [ ] **Step 2: Run the test to verify it still passes (it reads config.yaml = 0.5.0)**

```
py -m pytest tests/test_api.py::test_health_endpoint -v
```
Expected: PASS (config.yaml still has 0.5.0, both sides agree)

- [ ] **Step 3: Create `hiris/app/version.py`**

```python
# hiris/app/version.py
"""Single source of truth for the HIRIS version.

Reads the version field from hiris/config.yaml at import time using a
lightweight regex — no YAML parser dependency required.
"""
import re
import pathlib

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"


def read_version() -> str:
    """Return the version string from config.yaml, e.g. '0.5.0'.

    Returns 'unknown' if the file cannot be read or the field is missing.
    This function is safe to call at module import time.
    """
    try:
        text = _CONFIG_PATH.read_text(encoding="utf-8")
        m = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"
```

- [ ] **Step 4: Update `hiris/app/server.py` — replace hardcoded version in `_handle_health`**

Add the import after the existing imports (around line 6, after `from aiohttp import web`):
```python
from .version import read_version
```

Replace the body of `_handle_health` (currently line 298):
```python
async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": read_version()})
```

- [ ] **Step 5: Update `hiris/app/api/handlers_status.py` — replace hardcoded `"0.0.8"`**

Full file after edit:
```python
# hiris/app/api/handlers_status.py
from aiohttp import web
from ..version import read_version


async def handle_status(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    agents = engine.list_agents()
    return web.json_response({
        "version": read_version(),
        "agents": {
            "total": len(agents),
            "enabled": sum(1 for a in agents.values() if a["enabled"]),
        },
    })
```

- [ ] **Step 6: Run all tests — verify green**

```
py -m pytest --tb=short -q
```
Expected: all tests pass (same count as before, 343+)

- [ ] **Step 7: Commit**

```bash
git add hiris/app/version.py hiris/app/server.py hiris/app/api/handlers_status.py tests/test_api.py
git commit -m "refactor: read version from config.yaml at runtime (single source of truth)"
```

---

## Task 2: `tests/test_release_script.py` — Tests First

**Files:**
- Create: `tests/test_release_script.py`

**Context:** The release script doesn't exist yet. Write the tests first so we know exactly what behaviour to implement in Task 3. The test file uses `sys.path.insert` to import from `scripts/release.py` without installing it as a package.

- [ ] **Step 1: Create `tests/test_release_script.py`**

```python
# tests/test_release_script.py
"""Unit tests for scripts/release.py — the HIRIS mechanical release script."""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, call

# Import release.py from scripts/ directory (not a package)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import release as rel  # noqa: E402


# ---------------------------------------------------------------------------
# validate_semver
# ---------------------------------------------------------------------------

def test_valid_semver_accepted():
    rel.validate_semver("1.2.3")   # must not raise / exit


def test_semver_missing_patch_rejected():
    with pytest.raises(SystemExit):
        rel.validate_semver("1.2")


def test_semver_v_prefix_rejected():
    with pytest.raises(SystemExit):
        rel.validate_semver("v1.2.3")


def test_semver_text_rejected():
    with pytest.raises(SystemExit):
        rel.validate_semver("abc")


# ---------------------------------------------------------------------------
# check_config_version
# ---------------------------------------------------------------------------

def test_version_match_passes(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text('version: "0.6.0"\n')
    with patch.object(rel, "CONFIG", cfg):
        rel.check_config_version("0.6.0")  # must not exit


def test_version_mismatch_aborts(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text('version: "0.5.0"\n')
    with patch.object(rel, "CONFIG", cfg):
        with pytest.raises(SystemExit):
            rel.check_config_version("9.9.9")


# ---------------------------------------------------------------------------
# check_changelog
# ---------------------------------------------------------------------------

def test_changelog_section_present_passes(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [0.6.0] — 2026-04-25\n### Added\n- stuff\n")
    with patch.object(rel, "CHANGELOG", cl):
        rel.check_changelog("0.6.0")  # must not exit


def test_missing_changelog_section_aborts(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [0.5.0] — 2026-04-20\n")
    with patch.object(rel, "CHANGELOG", cl):
        with pytest.raises(SystemExit):
            rel.check_changelog("0.6.0")


# ---------------------------------------------------------------------------
# dry_run — no git subprocess calls
# ---------------------------------------------------------------------------

def test_dry_run_no_git_calls():
    with patch("subprocess.run") as mock_run:
        rel.git_commit_and_tag("0.6.0", dry_run=True)
    for c in mock_run.call_args_list:
        args = c[0][0] if c[0] else c[1].get("args", [])
        assert "commit" not in args, "git commit must not run in dry-run mode"


# ---------------------------------------------------------------------------
# extract_changelog_section
# ---------------------------------------------------------------------------

def test_extract_changelog_section(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n"
        "## [0.6.0] — 2026-04-25\n### Added\n- feature A\n\n"
        "## [0.5.0] — 2026-04-20\n### Fixed\n- bug B\n"
    )
    with patch.object(rel, "CHANGELOG", cl):
        section = rel.extract_changelog_section("0.6.0")
    assert "## [0.6.0]" in section
    assert "feature A" in section
    assert "bug B" not in section, "Must not include next version's content"
```

- [ ] **Step 2: Run the tests — verify they all FAIL (script doesn't exist yet)**

```
py -m pytest tests/test_release_script.py -v
```
Expected: `ModuleNotFoundError: No module named 'release'` or `ImportError` — this confirms the tests are real.

- [ ] **Step 3: Create the `scripts/` directory**

```bash
mkdir -p scripts
```

- [ ] **Step 4: Commit the test file alone**

```bash
git add tests/test_release_script.py
git commit -m "test: add release script tests (TDD — script not yet implemented)"
```

---

## Task 3: Implement `scripts/release.py`

**Files:**
- Create: `scripts/release.py`

**Context:** Implement the script so all 9 tests from Task 2 pass. The script must use `subprocess.run` with list args (never `shell=True`, never PowerShell) — antivirus constraint. Colors via ANSI escapes only (no external libs).

- [ ] **Step 1: Create `scripts/release.py`**

```python
#!/usr/bin/env python3
"""HIRIS release script — mechanical release executor.

Usage:
  python scripts/release.py --version X.Y.Z           # standard release
  python scripts/release.py --version X.Y.Z --dry-run  # preview, no git ops
  python scripts/release.py --version X.Y.Z --skip-tests  # hotfix only

Steps (abort on first failure):
  1  Validate semver X.Y.Z
  2  Check config.yaml version matches --version
  3  Check CHANGELOG.md has ## [X.Y.Z] section
  4  Check git tree clean (only config.yaml / CHANGELOG.md allowed dirty)
  5  Run pytest (skipped with --skip-tests)
  6  git add + commit chore: release vX.Y.Z
  7  git tag vX.Y.Z
  8  git push origin master --tags
  9  Extract changelog section for X.Y.Z
  10 gh release create vX.Y.Z with extracted notes
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "hiris" / "config.yaml"
CHANGELOG = ROOT / "CHANGELOG.md"

_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}✓{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}✗{_RESET} {msg}")
    sys.exit(1)


def _info(msg: str) -> None:
    print(f"{_YELLOW}→{_RESET} {msg}")


# ---------------------------------------------------------------------------
# Step 1
# ---------------------------------------------------------------------------

def validate_semver(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        _fail(f"Invalid semver: '{version}' — expected X.Y.Z (e.g. 1.2.3, not v1.2.3)")
    _ok(f"Semver valid: {version}")


# ---------------------------------------------------------------------------
# Step 2
# ---------------------------------------------------------------------------

def check_config_version(version: str) -> None:
    try:
        text = CONFIG.read_text(encoding="utf-8")
    except FileNotFoundError:
        _fail(f"config.yaml not found at {CONFIG}")
    m = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        _fail("Cannot find version field in hiris/config.yaml")
    current = m.group(1)
    if current != version:
        _fail(
            f"config.yaml version is '{current}', expected '{version}'\n"
            f"  Update hiris/config.yaml → version: \"{version}\" first."
        )
    _ok(f"config.yaml version matches: {version}")


# ---------------------------------------------------------------------------
# Step 3
# ---------------------------------------------------------------------------

def check_changelog(version: str) -> None:
    try:
        text = CHANGELOG.read_text(encoding="utf-8")
    except FileNotFoundError:
        _fail(f"CHANGELOG.md not found at {CHANGELOG}")
    if f"## [{version}]" not in text:
        _fail(
            f"CHANGELOG.md missing section '## [{version}]'\n"
            f"  Write the changelog entry before running this script."
        )
    _ok(f"CHANGELOG.md has section for {version}")


# ---------------------------------------------------------------------------
# Step 4
# ---------------------------------------------------------------------------

def check_git_clean() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=ROOT,
    )
    allowed = {"config.yaml", "CHANGELOG.md"}
    dirty = [
        line for line in result.stdout.splitlines()
        if line.strip() and not any(pat in line for pat in allowed)
    ]
    if dirty:
        _fail(
            "Unexpected dirty files (commit or stash them first):\n  "
            + "\n  ".join(dirty)
        )
    _ok("Git working tree clean")


# ---------------------------------------------------------------------------
# Step 5
# ---------------------------------------------------------------------------

def run_tests() -> None:
    _info("Running pytest…")
    result = subprocess.run(
        ["py", "-m", "pytest", "--tb=short", "-q"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        _fail("Tests failed — fix before releasing")
    _ok("All tests pass")


# ---------------------------------------------------------------------------
# Steps 6-8
# ---------------------------------------------------------------------------

def git_commit_and_tag(version: str, dry_run: bool) -> None:
    cmds = [
        ["git", "add", "hiris/config.yaml", "CHANGELOG.md"],
        ["git", "commit", "-m", f"chore: release v{version}"],
        ["git", "tag", f"v{version}"],
        ["git", "push", "origin", "master", "--tags"],
    ]
    for cmd in cmds:
        if dry_run:
            _info(f"[dry-run] {' '.join(cmd)}")
            continue
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            _fail(f"Command failed: {' '.join(cmd)}")
    if not dry_run:
        _ok(f"Committed, tagged v{version}, pushed to origin/master")


# ---------------------------------------------------------------------------
# Step 9
# ---------------------------------------------------------------------------

def extract_changelog_section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    pattern = rf"(## \[{re.escape(version)}\].*?)(?=\n## \[|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        _fail(f"Cannot extract changelog section for {version} from CHANGELOG.md")
    return m.group(1).strip()


# ---------------------------------------------------------------------------
# Step 10
# ---------------------------------------------------------------------------

def create_github_release(version: str, notes: str, dry_run: bool) -> None:
    cmd = [
        "gh", "release", "create", f"v{version}",
        "--title", f"HIRIS v{version}",
        "--notes", notes,
    ]
    if dry_run:
        _info(f"[dry-run] gh release create v{version}")
        _info(f"Release notes preview:\n{notes[:400]}")
        return
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        _fail(
            f"gh release create failed.\n"
            f"  Create the release manually at:\n"
            f"  https://github.com/paolobets/hiris/releases/new?tag=v{version}"
        )
    _ok(f"GitHub Release v{version} created")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HIRIS mechanical release executor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", required=True, metavar="X.Y.Z",
                        help="Target release version (e.g. 0.6.0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview steps 6–10, no git/gh operations")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip pytest (emergency hotfix only)")
    args = parser.parse_args()

    if args.dry_run:
        _info("DRY RUN — steps 6–10 will be printed but not executed\n")

    validate_semver(args.version)          # step 1
    check_config_version(args.version)     # step 2
    check_changelog(args.version)          # step 3
    check_git_clean()                      # step 4
    if args.skip_tests:
        _info("Skipping pytest (--skip-tests)")
    else:
        run_tests()                        # step 5
    git_commit_and_tag(args.version, args.dry_run)   # steps 6-8
    notes = extract_changelog_section(args.version)  # step 9
    create_github_release(args.version, notes, args.dry_run)  # step 10

    print(f"\n{_GREEN}{'[DRY RUN] ' if args.dry_run else ''}Release v{args.version} completato ✓{_RESET}")
    if not args.dry_run:
        print("HA Supervisor rileverà l'aggiornamento al prossimo check (ogni ~24h).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the tests — verify all 9 pass**

```
py -m pytest tests/test_release_script.py -v
```
Expected: 9 passed

- [ ] **Step 3: Run the full suite — verify nothing regressed**

```
py -m pytest --tb=short -q
```
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add scripts/release.py
git commit -m "feat: add scripts/release.py mechanical release executor (10-step)"
```

---

## Task 4: CHANGELOG Backfill + CLAUDE.md Release Checklist

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

**Context:** `CHANGELOG.md` is stuck at `0.3.0` but the codebase is at `0.5.0+`. The missing versions need entries. Also, `CLAUDE.md` needs a `## Release Procedure` section so Claude knows what to do when asked for a release.

### Part A — CHANGELOG backfill

- [ ] **Step 1: Gather commits since 0.3.0**

Run:
```bash
git log --oneline
```
Look for commit messages to identify what was built in each version. Group by approximate milestone. The versions to backfill are: `0.4.0`, `0.4.2`, `0.5.0`, `0.5.1`.

- [ ] **Step 2: Add missing entries to `CHANGELOG.md`**

Insert the following block **immediately after** the `# HIRIS — Changelog` heading and before the existing `## [0.3.0]` entry. Adjust dates and content based on what you found in the git log (the entries below are based on known project context — verify and refine):

```markdown
## [0.5.1] — 2026-04-25

### Added
- **Lovelace card auto-registration** — on startup HIRIS calls `POST /api/lovelace/resources` (via Supervisor token) to register `hiris-chat-card.js` as a UI module; idempotent, graceful in YAML-mode HA

### Changed
- Version is now read dynamically from `config.yaml` at runtime; `server.py` and `handlers_status.py` no longer hardcode it

## [0.5.0] — 2026-04-25

### Added
- **X-HIRIS-Internal-Token middleware** — HMAC-validated auth for inter-add-on requests (non-Ingress)
- **Enriched `/api/agents` response** — includes `status`, `budget_eur`, `budget_limit_eur` for Lovelace dashboard
- **SSE streaming for `/api/chat`** — Server-Sent Events path when `stream: true` or `Accept: text/event-stream`; Phase 1 pseudo-streaming (full response sliced into 80-char tokens)
- **`hiris-chat-card.js`** — vanilla JS Lovelace custom card (shadow DOM, polling, SSE streaming, budget bar, toggle enable/disable)
- **MQTT Discovery publisher** — publishes `sensor.hiris_*_status/budget_eur/last_run` and `switch.hiris_*_enabled` via aiomqtt; exponential backoff reconnect; discovery messages queue during initial backoff

### Changed
- `config.yaml`: added `internal_token`, `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` options
- `AgentEngine`: tracks running/error status per agent; publishes MQTT state on each run

## [0.4.2] — 2026-04-24

### Fixed
- `internal_token` option uses `password` schema in `config.yaml` (masked in HA UI)
- HMAC comparison uses `hmac.compare_digest` (constant-time, prevents timing attacks)

## [0.4.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex; organizes entities by area using `device_class` + domain classification; ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations
- **TaskEngine** — shared deferred-task system; 4 trigger types (`delay`, `at_time`, `at_datetime`, `time_window`); 3 action types; task persistence in `/data/tasks.json`
- **LLM Router** — routes standard inference to Claude, offloads `classify_entities()` to local Ollama when `LOCAL_MODEL_URL` configured
- **Task UI** — "Task" tab with pending-count badge; active + recent task list; cancel button; auto-refresh every 30s

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

```

- [ ] **Step 3: Verify CHANGELOG looks correct**

```bash
head -80 CHANGELOG.md
```
Confirm the new entries appear before `## [0.3.0]`.

### Part B — CLAUDE.md release checklist

- [ ] **Step 4: Append the release checklist to `CLAUDE.md`**

Add the following block at the **end** of `CLAUDE.md`:

```markdown

---

## Release Procedure

Follow these steps **in order** whenever asked for a release ("fai il release", "prepara la X.Y.Z", "rilascia", "nuova versione"):

### Step 1 — Scope commits
```bash
git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --oneline
```
Collect all commits since the last tag (or since repo start if no tags yet).

### Step 2 — Propose version
Determine bump type:
- Any `feat:` or `feat(...):` → minimum **minor** bump (0.5.x → 0.6.0)
- Any `BREAKING CHANGE` or `!:` → **major** bump
- Only `fix:`, `chore:`, `docs:`, `test:` → **patch** bump (0.5.0 → 0.5.1)

Show proposed version to user. Wait for confirmation. User may override.

### Step 3 — Draft CHANGELOG section
Generate a Keep-a-Changelog section and show it to the user:
```
## [X.Y.Z] — YYYY-MM-DD

### Added      ← feat: commits
### Fixed      ← fix: commits
### Changed    ← refactor:, perf: commits
### Removed    ← commits that delete features
```
Wait for user approval. Incorporate any edits.

### Step 4 — Update files (after user approves)
a. Insert the approved section into `CHANGELOG.md` immediately after the `# HIRIS — Changelog` heading line.
b. Update `hiris/config.yaml` → `version: "X.Y.Z"`.

### Step 5 — Run release script (Bash only — never PowerShell)
```bash
python scripts/release.py --version X.Y.Z
```

### Step 6 — Report
Show full script output to the user.
- Exit 0 → announce "Release vX.Y.Z completato ✓ — HA rileverà l'aggiornamento al prossimo check."
- Non-zero → show the failing step. **Do NOT retry automatically.** Wait for the user to fix the issue.
```

- [ ] **Step 5: Run the full test suite one final time**

```
py -m pytest --tb=short -q
```
Expected: all tests pass

- [ ] **Step 6: Commit everything**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -m "docs: backfill CHANGELOG 0.4.0-0.5.1, add Claude release checklist to CLAUDE.md"
```

---

## Smoke Test (non-automated)

After all tasks are complete, verify the release script works end-to-end with dry-run:

```bash
python scripts/release.py --version 0.5.1 --dry-run
```

Expected output (all green checkmarks, no real git ops):
```
→ DRY RUN — steps 6–10 will be printed but not executed
✓ Semver valid: 0.5.1
✓ config.yaml version matches: 0.5.1
✓ CHANGELOG.md has section for 0.5.1
✓ Git working tree clean
→ Running pytest…
✓ All tests pass
→ [dry-run] git add hiris/config.yaml CHANGELOG.md
→ [dry-run] git commit -m chore: release v0.5.1
→ [dry-run] git tag v0.5.1
→ [dry-run] git push origin master --tags
→ [dry-run] gh release create v0.5.1
→ Release notes preview: ...
[DRY RUN] Release v0.5.1 completato ✓
```

If this passes, the release procedure is fully operational.
