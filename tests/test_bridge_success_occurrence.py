"""Task 6 (collaudo-3.22, `indagine-abbonamento.md`): un turno riuscito del
ponte deve lasciare una traccia in `OccurrenceRegistry` per `"subscription"`.

Prima di questa fetta l'UNICA scrittura che il ponte poteva produrre era un
fallimento per scadenza (`handlers_chat.py:477`, famiglia `scaduto`): nessun
punto del prodotto chiamava mai `.successo("subscription")`, perche' il ponte
non passa da `LLMRouter.chat()` (l'unico chiamante di `.successo(...)` prima
di questa fetta) -- lo smista `reasoning_queue.enqueue(...)` prima del router
(`handlers_chat.py:739`). Conseguenza misurata dal vivo: la pagina Modelli
diceva «non l'hai ancora usato» con 105 turni riusciti sul ponte in
`consumo_giorno` (`GET /api/usage`), l'ultimo lo stesso giorno.

Il percorso vero, dall'HTTP in giu': `POST /api/reasoning/submit` (job
`kind="chat"`) -> `handle_reasoning_submit` -> `app["submit_chat_reply"]` --
che qui e' la funzione REALE di `server._on_startup`, estratta via
`inspect.getsource` come gia' fa `test_submit_chat_reply_guards.py`, non una
copia a mano che potrebbe divergere in silenzio dal codice spedito. Nessuna
riga di questo file chiama `registry.successo(...)` a mano: se il
collegamento sparisse dal sorgente vero, il primo test qui sotto tornerebbe
rosso da solo.
"""
import inspect
import textwrap

import pytest
from aiohttp import web

from hiris.app import server
from hiris.app.api.handlers_reasoning import (
    handle_reasoning_claim,
    handle_reasoning_submit,
)
from hiris.app.chat_store import _is_toxic_assistant, append_messages
from hiris.app.provider_occurrences import OccurrenceRegistry
from hiris.app.reasoning.queue import ReasoningQueue


def _load_real_submit_chat_reply(app, data_dir):
    """Stessa estrazione di `test_submit_chat_reply_guards.py`: la funzione
    VERA di `server._on_startup`, non una copia a mano che potrebbe
    divergere dal codice spedito senza che nessun test se ne accorga."""
    src = inspect.getsource(server._on_startup)
    start = src.index(
        "    async def _submit_chat_reply(reply_text: str) -> None:")
    end_marker = ('_append_chat_messages([{"role": "assistant", '
                  '"content": reply_text}], data_dir)')
    end = src.index(end_marker, start) + len(end_marker)
    func_src = textwrap.dedent(src[start:end])

    namespace = {
        "app": app,
        "data_dir": data_dir,
        "_append_chat_messages": append_messages,
        "_is_toxic_chat_reply": _is_toxic_assistant,
    }
    exec(compile(func_src, "<_submit_chat_reply extracted from server.py>",
                 "exec"), namespace)
    return namespace["_submit_chat_reply"]


@pytest.mark.asyncio
async def test_un_turno_riuscito_del_ponte_lascia_una_traccia_nel_registro(
    aiohttp_client, tmp_path,
):
    """Accoda un job `kind="chat"` nella coda del ponte, lo reclama come
    farebbe il lavoratore in-addon, e lo consegna con una risposta pulita
    attraverso l'endpoint HTTP reale -- fino a `handle_reasoning_submit`, che
    chiama `app["submit_chat_reply"]`: qui la funzione VERA di `server.py`,
    non la riga isolata che questa fetta ha aggiunto."""
    data_dir = str(tmp_path / "data")
    registry = OccurrenceRegistry(clock=lambda: 999.0)

    app = web.Application()
    app["_clock"] = lambda: 10.0
    app["occurrence_registry"] = registry
    q = ReasoningQueue(str(tmp_path / "r.db"))
    app["reasoning_queue"] = q
    app["submit_chat_reply"] = _load_real_submit_chat_reply(app, data_dir)
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    q.enqueue("chat", {}, {"history": []}, deadline_ts=100.0, job_id="J1", now=1.0)
    client = await aiohttp_client(app)
    claimed = await (await client.post("/api/reasoning/claim")).json()
    assert claimed["job"]["job_id"] == "J1"

    r = await client.post("/api/reasoning/submit", json={
        "job_id": "J1", "nonce": claimed["job"]["nonce"],
        "decision": {"reply": "ecco la risposta del ponte"},
    })
    assert (await r.json()) == {"ok": True, "outcome": "chat_reply_recorded"}

    esito = registry.occurrence("subscription")
    assert esito is not None, (
        "un turno del ponte con una risposta vera non ha lasciato traccia: "
        "il collegamento fra il successo del ponte e OccurrenceRegistry manca")
    assert esito["tipo"] == "risposto"
    assert esito["quando"] == 999.0


@pytest.mark.asyncio
async def test_un_sentinella_di_errore_del_ponte_registra_un_fallimento(
    aiohttp_client, tmp_path,
):
    """Rovescio del test sopra: un job `kind="chat"` la cui `reply` e' uno dei
    cinque sentinella di errore del ponte (`chat_store.BRIDGE_SENTINELS`) non
    deve MAI registrare un successo -- altrimenti la correzione del Task 6
    curerebbe la bugia di Modelli («non l'hai ancora usato») sostituendola con
    la bugia opposta («ha risposto», su un turno che invece e' fallito). E'
    la ragione per cui il collegamento sta DOPO il filtro di tossicita' di
    `_submit_chat_reply` (lo stesso filtro che oggi impedisce ai sentinella di
    finire in cronologia), e non prima, dove `handle_reasoning_submit` guarda
    solo se `reply` e' non vuota.

    Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`: la
    versione precedente di questo test asseriva `occurrence(...) is None`,
    cioe' il FATTO «nessuna traccia» invece della PROPRIETA' «non e' un
    successo» -- e un domani in cui qualcuno registrasse qui il fallimento
    giusto avrebbe fatto arrossire proprio il test che doveva festeggiarlo.
    Un turno del ponte che produce un sentinella e' un turno che HA PROVATO
    ed E' FALLITO: un silenzio sul registro sarebbe la stessa bugia che il
    Task 6 aveva chiuso per la chat riuscita, spostata sul fallimento."""
    data_dir = str(tmp_path / "data")
    registry = OccurrenceRegistry(clock=lambda: 999.0)

    app = web.Application()
    app["_clock"] = lambda: 10.0
    app["occurrence_registry"] = registry
    q = ReasoningQueue(str(tmp_path / "r.db"))
    app["reasoning_queue"] = q
    app["submit_chat_reply"] = _load_real_submit_chat_reply(app, data_dir)
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    q.enqueue("chat", {}, {"history": []}, deadline_ts=100.0, job_id="J2", now=1.0)
    client = await aiohttp_client(app)
    claimed = await (await client.post("/api/reasoning/claim")).json()

    r = await client.post("/api/reasoning/submit", json={
        "job_id": "J2", "nonce": claimed["job"]["nonce"],
        "decision": {"reply": "[errore runner rc=1] boom"},
    })
    assert (await r.json()) == {"ok": True, "outcome": "chat_reply_recorded"}

    esito = registry.occurrence("subscription")
    assert esito is not None, (
        "un turno del ponte finito con un sentinella d'errore non ha lasciato "
        "traccia: il registro non distingue 'non l'ho interrogato' da "
        "'ha fallito', e Modelli dira' 'nessuna osservazione' su un turno "
        "che invece e' stato provato")
    assert esito["tipo"] == "rifiutato", (
        f"un sentinella di errore del ponte e' stato registrato come "
        f"{esito['tipo']!r} invece che come fallimento")
