# tests/test_release_script.py
"""Unit tests for scripts/release.py — the HIRIS mechanical release script."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import release.py from scripts/ directory (not a package)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import release as rel

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
    with patch.object(rel, "CONFIG", cfg), pytest.raises(SystemExit):
        rel.check_config_version("9.9.9")


def test_config_file_not_found_aborts(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    with patch.object(rel, "CONFIG", missing), pytest.raises(SystemExit):
        rel.check_config_version("0.6.0")


# ---------------------------------------------------------------------------
# check_changelog
# ---------------------------------------------------------------------------

def test_changelog_section_present_passes(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [0.6.0] — 2026-04-25\n### Added\n- stuff\n")
    with patch.object(rel, "CHANGELOG", cl):
        rel.check_changelog("0.6.0")  # must not exit


def test_una_sezione_non_rilasciato_ferma_il_rilascio(tmp_path):
    """Il cancello: `extract_changelog_section` estrae SOLO `## [X.Y.Z]` e
    ignora cio' che le sta sopra, quindi una sezione «Non rilasciato» lasciata
    li' resterebbe orfana per sempre e fuori dalle note di rilascio. Provato
    per mutazione: tolto il controllo da `check_changelog`, questo test passa
    invece di fallire."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# HIRIS\n\n## [Non rilasciato]\n\nun cambio di comportamento\n\n"
                  "## [0.6.0]\n\nnote\n", encoding="utf-8")
    with patch.object(rel, "CHANGELOG", cl), pytest.raises(SystemExit):
        rel.check_changelog("0.6.0")


def test_senza_sezione_non_rilasciato_il_controllo_passa(tmp_path):
    """Il contrario, perche' un cancello che ferma sempre non e' un cancello."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# HIRIS\n\n## [0.6.0]\n\nnote\n", encoding="utf-8")
    with patch.object(rel, "CHANGELOG", cl):
        rel.check_changelog("0.6.0")  # non deve uscire


def test_missing_changelog_section_aborts(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [0.5.0] — 2026-04-20\n")
    with patch.object(rel, "CHANGELOG", cl), pytest.raises(SystemExit):
        rel.check_changelog("0.6.0")


# ---------------------------------------------------------------------------
# dry_run — no git subprocess calls
# ---------------------------------------------------------------------------

def test_dry_run_no_git_calls():
    # In dry-run mode all git mutating commands must be skipped entirely.
    # No subprocess.run calls expected (branch detection was removed).
    with patch("subprocess.run") as mock_run:
        rel.git_commit_and_tag("0.6.0", dry_run=True)
    assert mock_run.call_count == 0, (
        f"No subprocess.run calls expected in dry-run mode, got {mock_run.call_count}"
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


# ---------------------------------------------------------------------------
# il registro dei doppioni segue il rilascio (N74-3, scelta di Paolo 07/10/2026)
# ---------------------------------------------------------------------------

_REGISTER = (
    "## A. Leggere\n\n| Id | Voce | Stato | Unirla | Fonti |\n|---|---|---|---|---|\n"
    "| A-01 | prima | E | PS | reg · **chiudibile al rilascio** `abc1234`: copia tolta |\n"
    "| A-03 | terza | D | CC | reg |\n\n"
    "## Chiuse\n\n| Id | Voce | Chiusa con | Commit | Cosa |\n|---|---|---|---|---|\n"
    "| A-04 | quarta | Tappa 6, Task 7 | 2222222 | tolta prima del rilascio |\n")


def test_il_rilascio_chiude_le_voci_segnate_del_registro(tmp_path):
    """Mutazione ESEGUITA: tolta da `close_register` la chiamata a
    `registro.release` -- rossa (A-01 resta aperta)."""
    document = tmp_path / "registro.md"
    document.write_text(_REGISTER, encoding="utf-8")
    with patch.object(rel, "REGISTER", document):
        rel.close_register("3.78.0", dry_run=False)
    entries = {entry.id: entry for entry in rel.registro.read_entries(document)}
    assert entries["A-01"].closed and entries["A-01"].cells[2] == "3.78.0"
    assert entries["A-04"].cells[2] == "3.78.0"
    assert not entries["A-03"].closed


def test_in_prova_il_registro_non_si_scrive(tmp_path, capsys):
    """Mutazione ESEGUITA: in `close_register` saltato il ramo della prova --
    rossa (il registro e' stato scritto)."""
    document = tmp_path / "registro.md"
    document.write_text(_REGISTER, encoding="utf-8")
    with patch.object(rel, "REGISTER", document):
        rel.close_register("3.78.0", dry_run=True)
    assert document.read_text(encoding="utf-8") == _REGISTER
    assert "A-01" in capsys.readouterr().out


def test_il_registro_entra_nel_commit_del_rilascio():
    """Il registro scritto dal rilascio e lasciato fuori dal `git add` sarebbe
    un file sporco dopo il tag: la versione nel registro e quella nel tag
    devono stare nello stesso commit.
    Mutazione ESEGUITA: tolto il registro dalla lista -- rossa."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        rel.git_commit_and_tag("3.78.0", dry_run=False)
    add = mock_run.call_args_list[0].args[0]
    assert add[:2] == ["git", "add"]
    assert "docs/design/2026-10-01-registro-dei-doppioni.md" in add
