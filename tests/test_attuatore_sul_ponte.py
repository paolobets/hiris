"""L'attuatore sul ponte: la specie che il server accodava e nessuno ragionava.

**Misurato dal vivo il 28/09/2026 nel registro dell'add-on (3.69.0).** Ogni ora
`server.py::_enqueue_actuator_turn` accodava un turno `attuazione`; il runner
del ponte ragiona solo `RAGIONABILI`, e per quella specie scriveva «job
non-chat in coda: nessun ramo lo ragiona piu'» e restituiva una decisione
vuota. Dalla 3.56.0 (21/09) sul ponte l'attuatore non ha mai prodotto niente.

E' la **seconda volta** dello stesso difetto: il 13/09 le ricette. Il 15/09
l'analista entro' «insieme al modulo che la produce» proprio per non
ripeterlo -- ma la difesa era una riga di prova scritta a mano per QUELLA
specie, e la specie successiva e' nata senza la sua.

Qui il cancello **chiede il suo elenco** (CLAUDE.md, I-0): le specie non si
ricopiano, si ricavano da ogni `.enqueue(` in `hiris/app`, e ognuna deve essere
ragionata dal ponte e avere un nome nel registro dei turni.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

from hiris.app.agent import runner as ponte

RADICE = Path(__file__).resolve().parent.parent
APP = RADICE / "hiris" / "app"


def _modulo(percorso: Path) -> str:
    return ".".join(percorso.relative_to(RADICE).with_suffix("").parts)


def _risolvi(nodo: ast.expr, spazio: dict):
    """Il valore del primo argomento di `.enqueue(`, chiesto al modulo vivo.

    Si risolve **nello spazio dei nomi del modulo che accoda**: un letterale
    vale se stesso, `SCOPE_TURN_KIND` e `proposer_turn.PROPOSAL_TURN_KIND`
    valgono cio' che valgono li'. Ricostruire gli import a mano sarebbe una
    seconda risoluzione dei nomi, cioe' un doppione di Python.
    """
    if isinstance(nodo, ast.Constant):
        return nodo.value
    if isinstance(nodo, ast.Name):
        return spazio[nodo.id]
    if isinstance(nodo, ast.Attribute):
        return getattr(_risolvi(nodo.value, spazio), nodo.attr)
    raise AssertionError(
        f"non so risolvere la specie accodata `{ast.unparse(nodo)}`: il "
        "cancello non puo' ricavarla, e un cancello che salta cio' che non "
        "capisce sembra vivo e non guarda")


def specie_accodate() -> dict[str, list[str]]:
    """`{specie: [dove]}` -- ogni `kind` che il codice accoda nella coda del
    ragionamento, RICAVATO dal sorgente e non elencato."""
    trovate: dict[str, list[str]] = {}
    for percorso in sorted(APP.rglob("*.py")):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        chiamate = [n for n in ast.walk(albero)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "enqueue"]
        if not chiamate:
            continue
        spazio = vars(importlib.import_module(_modulo(percorso)))
        for chiamata in chiamate:
            primo = (chiamata.args[0] if chiamata.args
                     else next(k.value for k in chiamata.keywords if k.arg == "kind"))
            dove = f"{percorso.relative_to(RADICE).as_posix()}:{chiamata.lineno}"
            trovate.setdefault(_risolvi(primo, spazio), []).append(dove)
    return trovate


def test_la_derivazione_trova_TUTTE_le_specie_che_si_accodano():
    """La prova che la derivazione non si e' rotta: un insieme improvvisamente
    piccolo e' un cancello che sembra vivo e non guarda piu' niente.

    Le sei specie sono quelle accodate il 28/09/2026 -- chat, promessa, scope,
    ricetta, analisi, attuazione -- e sono il pavimento, non il tetto: una
    specie nuova entra nel cancello qui sotto da sola.
    """
    trovate = specie_accodate()
    assert {"chat", "promessa", "scope", "ricetta", "analisi",
            "proposta"} <= set(trovate), (
        f"ho ricavato solo {sorted(trovate)}: la derivazione si e' rotta")


def test_ogni_specie_ACCODATA_e_ragionata_dal_ponte_e_ha_un_nome_nel_registro():
    """Il cancello. Una specie accodata e non ragionata e' una domanda che
    nessuno risponde, e il giro che la aspetta resta muto **per sempre**, senza
    un errore: la decisione vuota e' indistinguibile da «niente da dire».

    Mutazione ESEGUITA: togliere `attuazione` da `RAGIONABILI` (e da
    `JOB_SPECIES`) -- rossa, col nome della specie e della riga che la accoda.
    """
    for specie, dove in specie_accodate().items():
        assert specie in ponte.RAGIONABILI, (
            f"`{specie}` si accoda in {dove} e il ponte non la ragiona: ogni "
            "turno finirebbe in «nessun ramo lo ragiona piu'»")
        assert specie in ponte.JOB_SPECIES, (
            f"`{specie}` si accoda in {dove} e non ha un nome nel registro dei "
            "turni: il ponte lo spenderebbe senza che nessuno lo veda")


class _ProcessoFinto:
    """Cio' che `subprocess.run` restituirebbe, senza lanciare la CLI: una
    prova unitaria non spende un turno dell'abbonamento."""

    returncode = 1
    stdout = ""
    stderr = "la CLI non e' stata lanciata: e' una prova"


def test_un_turno_di_ATTUAZIONE_arriva_al_ponte_SENZA_strumenti(monkeypatch):
    """Sulla catena l'attuatore chiama `runner.chat` senza strumenti: sul ponte
    deve essere uguale. Non e' eleganza: col catalogo della chat avrebbe
    `execute`, la porta con cui HIRIS accende e spegne, e un attore che per
    contratto «non tocca la casa» potrebbe toccarla senza nessun si'.

    Due fatti, e servono entrambi. Che la CLI venga lanciata dice che il turno
    e' arrivato a `_reason_chat` e non al ramo della decisione vuota; che la
    sonda non giri e che nell'argv non ci sia la `--mcp-config` dice che ci e'
    arrivato senza strumenti. La spia risponde «strumenti presenti»: se fosse
    interrogata, la `--mcp-config` finirebbe davvero nell'argv.

    Mutazioni ESEGUITE: togliere `attuazione` da `RAGIONABILI` -- rossa (la
    CLI non parte); toglierla da `_SELF_CONTAINED_KINDS` -- rossa (la sonda
    gira).
    """
    lanci: list[list[str]] = []

    def cli(argv, *a, **kw):
        lanci.append(list(argv))
        return _ProcessoFinto()

    sondato = []

    def spia(*a, **kw):
        sondato.append(kw)
        return True, ""

    monkeypatch.setattr(ponte.subprocess, "run", cli)
    monkeypatch.setattr(ponte, "probe_tools", spia)

    ponte.reason(
        {"kind": "proposta", "job_id": "ja",
         "context": {"model": "sonnet", "history": [{"role": "user", "content": "le osservazioni"}],
                     "system_prompt": "sei l'attuatore",
                     "istruzione": "Rispondi SOLO con un oggetto JSON."}},
        "live", client=object(), base_url="http://127.0.0.1:8099")

    assert lanci, "il turno di attuazione non e' arrivato al ponte"
    assert sondato == [], "un turno di attuazione non ha strumenti da sondare"
    assert all("--mcp-config" not in argv for argv in lanci)
