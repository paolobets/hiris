"""Il guasto dell'osservatore del 09-11/10/2026 e' chiuso dalla 3.78.0 (F7,
13/10/2026).

Misurato dallo Sprint nel registro dell'add-on (3.77.0): la CLI del ponte
esce con 1 dopo il solo evento `init`, il ponte consegna il testo
`[errore runner rc=1] ...`, e l'osservatore lo legge come risposta del modello
-- «la risposta non e' un JSON leggibile (JSONDecodeError)», 20 volte. In
3.77.0 il raccoglitore dello scope leggeva `decision["reply"]` senza guardare
l'esito; dalla 3.78.0 (`d605aecb`) legge `reasoning.queue.turn_answer`, e il
ponte dichiara `outcome: "fallito"` anche sulla strada di rc diverso da zero
(`agent/runner.py`, il ritorno con `RUNNER_ERROR_PREFIX`).

Qui si prova la strada di quel giorno, rc=1 con il solo `init`, dal ponte fino
alla lettura dell'osservatore: «il modello non ha risposto», non un JSON
rotto. Le prove vicine (`test_turno_fallito_del_ponte.py`) coprono la
scadenza, non il codice d'uscita.

Mutazioni ESEGUITE il 13/10/2026, ripristino verificato con `git status`:
- in `agent/runner.py`, il ritorno con `RUNNER_ERROR_PREFIX` senza
  `outcome="fallito"` -- rossa (`'riuscito' == 'fallito'`);
- `turn_answer` che non guarda l'esito, cioe' la lettura di 3.77.0 -- rossa
  col messaggio del registro di quei giorni: «la risposta non e' un JSON
  leggibile (JSONDecodeError)» al posto di «il modello non ha risposto».
"""
from __future__ import annotations

from unittest.mock import patch

from conftest import SCADENZA_LONTANA
from hiris.app.agent import runner
from hiris.app.mind import observer
from hiris.app.reasoning.queue import ReasoningQueue, turn_answer
from hiris.app.steering import NO_ANSWER_REASON


class _InitOnly:
    """L'uscita misurata: rc=1, stderr vuoto, sullo stdout il solo `init`."""
    returncode = 1
    stdout = ('{"type":"system","subtype":"init","claude_code_version":"2.1.286",'
              '"apiKeySource":"none","mcp_servers":[]}\n')
    stderr = ""


def _job():
    return {"kind": observer.SCOPE_TURN_KIND, "deadline_ts": SCADENZA_LONTANA,
            "context": {"model": "sonnet", "system_prompt": observer.SYSTEM,
                        "history": [{"role": "user", "content": "la casa"}],
                        "istruzione": observer.ANSWER_CONTRACT}}


def test_rc_1_col_solo_init_arriva_all_osservatore_come_nessuna_risposta(tmp_path):
    with patch.object(runner.subprocess, "run", lambda *a, **k: _InitOnly()):
        decisione = runner._reason_chat(_job(), "live")
    assert decisione["reply"].startswith("[errore runner rc=1]")
    assert decisione["outcome"] == "fallito"

    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    try:
        coda.enqueue(observer.SCOPE_TURN_KIND, {}, {}, SCADENZA_LONTANA, now=1000.0)
        preso = coda.claim(1001.0)
        assert coda.submit(preso["job_id"], preso["nonce"], decisione, 1002.0)
        turno = coda.latest(observer.SCOPE_TURN_KIND)
    finally:
        coda.close()
    assert observer.read_decisions(turn_answer(turno)) == ([], NO_ANSWER_REASON)
