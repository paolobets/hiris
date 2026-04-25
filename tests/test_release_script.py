# tests/test_release_script.py
"""Unit tests for scripts/release.py — the HIRIS mechanical release script."""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def test_config_file_not_found_aborts(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    with patch.object(rel, "CONFIG", missing):
        with pytest.raises(SystemExit):
            rel.check_config_version("0.6.0")


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
    # The branch-detection call (git rev-parse) is read-only and always runs.
    # All other git mutating commands must be skipped in dry-run mode.
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="master\n", returncode=0)
        rel.git_commit_and_tag("0.6.0", dry_run=True)
    # Only the one read-only branch-detection call is expected
    assert mock_run.call_count == 1, (
        f"Only the branch-detection subprocess.run call is allowed in dry-run mode, "
        f"got {mock_run.call_count}"
    )


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


# ---------------------------------------------------------------------------
# check_git_clean
# ---------------------------------------------------------------------------

def test_git_clean_passes_when_only_release_files_dirty():
    """Only config.yaml and CHANGELOG.md dirty → should not exit."""
    porcelain = " M hiris/config.yaml\n M CHANGELOG.md\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=porcelain, returncode=0)
        rel.check_git_clean()  # must not exit


def test_git_clean_aborts_on_unexpected_dirty_file():
    """Any other dirty file → should exit."""
    porcelain = " M hiris/config.yaml\n M hiris/app/server.py\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=porcelain, returncode=0)
        with pytest.raises(SystemExit):
            rel.check_git_clean()
