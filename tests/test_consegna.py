"""La consegna di un turno del ponte (`reasoning/consegna.py`).

Fino al 06/10/2026 queste prove passavano per `POST /api/reasoning/claim` e
`POST /api/reasoning/submit`, le due rotte con cui il lavoratore del ponte
chiamava se stesso. Le rotte sono uscite con A-23: il lavoratore prende il
turno dalla coda e lo consegna direttamente, e le prove fanno lo stesso.
"""
import pytest

from hiris.app.chat_thread import ChatThread
from hiris.app.reasoning.consegna import SUBMIT_CHAT_REPLY_KEY, consegna
from hiris.app.reasoning.queue import REASONING_QUEUE_KEY, ReasoningQueue


def _app(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    return {REASONING_QUEUE_KEY: q}, q


# test_claim_then_submit_executes, che viveva qui, e' cancellato dalla fetta
# E3 Task 9 (rilievo 1 della review indipendente sul blocco 5-8): wirava
# `app["execute_decision"]` e verificava che un submit non-chat lo chiamasse
# (outcome "notify"). Quell'hook e' uscito per intero -- non e' un ramo che si
# possa piu' wirare, ne' in produzione ne' nei test.


def _actor_kinds() -> list[str]:
    """I turni che la consegna registra e basta: quelli degli attori, chiesti
    alla vista dei mestieri sui job (`steering.JOB_SPECIES`), meno chat e
    promessa che hanno un ramo loro. Piu' una specie che nessuno ragiona piu'
    (`holistic`): un job lasciato da un'installazione vecchia passa dallo
    stesso ramo."""
    from hiris.app.steering import JOB_SPECIES

    kinds = sorted(k for k in JOB_SPECIES if k not in ("chat", "promessa"))
    assert len(kinds) >= 4, f"la derivazione delle specie si e' rotta: {kinds!r}"
    return kinds + ["holistic"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", _actor_kinds())
async def test_la_consegna_di_un_attore_registra_e_tace(tmp_path, caplog, kind):
    """S-23 (e S-39, lo stesso difetto): fino alla Chiusura ogni consegna di
    un attore che non fosse l'osservatore scriveva un WARNING su un
    meccanismo uscito da mesi (la revisione olistica, «nessun
    execute_decision wired»). E' la consegna normale di un attore: la
    decisione resta nella coda, la raccoglie il giro che l'ha accodata, e il
    registro dell'add-on non ha niente da dire."""
    app, q = _app(tmp_path)
    q.enqueue(kind, {"giorno": "2026-10-13"}, {"snapshot": {}}, deadline_ts=100.0,
              job_id="J", now=1.0)
    c = q.claim(10.0)
    assert c["job_id"] == "J"

    with caplog.at_level("WARNING", logger="hiris.app.reasoning.consegna"):
        esito = await consegna(app, "J", c["nonce"], {"reply": "[]"}, 10.0)
    assert esito is True
    assert q.get("J")["status"] == "decided"
    assert q.get("J")["decision"] == {"reply": "[]"}
    assert [r.getMessage() for r in caplog.records] == [], (
        f"la consegna normale di un turno «{kind}» ha scritto nel registro")


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
    app[SUBMIT_CHAT_REPLY_KEY] = _submit_chat_reply
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, job_id="J", now=1.0,
              thread=ChatThread("persona:paolo", "pannello"))
    c = q.claim(10.0)
    esito = await consegna(app, "J", c["nonce"], {"reply": "ecco la risposta"}, 10.0)
    assert esito is True
    assert replies == ["ecco la risposta"]


@pytest.mark.asyncio
async def test_consegna_col_nonce_sbagliato_e_rifiutata(tmp_path):
    app, q = _app(tmp_path)
    q.enqueue("holistic", {}, {}, deadline_ts=100.0, job_id="J", now=1.0)
    q.claim(now=10.0)
    assert await consegna(app, "J", "bad", {}, 10.0) is False
    assert q.get("J")["status"] == "claimed"


@pytest.mark.asyncio
async def test_consegna_senza_coda_e_rifiutata(tmp_path):
    assert await consegna({}, "J", "N", {}, 10.0) is False
