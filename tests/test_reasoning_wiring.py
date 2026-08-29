def test_reasoning_routes_registered():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/reasoning/claim" in paths
    assert "/api/reasoning/submit" in paths


def test_reasoning_queue_importable():
    from hiris.app.reasoning.queue import ReasoningQueue
    assert ReasoningQueue is not None


# ── Il cablaggio di `leggi_fuso` non era sorvegliato da nessun test ─────────
#
# Review finale della fetta «il linter e le best practice», I-3: provato per
# mutazione che togliendo `leggi_fuso=lambda: _fuso_da_archivio_casa(
# archivio_casa)` dalla costruzione di `ReasoningQueue` in `server.py`,
# l'intera suite restava verde. Il gemello nello stesso commit -- la
# costruzione di `Workshop` -- quella mutazione la prende
# (`tests/test_costruzione_wiring.py::
# test_l_officina_riceve_solo_ha_e_cronaca_non_la_porta`), perche' quel test
# confronta il TESTO esatto della chiamata. Qui si sceglie una forma diversa
# apposta: un test che confronta il sorgente vedrebbe la stringa "leggi_fuso="
# comparire da qualche parte, ma non che il collaboratore FUNZIONI -- e
# questo progetto ha gia' pagato quell'errore tre volte (vedi la lezione in
# `hiris/app/server.py`, `_on_startup`, cerca "STRINGA comparisse").
#
# Il sito scoperto e' il tetto giornaliero dei turni (`ReasoningQueue.
# count_turni_oggi`), la difesa dell'abbonamento: se qualcuno toglie quel
# kwarg il giorno torna ad azzerarsi all'ora del container (UTC), non a
# mezzanotte della casa, e nessuno se ne accorge.
#
# La forma buona: uno SPY su `ReasoningQueue.__init__` che verifica che
# `leggi_fuso` arrivi davvero e che, chiamandolo, restituisca il fuso della
# casa -- non il testo della chiamata.

import inspect
import os
import textwrap

from hiris.app import server


def _estrai_costruzione_reasoning_queue():
    """Estrae dal sorgente VERO di `_on_startup` il blocco che costruisce
    `app["reasoning_queue"]` e lo esegue isolato -- stessa tecnica di
    `tests/test_schedulatore_wiring.py`. L'estrazione parte DOPO l'import
    locale (`from .reasoning.queue import ReasoningQueue`) apposta: se
    partisse prima, quell'import rimporterebbe la classe VERA e
    sovrascriverebbe lo spy passato come parametro."""
    src = inspect.getsource(server._on_startup)
    start = src.index('    reasoning_queue = ReasoningQueue(')
    end_marker = '    app["reasoning_queue"] = reasoning_queue'
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "def _check(app, data_dir, os, archivio_casa, ReasoningQueue, "
        "_fuso_da_archivio_casa):\n" + textwrap.indent(body, "    ")
    )
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup costruzione reasoning_queue>", "exec"), namespace)
    return namespace["_check"]


class _SpiaReasoningQueue:
    """Un doppio che registra COME e' stato costruito, invece di lasciare
    che un test legga il testo della chiamata. Se la finta ignorasse
    `leggi_fuso` (invece di conservarlo) nessun test potrebbe mai vedere
    l'errore -- qui lo conserva ed espone, cosi' il test puo' chiamarlo
    davvero e vedere cosa risponde."""

    ultima_istanza = None

    def __init__(self, db_path, *, leggi_fuso=None):
        self.db_path = db_path
        self.leggi_fuso = leggi_fuso
        type(self).ultima_istanza = self


def test_la_reasoning_queue_riceve_leggi_fuso_e_legge_il_fuso_della_casa(tmp_path):
    from hiris.app.casa.archivio import ArchivioCasa

    archivio_casa = ArchivioCasa(str(tmp_path / "casa.db"))
    try:
        archivio_casa.sostituisci({}, [], sistema_di_riferimento={"fuso": "Europe/Rome"})

        check = _estrai_costruzione_reasoning_queue()
        app: dict = {}
        check(app, str(tmp_path), os, archivio_casa, _SpiaReasoningQueue,
              server._fuso_da_archivio_casa)

        istanza = app["reasoning_queue"]
        assert isinstance(istanza, _SpiaReasoningQueue)
        assert istanza.leggi_fuso is not None, (
            "ReasoningQueue deve ricevere leggi_fuso -- senza, il tetto "
            "giornaliero dei turni si azzera all'ora del container invece "
            "che a mezzanotte della casa")
        # Non basta che arrivi: deve FUNZIONARE, cioe' restituire il fuso
        # vero della casa quando chiamato -- non un valore qualunque.
        assert istanza.leggi_fuso() == "Europe/Rome"
    finally:
        archivio_casa.chiudi()


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
