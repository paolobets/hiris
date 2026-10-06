"""I tetti dichiarati e il modello degli attori sul ponte (Tappa 6, Task 4).

**Il tetto.** Misurato il 05/10/2026 su `5bce65d`: l'analista chiamava
`runner.chat` SENZA `max_tokens`, e prendeva i 4.096 di fabbrica di
`claude_runner` -- un numero che nessuno aveva scelto per lui. Su 8 turni, 7 si
fermavano li' (`docs/misure/2026-10-tappa-0.md`). Lo stesso facevano
l'attuatore e il «Rifalla». D3 (approvata il 05/10/2026): il tetto si DICHIARA,
e finche' non e' misurato dal vivo vale 4.096, per iscritto -- lo stesso
comportamento, ora visibile.

**Il modello** (decisione 11 della spec). Sul ponte solo il turno di chat
portava `model`; gli altri cinque accodamenti no, e il lavoratore ripiegava
su «sonnet» (`agent/runner.py`, `context.get("model") or "sonnet"`): un
proprietario che sceglieva «opus» per il piano lo vedeva usato dalla chat e
ignorato da osservatore, ricette, analista, attuatore e promesse.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from unittest.mock import patch

from conftest import SCADENZA_LONTANA
from hiris.app import server, steering
from hiris.app.agent import runner as ponte
from hiris.app.keeper import exchange
from hiris.app.mind.store import ObservationsStore
from tests.test_agent_runner_inaddon import _ProcFelice
from tests.test_mind_analyst_turn import _serie
from tests.test_mind_observer import _casa
from tests.test_mind_recipe_turn import CASA

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


# -- il tetto ------------------------------------------------------------------

def _turn_calls() -> list[tuple[str, int, ast.Call]]:
    """Le partenze dei turni sulla catena: le chiamate di
    `steering.chain_turn`, **chieste al sorgente**. Dalla Tappa 6 (Task 7)
    e' l'unico posto che chiama `runner.chat` (`tests/test_un_turno.py`)."""
    trovate = []
    for percorso in sorted(APP.rglob("*.py")):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if (isinstance(nodo, ast.Call)
                    and (getattr(nodo.func, "id", None) == "chain_turn"
                         or getattr(nodo.func, "attr", None) == "chain_turn")):
                trovate.append((str(percorso.relative_to(APP)), nodo.lineno, nodo))
    return trovate


def test_ogni_chiamata_a_un_modello_DICHIARA_il_suo_tetto():
    """Rossa su `5bce65d` con tre chiamate: l'analista e l'attuatore in
    `server.py`, il «Rifalla» in `api/handlers_proposals.py`.

    Mutazione ESEGUITA: tolto `max_tokens=` dalla chiamata dell'analista --
    rossa, nominando `server.py`.

    Dal Task 7 la chiamata e' una sola, e il tetto e' un argomento di
    `chain_turn` **senza predefinito**: Python stesso rifiuta un turno che non
    lo dichiara. La prova guarda anche ogni partenza, per nome."""
    import inspect

    parametro = inspect.signature(steering.chain_turn).parameters["max_tokens"]
    assert parametro.kind is inspect.Parameter.KEYWORD_ONLY
    assert parametro.default is inspect.Parameter.empty
    chiamate = _turn_calls()
    # **La prova della derivazione**: su `5bce65d` le chiamate dirette erano
    # otto (piano della Tappa 6, «Misurato prima di disegnare»), e sono
    # diventate otto partenze.
    assert len(chiamate) >= 8, (
        f"la ricerca delle chiamate e' rotta: ne ha trovate {len(chiamate)}")
    senza = [f"{file}:{riga}" for file, riga, nodo in chiamate
             if not any(k.arg == "max_tokens" for k in nodo.keywords)]
    assert senza == [], f"chiamate a un modello senza tetto dichiarato: {senza}"


def test_il_tetto_dell_analista_e_quello_di_prima_SCRITTO():
    """D3: 4.096 finche' la misura dal vivo (T9) non ne sceglie un altro.
    Cambiarlo senza la misura e' un numero inventato."""
    from hiris.app.mind import actuator_turn, analyst_turn

    assert analyst_turn.MAX_ANSWER_TOKENS == 4096
    assert actuator_turn.MAX_ANSWER_TOKENS == 4096


# -- il modello degli attori sul ponte -----------------------------------------

class _Coda:
    """La coda del ponte, dal lato di chi accoda: tiene cio' che riceve."""

    def __init__(self):
        self.accodati = []

    def enqueue(self, kind, wake, context, deadline, *, now=None, thread=None,
                priority=None):
        # `priority`: la firma vera di `ReasoningQueue.enqueue` dalla Tappa 6,
        # T2 (la precedenza della chat); qui si guarda solo il modello.
        self.accodati.append({"kind": kind, "context": context})
        return "job-1"


def _app(tmp_path, modello="opus"):
    return {"reasoning_queue": _Coda(),
            "models_config": {"ponte": {"modello": modello, "scadenza_min": 5}},
            "observations": ObservationsStore(str(tmp_path / "oss.db"))}


def _accodato(app) -> dict:
    (job,) = app["reasoning_queue"].accodati
    return job["context"]


def test_l_osservatore_sul_ponte_usa_il_modello_del_proprietario(tmp_path):
    """Rossa su `5bce65d`: il job dell'osservatore non porta `model`, e il
    lavoratore usa «sonnet».

    Mutazione ESEGUITA: tolto il modello dall'accodamento dell'osservatore --
    rossa (`KeyError: 'model'`)."""
    app = _app(tmp_path)
    try:
        server._enqueue_scope_turn(app, app["observations"], _casa(),
                                   reason="prova", window_s=None,
                                   lotto={"climate.camera_t"}, annota=False,
                                   campagna_ts=0.0)
        assert _accodato(app)["model"] == "opus"
    finally:
        app["observations"].close()


def test_ricette_analista_attuatore_e_promessa_portano_il_modello(tmp_path):
    """Gli altri quattro accodamenti, uno per uno: la chat lo portava gia'
    (`handlers_chat._enqueue_chat_job`).

    Mutazione ESEGUITA: tolto il modello dall'accodamento della promessa --
    rossa, nominando «promessa»."""
    app = _app(tmp_path)
    try:
        accodamenti = {
            "ricette": lambda: server._enqueue_recipe_turn(
                app, CASA, "dev1", objective="risparmiare"),
            "analista": lambda: server._enqueue_analyst_turn(
                app, _serie(), "2026-10-05"),
            "promessa": lambda: exchange._enqueue_to_bridge(
                app, {"id": "p1", "frase": "dimmi", "domanda": "guarda"}),
        }
        for nome, accoda in accodamenti.items():
            app["reasoning_queue"].accodati.clear()
            accoda()
            assert _accodato(app).get("model") == "opus", nome

        app["reasoning_queue"].accodati.clear()
        app["observations"].replace_analysis("2026-10-05", {"osservazioni": [
            {"soggetto": "dev1", "misura": "prelievo", "chiave": None,
             "innesco": 1, "base": 3, "cosa": "sale",
             "cosa_cambierebbe": "spendere meno"}]})
        server._enqueue_actuator_turn(app, "2026-10-05")
        assert _accodato(app).get("model") == "opus", "attuatore"
    finally:
        app["observations"].close()


def test_il_modello_del_ponte_si_legge_in_UN_posto():
    """Il predefinito vive in `_STORE_DEFAULTS`: chi legge il campo non ne
    scrive un secondo."""
    from hiris.app.api.handlers_models import _STORE_DEFAULTS

    assert steering.bridge_model({}) == _STORE_DEFAULTS["ponte"]["modello"]
    assert steering.bridge_model(
        {"models_config": {"ponte": {"modello": "haiku"}}}) == "haiku"


def _job(kind="osservatore", **context):
    return {"deadline_ts": SCADENZA_LONTANA, "job_id": "J", "kind": kind,
            "context": {"system_prompt": "Sei HIRIS.",
                        "history": [{"role": "user", "content": "guarda"}],
                        "contesto": "", **context}}


def test_il_lavoratore_usa_il_modello_che_il_job_porta():
    visto = {}

    def _cli(argv, *a, **k):
        visto["argv"] = argv
        return _ProcFelice()

    with patch.object(ponte.subprocess, "run", _cli):
        ponte._reason_chat(_job(model="opus"), "live")

    argv = visto["argv"]
    assert argv[argv.index("--model") + 1] == "opus"


def test_un_job_SENZA_modello_e_un_errore_dichiarato_non_sonnet(caplog):
    """Niente ripiego: un job senza modello non ha un proprietario che
    l'abbia scelto, e «sonnet» sarebbe una scelta fatta al suo posto. Non si
    chiama la CLI, la decisione e' vuota (come per una specie sconosciuta), e
    il registro lo dice.

    Mutazione ESEGUITA: rimesso `or "sonnet"` in `agent/runner.py` -- rossa
    (la CLI parte e la decisione porta una risposta)."""
    chiamata = []

    with (patch.object(ponte.subprocess, "run",
                       lambda *a, **k: chiamata.append(a) or _ProcFelice()),
          caplog.at_level(logging.ERROR, logger="hiris.agent")):
        decisione = ponte._reason_chat(_job(), "live")

    assert decisione == {}
    assert chiamata == []
    assert any("model" in r.getMessage() for r in caplog.records)



# -- il tempo della CLI (S-09, Tappa 6, Task 8) --------------------------------

def test_la_CLI_ha_il_tempo_che_resta_al_turno():
    """Rossa su `8529b30`: `timeout=300` fisso, qualunque scadenza avesse il
    turno.

    Mutazione ESEGUITA il 06/10/2026: rimesso `timeout=300` -- rossa, 300
    contro i circa 120 secondi che restavano."""
    import time

    visto = {}

    def _cli(argv, *a, **k):
        visto["timeout"] = k.get("timeout")
        return _ProcFelice()

    adesso = time.time()
    with patch.object(ponte.subprocess, "run", _cli):
        ponte._reason_chat(_job(model="opus") | {"deadline_ts": adesso + 120}, "live")
    assert 110 < visto["timeout"] <= 120, visto


def test_un_turno_gia_scaduto_non_invoca_la_CLI():
    """La coda chiude il job alla scadenza (`sweep_expired`): una risposta
    che arrivasse dopo non la riceverebbe nessuno."""
    import time

    chiamata = []
    with patch.object(ponte.subprocess, "run",
                      lambda *a, **k: chiamata.append(a) or _ProcFelice()):
        ponte._reason_chat(_job(model="opus") | {"deadline_ts": time.time() - 1}, "live")
    assert chiamata == []


def test_un_job_SENZA_scadenza_e_un_errore_dichiarato(caplog):
    """Ogni job della coda la porta (`deadline_ts NOT NULL`): uno senza non
    viene dalla coda. Si dichiara, come il job senza modello."""
    chiamata = []
    job = _job(model="opus")
    del job["deadline_ts"]
    with (patch.object(ponte.subprocess, "run",
                       lambda *a, **k: chiamata.append(a) or _ProcFelice()),
          caplog.at_level(logging.ERROR, logger="hiris.agent")):
        decisione = ponte._reason_chat(job, "live")
    assert (decisione, chiamata) == ({}, [])
    assert any("deadline_ts" in r.getMessage() for r in caplog.records)
