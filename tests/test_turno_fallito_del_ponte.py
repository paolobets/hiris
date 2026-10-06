"""Un turno che il ponte ha fallito non e' una risposta.

Misurato nel registro dell'add-on dal 05/10 13:32 al 06/10 14:05: il ponte
fallisce un turno dell'analista e risponde `[runner non disponibile]`; la coda
lo marca `decided` senza guardare l'esito; il raccoglitore lo passa alla
validazione, che lo rifiuta come «non JSON» tornando `risposta: True`; e il
giro dell'analista esce li', prima di accodare un turno nuovo. Lo stesso turno
si rileggeva e rifiutava ogni ora fino a mezzanotte.

Il ponte SA che il turno e' fallito (`outcome="fallito"`, lo stesso esito che
scrive nel registro dei turni): qui si prova che l'esito arriva fino alla coda,
e che chi raccoglie lo legge come «nessuna risposta».
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from conftest import SCADENZA_LONTANA
from hiris.app.agent import runner
from hiris.app.reasoning.queue import ReasoningQueue, turn_answer


def _job():
    return {"kind": "chat", "deadline_ts": SCADENZA_LONTANA,
            "context": {"model": "sonnet", "system_prompt": "Sei HIRIS.",
                        "history": [{"role": "user", "content": "ciao"}]}}


def test_il_ponte_dichiara_il_turno_fallito_nella_decisione():
    def _raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=300)

    with patch.object(runner.subprocess, "run", _raise_timeout):
        decisione = runner._reason_chat(_job(), "live")

    # La chat continua a ricevere il testo che riceveva.
    assert decisione["reply"] == "[runner non disponibile]"
    assert decisione["outcome"] == "fallito"


def test_un_turno_riuscito_lo_dice_anche_lui():
    class _Proc:
        returncode = 0
        stdout = ('{"type":"result","subtype":"success","is_error":false,'
                  '"result":"ciao a te"}\n')
        stderr = ""

    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        decisione = runner._reason_chat(_job(), "live")

    assert decisione["reply"] == "ciao a te"
    assert decisione["outcome"] == "riuscito"


def test_l_esito_arriva_fino_alla_coda_e_chi_raccoglie_non_vede_una_risposta(tmp_path):
    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    try:
        coda.enqueue("analista", {"giorno": "2026-10-06"}, {}, 2000.0, now=1000.0)
        preso = coda.claim(1001.0)
        assert coda.submit(preso["job_id"], preso["nonce"],
                           {"reply": "[runner non disponibile]", "tools_called": [],
                            "outcome": "fallito"}, 1002.0)
        turno = coda.latest("analista")
        assert turno["decision"]["outcome"] == "fallito"
        assert turn_answer(turno) == ""
    finally:
        coda.close()


def test_una_risposta_vera_resta_la_risposta():
    turno = {"status": "decided",
             "decision": {"reply": '{"osservazioni": []}', "outcome": "riuscito"}}
    assert turn_answer(turno) == '{"osservazioni": []}'
    # Una decisione scritta prima di questa versione non porta l'esito: si
    # legge com'era, una risposta.
    assert turn_answer({"decision": {"reply": "testo"}}) == "testo"
    assert turn_answer({"decision": None}) == ""
    assert turn_answer(None) == ""
