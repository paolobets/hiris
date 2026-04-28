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
  8  git push HEAD:master --tags  (always targets master, worktree-safe)
  9  Extract changelog section for X.Y.Z
  10 gh release create vX.Y.Z with extracted notes
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows (cp1252 terminals can't encode ✓/✗/→)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
        text = CHANGELOG.read_text(encoding="utf-8", errors="replace")
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
    # git status --porcelain format: "XY PATH" or "XY OLD_PATH -> NEW_PATH"
    # Allow only the exact relative paths for our release files
    _ALLOWED = {"hiris/config.yaml", "CHANGELOG.md"}

    def _extract_path(line: str) -> str:
        # Strip the 2-char status + space prefix, handle renames
        return line[3:].strip().split(" -> ")[-1]

    dirty = [
        line for line in result.stdout.splitlines()
        if line.strip() and _extract_path(line) not in _ALLOWED
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
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        _fail("Tests failed — fix before releasing")
    _ok("All tests pass")


# ---------------------------------------------------------------------------
# Steps 6-8
# ---------------------------------------------------------------------------

def git_commit_and_tag(version: str, dry_run: bool) -> None:
    # Always push HEAD to master regardless of the working branch/worktree.
    # "HEAD:master" is a refspec that fast-forwards remote master to the
    # current commit without requiring a local checkout of master.
    cmds = [
        ["git", "add", "hiris/config.yaml", "CHANGELOG.md"],
        ["git", "commit", "-m", f"chore: release v{version}"],
        ["git", "tag", f"v{version}"],
        ["git", "push", "origin", "HEAD:master", "--tags"],
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
    text = CHANGELOG.read_text(encoding="utf-8", errors="replace")
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
