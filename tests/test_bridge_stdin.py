"""La domanda del ponte viaggia su stdin, il prompt di sistema da un file (S-08).

Tappa 6, Task 1 (piano `piani/2026-10-tappa-6-un-turno.md`). Fino a qui la
domanda era l'argomento di `-p` e il prompt di sistema quello di
`--system-prompt`: due argomenti della riga di comando. Linux rifiuta un
SINGOLO argomento da 131.072 byte in su (`MAX_ARG_STRLEN`, 32 pagine da 4 KiB:
misurato nel contenitore della nuvola il 05/10/2026, kernel 6.18.44 -- 131.071
byte passano, 131.072 danno `OSError` errno 7, E2BIG), e il turno usciva come
«runner non disponibile». La domanda dell'analista e' arrivata a 136.822
caratteri (registro, S-08).

**La CLI non e' quella vera**: e' un programma di prova che fa cio' che la
documentazione dice della CLI fissata nel `Dockerfile` (2.1.286, verificato il
05/10/2026 su quel binario con un'API finta in locale: la domanda letta da
stdin quando `-p` non porta argomento, il prompt di sistema letto per intero
da `--system-prompt-file`), e risponde nel formato `stream-json` con cio' che
ha ricevuto. Il processo pero' parte DAVVERO: e' il solo modo di vedere il
rifiuto del kernel, che un `subprocess.run` finto non vedrebbe mai.
"""
from __future__ import annotations

import errno
import json
import os
import stat
import sys

import pytest

from conftest import SCADENZA_LONTANA
from hiris.app.agent import runner

#: La CLI finta e' uno script con la riga `#!` e la soglia e' quella del
#: kernel Linux: su Windows il sistema rifiuta di eseguirla (ENOEXEC) e i
#: permessi del file non si leggono come su POSIX. Il ponte gira solo nel
#: container dell'add-on, Linux: queste prove girano nella CI, non sul PC
#: Windows (misurato il 05/10/2026: quattro rosse per ENOEXEC).
pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="la CLI finta e' uno script POSIX col #!")

#: La soglia misurata: il primo argomento che il kernel rifiuta.
THRESHOLD = 131_072

_FAKE_CLI = '''#!{python}
import json, sys
argv = sys.argv[1:]
assert "-p" in argv
with open(argv[argv.index("--system-prompt-file") + 1], encoding="utf-8") as f:
    sistema = f.read()
domanda = sys.stdin.read()
risposta = json.dumps({{"domanda_byte": len(domanda.encode("utf-8")),
                       "sistema_byte": len(sistema.encode("utf-8")),
                       "file_sistema": argv[argv.index("--system-prompt-file") + 1],
                       "argv_byte": max(len(a.encode("utf-8")) for a in argv)}})
print(json.dumps({{"type": "system", "subtype": "init", "tools": [], "mcp_servers": []}}))
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "num_turns": 1, "result": risposta,
                  "usage": {{"input_tokens": 1, "output_tokens": 1,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0}}}}))
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    percorso = tmp_path / "claude-di-prova"
    percorso.write_text(_FAKE_CLI.format(python=sys.executable), encoding="utf-8")
    percorso.chmod(percorso.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(runner, "CLI_PONTE", str(percorso))

    # Il rifiuto del kernel si legge per NOME nel messaggio della prova: il
    # runner lo inghiotte (giustamente) in «runner non disponibile».
    rifiuti: list[str] = []
    vero = runner.subprocess.run

    def _run(*a, **k):
        try:
            return vero(*a, **k)
        except OSError as exc:
            rifiuti.append(errno.errorcode.get(exc.errno, str(exc.errno)))
            raise

    monkeypatch.setattr(runner.subprocess, "run", _run)
    return rifiuti


def _job(domanda: str, contesto: str = "") -> dict:
    return {"kind": "chat", "deadline_ts": SCADENZA_LONTANA, "job_id": "job-stdin",
            "context": {"history": [{"role": "user", "content": domanda}],
                        "system_prompt": "Sei HIRIS.", "contesto": contesto,
                        "model": "sonnet"}}


def _received(esito: dict, rifiuti: list[str]) -> dict:
    try:
        return json.loads(esito["reply"])
    except (ValueError, TypeError):
        pytest.fail(f"la CLI non ha risposto: {esito['reply']!r}; rifiuti del "
                    f"sistema operativo: {rifiuti}")


def test_question_over_threshold_reaches_cli_whole(fake_cli):
    esito = runner._reason_chat(_job("d" * THRESHOLD), "live")
    ricevuto = _received(esito, fake_cli)
    assert ricevuto["domanda_byte"] >= THRESHOLD
    assert ricevuto["argv_byte"] < THRESHOLD


def test_system_prompt_over_threshold_reaches_cli_whole(fake_cli):
    """Il nucleo entra nel prompt di sistema: su una casa grande e' lui a
    crescere, e `--system-prompt` era un argomento come `-p`."""
    esito = runner._reason_chat(_job("ciao", contesto="n" * THRESHOLD), "live")
    ricevuto = _received(esito, fake_cli)
    assert ricevuto["sistema_byte"] >= THRESHOLD
    assert ricevuto["argv_byte"] < THRESHOLD


def test_system_prompt_file_is_removed_after_invocation(fake_cli):
    """Il prompt di sistema porta il nucleo della casa: il file vive quanto
    l'invocazione, non un istante di piu'."""
    esito = runner._reason_chat(_job("ciao", contesto="la casa"), "live")
    ricevuto = _received(esito, fake_cli)
    assert not os.path.exists(ricevuto["file_sistema"])


def test_system_prompt_file_is_owner_only(fake_cli, monkeypatch):
    permessi: list[int] = []
    vero = runner.subprocess.run

    def _run(argv, *a, **k):
        file_sistema = argv[argv.index("--system-prompt-file") + 1]
        permessi.append(stat.S_IMODE(os.stat(file_sistema).st_mode))
        return vero(argv, *a, **k)

    monkeypatch.setattr(runner.subprocess, "run", _run)
    runner._reason_chat(_job("ciao"), "live")
    assert permessi == [0o600]


def test_argv_carries_neither_question_nor_system_prompt():
    argv = runner._chat_claude_args("/percorso/del/sistema.txt", "sonnet")
    assert "--system-prompt" not in argv
    assert argv[argv.index("--system-prompt-file") + 1] == "/percorso/del/sistema.txt"
    # `-p` senza argomento: subito dopo viene un'altra opzione.
    assert argv[argv.index("-p") + 1].startswith("--")
