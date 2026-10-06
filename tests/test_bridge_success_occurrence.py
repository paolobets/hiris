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

Il percorso vero, dalla consegna in giu': `reasoning/consegna.consegna` (job
`kind="chat"`, come la chiama il lavoratore del ponte) -> `app["submit_chat_reply"]` --
che qui e' la funzione REALE che l'avvio vero pubblica (dal 03/10/2026 l'app
si avvia davvero, `tests/_avvio.py::started_with`; prima la si ritagliava dal
testo di `_on_startup`), non una copia a mano che potrebbe divergere in
silenzio dal codice spedito. Nessuna
riga di questo file chiama `registry.successo(...)` a mano: se il
collegamento sparisse dal sorgente vero, il primo test qui sotto tornerebbe
rosso da solo.
"""
import contextlib
from unittest import mock

import pytest

from hiris.app.chat_thread import ChatThread
from hiris.app.provider_occurrences import OccurrenceRegistry
from hiris.app.reasoning.consegna import consegna
from hiris.app.reasoning.queue import ReasoningQueue

# Fetta «le chat divise»: un job di chat porta il filo di chi ha scritto, e
# senza filo la consegna non scrive (`chat_reply_senza_filo`).
T = ChatThread("persona:paolo", "pannello")


@contextlib.asynccontextmanager
async def _real_submit(tmp_path, registry):
    """La consegna VERA che l'avvio pubblica in `app["submit_chat_reply"]`,
    con il registro degli esiti dell'app sostituito da `registry` (la
    consegna lo chiede all'app a ogni chiamata)."""
    from tests._avvio import started_with

    async with started_with(tmp_path / "avvio") as started:
        with mock.patch.dict(started, {"occurrence_registry": registry}):
            yield started["submit_chat_reply"]


@pytest.mark.asyncio
async def test_un_turno_riuscito_del_ponte_lascia_una_traccia_nel_registro(
    tmp_path,
):
    """Accoda un job `kind="chat"` nella coda del ponte, lo reclama come
    farebbe il lavoratore in-addon, e lo consegna con una risposta pulita
    attraverso la consegna vera -- `reasoning/consegna`, che
    chiama `app["submit_chat_reply"]`: qui la funzione VERA che l'avvio
    pubblica, non la riga isolata che questa fetta ha aggiunto.

    Mutazione ESEGUITA (03/10/2026): tolto `registry.successo("subscription")`
    dalla consegna -- rossa."""
    registry = OccurrenceRegistry(clock=lambda: 999.0)

    q = ReasoningQueue(str(tmp_path / "r.db"))
    app = {"occurrence_registry": registry, "reasoning_queue": q}

    q.enqueue("chat", {}, {"history": []}, deadline_ts=100.0, job_id="J1", now=1.0, thread=T)
    async with _real_submit(tmp_path, registry) as submit:
        app["submit_chat_reply"] = submit
        claimed = q.claim(10.0)
        assert claimed["job_id"] == "J1"
        esito_consegna = await consegna(app, "J1", claimed["nonce"],
                                        {"reply": "ecco la risposta del ponte"}, 10.0)
        assert esito_consegna == "chat_reply_recorded"

    esito = registry.occurrence("subscription")
    assert esito is not None, (
        "un turno del ponte con una risposta vera non ha lasciato traccia: "
        "il collegamento fra il successo del ponte e OccurrenceRegistry manca")
    assert esito["tipo"] == "risposto"
    assert esito["quando"] == 999.0


@pytest.mark.asyncio
async def test_un_sentinella_di_errore_del_ponte_registra_un_fallimento(
    tmp_path,
):
    """Rovescio del test sopra: un job `kind="chat"` la cui `reply` e' uno dei
    cinque sentinella di errore del ponte (`chat_store.BRIDGE_SENTINELS`) non
    deve MAI registrare un successo -- altrimenti la correzione del Task 6
    curerebbe la bugia di Modelli («non l'hai ancora usato») sostituendola con
    la bugia opposta («ha risposto», su un turno che invece e' fallito). E'
    la ragione per cui il collegamento sta DOPO il filtro di tossicita' di
    `_submit_chat_reply` (lo stesso filtro che oggi impedisce ai sentinella di
    finire in cronologia), e non prima, dove `reasoning/consegna` guarda
    solo se `reply` e' non vuota.

    Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`: la
    versione precedente di questo test asseriva `occurrence(...) is None`,
    cioe' il FATTO «nessuna traccia» invece della PROPRIETA' «non e' un
    successo» -- e un domani in cui qualcuno registrasse qui il fallimento
    giusto avrebbe fatto arrossire proprio il test che doveva festeggiarlo.
    Un turno del ponte che produce un sentinella e' un turno che HA PROVATO
    ed E' FALLITO: un silenzio sul registro sarebbe la stessa bugia che il
    Task 6 aveva chiuso per la chat riuscita, spostata sul fallimento.

    Mutazione ESEGUITA (03/10/2026): tolto il `registry.fallimento(...)` del
    ramo tossico -- rossa."""
    registry = OccurrenceRegistry(clock=lambda: 999.0)

    q = ReasoningQueue(str(tmp_path / "r.db"))
    app = {"occurrence_registry": registry, "reasoning_queue": q}

    q.enqueue("chat", {}, {"history": []}, deadline_ts=100.0, job_id="J2", now=1.0, thread=T)
    async with _real_submit(tmp_path, registry) as submit:
        app["submit_chat_reply"] = submit
        claimed = q.claim(10.0)
        assert claimed["job_id"] == "J2"
        esito_consegna = await consegna(app, "J2", claimed["nonce"],
                                        {"reply": "[errore runner rc=1] boom"}, 10.0)
        assert esito_consegna == "chat_reply_recorded"

    esito = registry.occurrence("subscription")
    assert esito is not None, (
        "un turno del ponte finito con un sentinella d'errore non ha lasciato "
        "traccia: il registro non distingue 'non l'ho interrogato' da "
        "'ha fallito', e Modelli dira' 'nessuna osservazione' su un turno "
        "che invece e' stato provato")
    assert esito["tipo"] == "rifiutato", (
        f"un sentinella di errore del ponte e' stato registrato come "
        f"{esito['tipo']!r} invece che come fallimento")
