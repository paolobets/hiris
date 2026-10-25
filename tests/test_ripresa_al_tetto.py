"""Il ponte riconosce la ripresa al tetto e dichiara il turno «troncato»
(B25; Tappa 8, Task 11).

**Il difetto, misurato.** Quando il modello si ferma al tetto di token in
uscita, la CLI del ponte non lo dice nel `stop_reason`: gli chiede da se' di
riprendere, con un evento `user` che porta `isSynthetic: true` («Output token
limit hit. Resume directly...»), fino a tre volte. Misurato il 05/10/2026 su
un server finto (CLI 2.1.286) e il 15/10/2026 sulla CLI vera (P7: CLI
2.1.300, `claude-opus-5-5`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS=300`):
- tre riprese, poi `rc` 1, `result` con `subtype: "success"` ma
  `is_error: true`, `terminal_reason: "api_error"`, `num_turns: 4`;
- il turno di controllo: `rc` 0, nessun evento sintetico, `num_turns: 1`;
- dopo una ripresa andata a buon fine (server finto, 05/10) il turno finiva
  `end_turn` e `result` portava SOLO l'ultimo pezzo: in chat la coda di una
  risposta, per un attore un JSON spezzato, e nel registro «riuscito».

**Da qui.** `read_stream` conta le riprese dal FLAG (la proprieta', non il
testo); un turno con almeno una ripresa esce `steering.TRUNCATED`, con il solo
avviso di troncatura in chat (D8 della Tappa 8: la coda e' il pezzo sbagliato
della risposta); chi raccoglie un turno del ponte passa `truncated=` al suo
lettore, che non legge una risposta troncata (D2).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

from hiris.app import steering
from hiris.app.agent import runner
from hiris.app.claude_runner import TRUNCATION_NOTICE
from hiris.app.reasoning.queue import turn_answer, turn_truncated
from tests.test_json_stream import _flusso, _init, _job, _Proc, _result

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

#: Gli stream VERI di P7 (CLI 2.1.300, `claude-opus-5-5`, 15/10/2026, dal PC
#: del proprietario: `-p --output-format stream-json --verbose
#: --strict-mcp-config --tools ""`). Turno A con
#: `CLAUDE_CODE_MAX_OUTPUT_TOKENS=300`, turno B di controllo senza. Ripuliti
#: sul PC (via `session_id`, `cwd`, `uuid`, firme del ragionamento, percorsi,
#: gli eventi `system/thinking_tokens` e qualche testo ripetuto, segnato
#: «...»); `init`, gli eventi sintetici, l'ultimo `assistant` e il `result`
#: hanno i campi come sono arrivati.
FIXTURES = Path(__file__).parent / "fixtures"
RIPRESA_VERA = FIXTURES / "stream_ripresa_cli_2_1_300.ndjson"
CONTROLLO_VERO = FIXTURES / "stream_controllo_cli_2_1_300.ndjson"


def _campione(percorso: Path) -> str:
    return percorso.read_text(encoding="utf-8")

#: Il testo della ripresa, com'e' nella CLI 2.1.300 (P7, 15/10/2026). La prova
#: non lo usa per riconoscere l'evento: lo porta perche' l'evento sia quello
#: vero.
RIPRESA = ("Output token limit hit. Resume directly — no apology, no recap of "
           "what you were doing. Pick up mid-thought if that is where the cut "
           "happened. Break remaining work into smaller pieces.")


def _assistant(testo, id_="msg_1"):
    return json.dumps({"type": "assistant",
                       "message": {"id": id_, "role": "assistant",
                                   "content": [{"type": "text", "text": testo}]}})


def _ripresa(testo=RIPRESA):
    return json.dumps({"type": "user", "isSynthetic": True,
                       "message": {"role": "user",
                                   "content": [{"type": "text", "text": testo}]}})


def _ripresa_riuscita():
    """Una ripresa andata a buon fine: il pezzo, la ripresa, la coda, e il
    `result` che porta solo la coda (la forma del 05/10/2026)."""
    return _flusso(_init(), _assistant("prima meta' della ri", "msg_1"),
                   _ripresa(), _assistant("sposta, la coda", "msg_2"),
                   _result("sposta, la coda", num_turns=2,
                           stop_reason="end_turn"))


def _reason(stdout, rc=0, kind="chat"):
    job = {**_job(), "kind": kind}
    with patch.object(runner.subprocess, "run",
                      lambda *a, **k: _Proc(rc, stdout, "")):
        return runner._reason_chat(job, "live")


# -- read_stream conta le riprese ---------------------------------------------

def test_una_ripresa_si_conta():
    """Mutazione ESEGUITA: tolto il conteggio nel ramo `user` -- rossa."""
    assert runner.read_stream(_ripresa_riuscita()).resumes == 1


def test_un_flusso_normale_ha_zero_riprese():
    e = runner.read_stream(_flusso(_init(), _assistant("tutto qui"),
                                   _result("tutto qui")))
    assert e.resumes == 0


def test_la_ripresa_si_riconosce_dal_flag_non_dal_testo():
    """Il testo della ripresa e' della CLI, e cambia da una versione
    all'altra; il flag e' la proprieta'.

    Mutazione ESEGUITA: riconoscere l'evento dal testo («Output token limit
    hit») -- rossa, perche' qui il testo e' diverso."""
    flusso = _flusso(_init(), _assistant("a"), _ripresa("Continua da dove eri."),
                     _assistant("b", "msg_2"), _result("b"))
    assert runner.read_stream(flusso).resumes == 1


def test_un_esito_di_strumento_non_e_una_ripresa():
    esito = json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
    flusso = _flusso(_init(), _assistant("a"), esito, _result("b"))
    assert runner.read_stream(flusso).resumes == 0


# -- il turno esce «troncato», con il solo avviso ----------------------------

def test_dopo_una_ripresa_riuscita_il_turno_e_troncato_e_la_coda_non_esce():
    decisione = _reason(_ripresa_riuscita())
    assert decisione["outcome"] == steering.TRUNCATED
    assert decisione["reply"] == TRUNCATION_NOTICE
    assert "la coda" not in decisione["reply"]


def test_finite_le_riprese_il_turno_e_troncato_non_fallito():
    """Lo stream VERO di P7, turno A: tre riprese, `rc` 1, `subtype`
    «success» con `is_error` vero. La causa e' il tetto, come sulla catena:
    il registro dice «troncato», e il freno lo conta.

    Mutazione ESEGUITA: il ramo della ripresa dopo quello di `rc` != 0 --
    rossa (esce «fallito» con il testo dell'errore)."""
    flusso = _campione(RIPRESA_VERA)
    assert runner.read_stream(flusso).resumes == 3
    decisione = _reason(flusso, rc=1)
    assert decisione["outcome"] == steering.TRUNCATED
    assert decisione["reply"] == TRUNCATION_NOTICE


def test_il_turno_di_controllo_vero_non_ha_riprese():
    """Lo stream VERO di P7, turno B: nessun evento sintetico, `rc` 0. Il
    `result` ripulito non porta il campo `result` (il testo della risposta,
    tolto sul PC): qui si chiede solo che il turno non risulti troncato."""
    flusso = _campione(CONTROLLO_VERO)
    assert runner.read_stream(flusso).resumes == 0
    assert _reason(flusso)["outcome"] != steering.TRUNCATED


def test_un_turno_senza_riprese_resta_riuscito():
    decisione = _reason(_flusso(_init(), _assistant("ok"), _result("ok")))
    assert decisione["outcome"] == steering.SUCCEEDED
    assert decisione["reply"] == "ok"


# -- chi raccoglie un turno del ponte non legge una risposta troncata --------

def test_la_coda_dice_se_un_turno_e_troncato():
    troncato = {"decision": {"reply": TRUNCATION_NOTICE,
                             "outcome": steering.TRUNCATED}}
    assert turn_truncated(troncato) is True
    assert turn_truncated({"decision": {"reply": "x", "outcome": "riuscito"}}) is False
    assert turn_truncated({"decision": {"reply": "x"}}) is False
    assert turn_truncated(None) is False


def _callers_of(nome: str) -> dict[str, set[str]]:
    """Per ogni funzione del prodotto che chiama `nome`: i nomi che chiama."""
    trovate: dict[str, set[str]] = {}
    for percorso in APP.rglob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for funzione in ast.walk(albero):
            if not isinstance(funzione, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            chiamati = {c.func.id if isinstance(c.func, ast.Name) else
                        c.func.attr if isinstance(c.func, ast.Attribute) else ""
                        for c in ast.walk(funzione) if isinstance(c, ast.Call)}
            if nome in chiamati:
                # `as_posix`: su Windows il percorso ha `\`, e le ammissioni
                # scritte con `/` non lo riconoscevano (Sprint, 25/10/2026).
                trovate[f"{percorso.relative_to(APP).as_posix()}::{funzione.name}"] = chiamati
    return trovate


def test_chi_legge_la_risposta_di_un_turno_del_ponte_sa_se_e_troncata():
    """L'elenco dei raccoglitori si CHIEDE al sorgente: ogni funzione che
    legge la risposta di un turno del ponte (`turn_answer`) chiede anche se
    e' troncata (`turn_truncated`), e la passa al suo lettore.

    Mutazione ESEGUITA: tolto `truncated=turn_truncated(turn)` dal
    raccoglitore dell'osservatore -- rossa."""
    lettori = _callers_of("turn_answer")
    # Una derivazione che si rompe non guarda piu' niente: i raccoglitori
    # sono, il 15/10/2026, osservatore, ricette, analista, proponente,
    # «Rifalla» e «Rendila automatica», piu' lo stato del «Rifalla».
    assert len(lettori) >= 7, sorted(lettori)
    ciechi = sorted(f for f, chiamati in lettori.items()
                    if "turn_truncated" not in chiamati and f not in AMMESSI)
    assert ciechi == []
    assert set(AMMESSI) <= set(lettori), "un'ammissione senza piu' il suo lettore"


#: Chi chiede la risposta di un turno del ponte SENZA leggerla, con la ragione.
AMMESSI = {
    "mind/proposal_redo.py::state":
        "chiede solo se la risposta c'e', per dire «fallito» o «illeggibile» "
        "a chi preme il bottone: un turno troncato ha l'avviso come testo, e "
        "risulta gia' «illeggibile» -- che e' il vero",
}


def test_un_turno_troncato_non_ha_una_risposta_da_leggere_per_un_attore():
    """Il testo resta per la chat, che lo mostra; l'attore riceve il segnale
    e non legge (D2) -- la stessa forma della catena, dove `misura_turno`
    consegna `truncated` e il testo e' l'avviso."""
    turno = {"decision": {"reply": TRUNCATION_NOTICE,
                          "outcome": steering.TRUNCATED}}
    assert turn_answer(turno) == TRUNCATION_NOTICE
    assert turn_truncated(turno) is True
