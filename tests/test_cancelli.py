"""I cancelli della fonte unica girano davvero, dal pre-push e dalla CI.

`censimento.py` e `doppioni.py` avevano `--cancello` e non giravano da nessuna
parte. Queste prove fissano che il comando unico li lanci tutti, che un solo
no basti a fermare, e che l'hook e il workflow lo chiamino: un cancello che
esiste e che nessuno chiama e' il difetto che lo sprint ha trovato.

Mutazione ESEGUITA: tolta da `.githooks/pre-push` la riga
`python scripts/cancelli.py` -- rossa (`il pre-push non lancia i cancelli`).
Mutazione ESEGUITA: in `cancelli.run` restituito sempre 0 -- rossa
(`assert 0 == 1` nella prova del no).
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cancelli

COMMAND = "python scripts/cancelli.py"


def _launcher(codes: dict):
    """Un lanciatore finto: l'esito lo decide il primo argomento del comando,
    non l'ordine di arrivo -- i cancelli partono insieme."""
    launched = []

    def launch(command, **_):
        launched.append(command)
        return types.SimpleNamespace(returncode=codes[command[1]],
                                     stdout="uscita", stderr="")
    return launch, launched


def test_i_cancelli_passano_tutti_e_il_comando_esce_zero():
    launch, launched = _launcher({"a.py": 0, "b.py": 0, "c.py": 0})
    gates = (("uno", ("a.py",)), ("due", ("b.py",)), ("tre", ("c.py",)))
    assert cancelli.run(gates, launch=launch) == 0
    assert len(launched) == 3


def test_un_solo_no_ferma_e_chi_ha_fermato_viene_nominato(capsys):
    launch, launched = _launcher({"a.py": 0, "b.py": 1, "c.py": 0})
    gates = (("uno", ("a.py",)), ("due", ("b.py", "--cancello")), ("tre", ("c.py",)))
    assert cancelli.run(gates, launch=launch) == 1
    assert len(launched) == 3, "partono tutti: uno lento non nasconde gli altri"
    printed = capsys.readouterr().out
    assert "FERMATO da «due»" in printed
    assert "python b.py --cancello" in printed
    assert "uno passa" in printed and "tre passa" in printed


def test_ogni_cancello_dichiarato_punta_a_un_file_che_esiste():
    missing = [argument for _name, arguments in cancelli.GATES for argument in arguments
               if argument.endswith((".py", ".json")) and not (ROOT / argument).exists()]
    assert not missing, f"cancelli che nominano file inesistenti: {missing}"
    names = [name for name, _arguments in cancelli.GATES]
    assert {"registro", "doppioni", "censimento", "fonte unica"} <= set(names)


def test_il_pre_push_lancia_i_cancelli():
    hook = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    active = [line.strip() for line in hook.splitlines() if not line.strip().startswith("#")]
    # La riga intera: `python scripts/cancelli.py || true` lancerebbe i cancelli
    # e ne butterebbe via l'esito.
    assert f"{COMMAND} || {{" in active, "il pre-push non lancia i cancelli"
    index = active.index(f"{COMMAND} || {{")
    assert "exit 1" in active[index:index + 5], "un cancello che ferma non ferma il push"


def test_la_ci_lancia_i_cancelli():
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    active = [line.strip() for line in workflow.splitlines()
              if not line.strip().startswith("#")]
    assert any(line == f"run: {COMMAND}" for line in active), (
        "la CI non lancia i cancelli")
