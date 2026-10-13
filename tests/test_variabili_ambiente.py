"""Ogni variabile d'ambiente letta dal prodotto ha una provenienza dichiarata (F-10).

*«Una env var che `run.sh` non esporta è di fatto una costante»* (CLAUDE.md).
Il censimento le trova (`envvar-mai-esportata`) ma non ferma: una parte arriva
da fuori, e lui non la distingue. Qui la distinzione si scrive: ogni variabile
letta dal codice o la esporta `run.sh` (un'opzione dell'add-on), o sta in
`FROM_OUTSIDE` con la sua provenienza. Una lettura nuova che non e' nessuna delle
due e' rossa: o diventa un'opzione, o una costante.

Le letture e gli export si CHIEDONO al censimento
(`censimento.censisci_configurazione`), non si ricopiano qui.

Fino alla Chiusura (F5, 13/10/2026) leggeva l'ambiente anche `HIRIS_SLUG`, la
cartella della vecchia card che nessuno esportava: e' diventata la costante
`action/installation.CARD_FOLDER`.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "censimento", ROOT / "scripts" / "censimento.py")
censimento = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("censimento", censimento)
_SPEC.loader.exec_module(censimento)

#: Lista di AMMISSIONE: le variabili che il prodotto legge e `run.sh` non
#: esporta, ognuna con la sua provenienza. Una voce si toglie quando la
#: lettura esce, e la prova lo pretende.
FROM_OUTSIDE: dict[str, str] = {
    "SUPERVISOR_TOKEN": (
        "la mette il Supervisor nell'ambiente dell'add-on: e' il gettone con "
        "cui HIRIS parla con Home Assistant e col Supervisor"),
    "HOME": "il sistema del container: l'ambiente della CLI del ponte",
    "PATH": "il sistema del container: l'ambiente della CLI del ponte",
    "HIRIS_ALLOW_NO_TOKEN": (
        "valvola di sviluppo: la accendono la suite (`conftest.py`) e la CI, "
        "mai l'add-on; spegne l'autenticazione e lo grida nel registro"),
    "HIRIS_ALLOW_NO_CSRF": (
        "valvola di sviluppo: la accendono la suite e la CI, mai l'add-on"),
    "HIRIS_DATA_DIR": (
        "valvola di sviluppo: la suite (`conftest.py`) e la fotografia delle "
        "porte spostano `/data` in una cartella temporanea"),
    "HA_BASE_URL": (
        "valvola di sviluppo: la fotografia delle porte punta il client a un "
        "indirizzo che non risponde; in produzione e' `http://supervisor/core`"),
    "HIRIS_AGENT_MODE": (
        "valvola delle prove: `dry-run` fa girare il lavoratore del ponte "
        "senza la CLI (`test_agent_worker_startup.py`)"),
}


def _not_exported() -> set[str]:
    findings = censimento.censisci_configurazione(
        ROOT / "hiris" / "config.yaml", ROOT / "hiris" / "run.sh",
        censimento._file_py(censimento.APP))
    return {f.nome for f in findings if f.categoria == "envvar-mai-esportata"}


def test_la_derivazione_vede_le_letture():
    """Un insieme vuoto sarebbe un cancello che non guarda piu' niente."""
    assert "SUPERVISOR_TOKEN" in _not_exported()


def test_ogni_variabile_non_esportata_ha_una_provenienza():
    """Mutazione ESEGUITA (13/10/2026): rimessa in `action/installation.py`
    la lettura `os.environ.get("HIRIS_SLUG", "hiris")` -- rossa, e la nomina."""
    extra = sorted(_not_exported() - set(FROM_OUTSIDE))
    assert not extra, (
        f"{extra}: il prodotto le legge e `run.sh` non le esporta. Una "
        "variabile cosi' e' una costante: o diventa un'opzione dell'add-on "
        "(prima nella UI), o una costante, o si dichiara in FROM_OUTSIDE")


def test_ogni_provenienza_e_ancora_vera():
    stale = sorted(set(FROM_OUTSIDE) - _not_exported())
    assert not stale, f"{stale}: nessuno le legge piu', o run.sh le esporta"
