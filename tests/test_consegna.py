"""La consegna di un turno del ponte (`reasoning/consegna.py`).

Fino al 06/10/2026 queste prove passavano per `POST /api/reasoning/claim` e
`POST /api/reasoning/submit`, le due rotte con cui il lavoratore del ponte
chiamava se stesso. Le rotte sono uscite con A-23: il lavoratore prende il
turno dalla coda e lo consegna direttamente, e le prove fanno lo stesso.
"""
import pytest

from hiris.app.chat_thread import ChatThread
from hiris.app.reasoning.consegna import consegna
from hiris.app.reasoning.queue import ReasoningQueue


def _app(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    return {"reasoning_queue": q}, q


# test_claim_then_submit_executes, che viveva qui, e' cancellato dalla fetta
# E3 Task 9 (rilievo 1 della review indipendente sul blocco 5-8): wirava
# `app["execute_decision"]` e verificava che un submit non-chat lo chiamasse
# (outcome "notify"). Quell'hook e' uscito per intero -- non e' un ramo che si
# possa piu' wirare, ne' in produzione ne' nei test. Resta solo il test sotto,
# che e' l'UNICO comportamento possibile.


@pytest.mark.asyncio
async def test_consegna_non_chat_registra_e_dichiara(tmp_path, caplog):
    """fetta E3 Task 4: server.py smise di wirare app["execute_decision"] --
    la ronda/revisione olistica che lo attuava era uscita, e con lei l'unico
    produttore di job non-"chat". Una consegna non-chat puo' arrivare solo da
    un job scaduto/legacy; non deve sparire in silenzio -- resta "recorded" e
    logga un warning esplicito che nomina il job."""
    app, q = _app(tmp_path)
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info",
              "evidence": {}, "ts": 1.0}, {"snapshot": {}}, deadline_ts=100.0, job_id="J", now=1.0)
    c = q.claim(10.0)
    assert c["job_id"] == "J"

    with caplog.at_level("WARNING", logger="hiris.app.reasoning.consegna"):
        esito = await consegna(app, "J", c["nonce"], {
            "verdict": "anomalia", "severity": "info", "message": "ok", "action": None,
        }, 10.0)
    assert esito == "recorded"
    assert any("execute_decision" in rec.message and "J" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_consegna_la_risposta_anche_con_una_chiave_vecchia_nel_contesto(tmp_path):
    """fetta E4 Task 5 ("un bot solo"): la consegna non estrae piu' nessun
    chatbot_id/agent_id dal context: dalla fetta «le chat divise» la
    cronologia si sceglie col FILO del job, che sta nelle colonne della coda,
    non nel context. Qualunque chiave (o nessuna) ci sia dentro e'
    irrilevante. Il secondo argomento di `submit_chat_reply` e' il filo."""
    app, q = _app(tmp_path)
    replies = []

    async def _submit_chat_reply(reply, thread):
        replies.append(reply)
    app["submit_chat_reply"] = _submit_chat_reply
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, job_id="J", now=1.0,
              thread=ChatThread("persona:paolo", "pannello"))
    c = q.claim(10.0)
    esito = await consegna(app, "J", c["nonce"], {"reply": "ecco la risposta"}, 10.0)
    assert esito == "chat_reply_recorded"
    assert replies == ["ecco la risposta"]


@pytest.mark.asyncio
async def test_consegna_col_nonce_sbagliato_e_rifiutata(tmp_path):
    app, q = _app(tmp_path)
    q.enqueue("holistic", {}, {}, deadline_ts=100.0, job_id="J", now=1.0)
    q.claim(now=10.0)
    assert await consegna(app, "J", "bad", {}, 10.0) is None
    assert q.get("J")["status"] == "claimed"


@pytest.mark.asyncio
async def test_consegna_senza_coda_e_rifiutata(tmp_path):
    assert await consegna({}, "J", "N", {}, 10.0) is None
