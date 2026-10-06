def test_la_coda_dei_turni_non_si_raggiunge_via_http():
    """A-23 (06/10/2026): il lavoratore del ponte prende i turni dalla coda e
    li consegna dentro il processo. `/api/reasoning/claim` e
    `/api/reasoning/submit` sono uscite con quel giro: la prima restituiva il
    job col nucleo della casa e i ricordi, la seconda scriveva nella chat
    come risposta di HIRIS (reperto A-4 del 21/09). Una rotta che rientrasse
    riaprirebbe quella superficie senza nessuno che la usi.

    Mutazione ESEGUITA (06/10/2026): rimessa in `server.py` la riga
    `add_post("/api/reasoning/claim", ...)` -- rossa."""
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert not {p for p in paths if p.startswith("/api/reasoning")}


def test_reasoning_queue_importable():
    from hiris.app.reasoning.queue import ReasoningQueue
    assert ReasoningQueue is not None


# ── Il cablaggio di `read_timezone` non era sorvegliato da nessun test ───────────
#
# **Le tre righe qui sotto sono un VERBALE e portano i nomi di ALLORA**: quel
# giorno il kwarg si chiamava `read_timezone=`, e `read_timezone` non esisteva.
# Riportate al nome di allora il 01/09, dopo che il giro di `reasoning/` le
# aveva riscritte: una citazione che registra una misura non segue il codice,
# altrimenti la misura non e' piu' ripetibile da chi legge.
#
# Review finale della fetta «il linter e le best practice», I-3: provato per
# mutazione che togliendo `leggi_fuso=lambda: _timezone_from_home_space_store(
# archivio_casa)` dalla costruzione di `ReasoningQueue` in `server.py`,
# l'intera suite restava verde. Il gemello nello stesso commit -- la
# costruzione di `Workshop` -- quella mutazione la prende
# (`tests/test_construction_wiring.py::
# test_l_officina_riceve_solo_ha_e_cronaca_non_la_porta`), perche' quel test
# confronta il TESTO esatto della chiamata. Qui si sceglie una forma diversa
# apposta: un test che confronta il sorgente vedrebbe la stringa "read_timezone="
# comparire da qualche parte, ma non che il collaboratore FUNZIONI -- e
# questo progetto ha gia' pagato quell'errore tre volte (vedi la lezione in
# `hiris/app/server.py`, `_on_startup`, cerca "STRINGA comparisse").
#
# Il sito scoperto e' il tetto giornaliero dei turni (`ReasoningQueue.
# count_exchanges_today`), la difesa dell'abbonamento: se qualcuno toglie quel
# kwarg il giorno torna ad azzerarsi all'ora del container (UTC), non a
# mezzanotte della casa, e nessuno se ne accorge.
#
# La forma buona: guardare che `read_timezone` arrivi davvero e che,
# chiamandolo, restituisca il fuso della casa -- non il testo della chiamata.
# Dal 03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'») si guarda
# sulla coda che l'app AVVIATA ha costruito, invece di ritagliare la
# costruzione dal sorgente di `_on_startup` e rieseguirla con una spia.

import sys
from pathlib import Path

import pytest

from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte


@pytest.mark.asyncio
async def test_la_reasoning_queue_riceve_leggi_fuso_e_legge_il_fuso_della_casa(tmp_path):
    """La casa sintetica dichiara `Europe/Rome` (`ha_config.time_zone`): la coda
    dell'app avviata deve leggerlo, perche' il tetto giornaliero dei turni si
    azzeri a mezzanotte della casa e non all'ora del container.

    Mutazione ESEGUITA: tolto `read_timezone=` dalla costruzione di
    `ReasoningQueue` in `_on_startup` -- rossa."""
    inputs = synthetic_inputs()
    async with fotografia_porte.mounted(inputs, str(tmp_path)) as app:
        coda = app["reasoning_queue"]
        assert coda._read_timezone() == inputs["ha_config"]["time_zone"] == "Europe/Rome", (
            "ReasoningQueue deve ricevere read_timezone -- senza, il tetto "
            "giornaliero dei turni si azzera all'ora del container invece "
            "che a mezzanotte della casa")


# fetta E3 Task 5 (raccoglie la riserva della review E3 blocco 1, I-1):
# `_resolve_verdict` viveva qui come specchio LOCALE della risoluzione del
# verdetto che un tempo viveva in `_execute_decision` (server.py) --
# cancellata per intero dal Task 4 (101189a). Da allora
# `test_verdict_resolution_fails_closed` testava solo lo specchio, non
# poteva piu' cadere per nessuna modifica al prodotto: cancellato.
# La META' VIVA di `test_missing_verdict_decision_does_not_execute_action`
# (il fail-closed vero, dentro `watcher.executor.execute` su un verdetto
# "falso_positivo") era stata SPOSTATA in tests/test_sentinel_executor.py
# come `test_falso_positivo_verdict_skips_execution` -- quell'esecutore era
# vivo (Guardian/Sentinella, sarebbe uscito solo al Task 7), quindi il test
# si era spostato invece di morire, come impone la regola della fetta.
# fetta E3 Task 7: quel Task 7 e' questo. `watcher/executor.py` (e con lui
# tutto `watcher/`) e' uscito per intero: `test_sentinel_executor.py`
# (insieme al test spostato che portava) e' cancellato, non c'e' piu' un
# esecutore vivo a cui il fail-closed possa spostarsi di nuovo.
#
# fetta E3 Task 9 (rilievo 1 della review indipendente sul blocco 5-8):
# `test_submit_logs_exception_from_execute_decision`, che viveva qui,
# cancellato a sua volta: verificava che un `execute_decision` che solleva
# fosse loggato invece di sparire silenzioso (Fix 2). Il ramo che chiamava
# quel callable -- `ex = request.app.get("execute_decision"); if ex is not
# None: ...` -- e' uscito per intero da handlers_reasoning.py: sopravviveva
# dal Task 7 senza che nessun report lo nominasse, benche' la review del
# blocco 1 lo assegnasse "al piu' tardi col Task 7" e il Task 5 lo
# differisse qui per iscritto. Era l'ultimo punto del prodotto in cui un
# callable cablato in `app` avrebbe attuato una Decisione -- dormiente,
# cablato solo da questo test e dal suo gemello in test_reasoning_api.py,
# mai da produzione (verificato con grep esaustivo su `hiris/app`). Fatto
# cadere per costruzione prima della cancellazione: con l'hook rimosso
# l'outcome torna sempre "recorded" e il messaggio di log diventa quello
# del ramo "nessun execute_decision wired" (test_reasoning_api.py::
# test_submit_without_execute_decision_wired_records_and_logs, ancora vivo
# e ora l'UNICO comportamento possibile), non piu' "execute_decision
# failed" -- l'assert su `outcome == "error"` cadeva.
