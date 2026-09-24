"""«Rifalla» non preleva più in silenzio (reperto C-5b, 23/09/2026).

**Il difetto.** `steering.py` dichiara, dal 22/08/2026, che «le porte chiedono
alla stessa funzione, e una terza porta che nascesse domani non potrebbe
inventarsene una terza senza accorgersene». «Rifalla» è nata dopo, e se n'è
inventata una: chiamava `runner.chat` diretto, senza passare da `who_answers`.

Su una casa che gira **interamente sul Piano Max** — che è il caso di chi ha
scelto il forfait — ogni «Rifalla» andava alla catena, cioè a consumo, senza
che niente lo dicesse. È lo stesso difetto pagato dal vivo il 21/08 sulle
promesse, e la regola del proprietario del 13/08 è che **il passaggio dal
forfait al consumo si annuncia ogni volta**.

**Due casi distinti, e non vanno confusi.**

- Il piano *non può* rispondere (token assente, tetto pieno): è il ripiego che
  le altre porte già dichiarano, con le sue tre parole di vocabolario.
- Il piano *può* rispondere ma questa porta non lo usa: «Rifalla» risponde
  **subito** e il piano risponde in differita. Non è un guasto del piano, ed è
  una frase diversa — dire «il piano non ha risposto» sarebbe falso.

**Cosa NON si fa qui**: mandare «Rifalla» sul ponte. Sarebbe la forma giusta,
e costa una fetta sua (il bottone smette di rispondere e la pagina deve
interrogare). Sta in `docs/BACKLOG.md` con questa ragione accanto; fino ad
allora il giro si paga a consumo, e **si dice**.
"""
import json

import pytest

from hiris.app.api.handlers_proposals import handle_proposal_redo
from hiris.app.mind.store import ObservationsStore


class _Modello:
    async def chat(self, **kwargs):
        return json.dumps({"testo": "Sposta la lavatrice dopo le 14",
                           "perche": "cosi' cade nelle ore di sole"})


class _Registro:
    """Il registro degli esiti: chi ha risposto si MISURA, non si deduce."""

    def __init__(self, chi):
        self._chi = chi

    def occurrence(self, nome):
        return {"tipo": "risposto"} if nome == self._chi else None


class _Coda:
    def count_exchanges_today(self):
        return 0


def _piano_acceso(monkeypatch) -> None:
    """Il piano ha un token, quindi puo' rispondere.

    **Si finge dove la funzione viene USATA**, non dove e' definita:
    `steering` la importa per nome (`from .model_resolution import ...`),
    quindi fingere l'attributo di `model_resolution` non tocca il riferimento
    che `steering` ha gia' in mano. Fatto cosi', queste prove passavano da sole
    -- il token vero era nell'ambiente -- e cadevano dentro la suite, dove
    un'altra prova lo toglie: cioe' non provavano niente.
    """
    monkeypatch.setattr("hiris.app.steering.subscription_has_token",
                        lambda: True)


def _richiesta(app, ident, corpo):
    class _R:
        def __init__(self):
            self.app = app
            self.match_info = {"id": ident}
            self.query = {}

        async def json(self):
            return corpo
        def get(self, chiave, default=None):
            """Una `Request` vera e' una mappa: `request.get("soggetto")` e'
            come il confine passa CHI sta chiamando (sprint sicurezza, A-1).
            La finta lo deve sapere fare, o imita un contratto che non
            esiste."""
            return getattr(self, "_valori", {}).get(chiave, default)
    return _R()


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    ident = store.add_proposal(
        text="Sposta la lavatrice nel primo pomeriggio",
        perche="il prelievo si concentra la mattina",
        fingerprint="dev1|prelievo|None|1",
        prova={"base": 19}, chi_applica="tu", now_ts=100.0)
    app = {
        "observations": store,
        "llm_router": _Modello(),
        "occurrence_registry": _Registro("claude"),
        "model_chain": ["claude"],
        "reasoning_queue": _Coda(),
        "models_config": {"ponte": {"tetto_giornaliero": 50}},
        "bridge_active": False,
    }
    try:
        yield app, store, ident
    finally:
        store.close()


async def _rifai(app, ident):
    risposta = await handle_proposal_redo(
        _richiesta(app, ident, {"richiesta": "troppo presto, dopo le 14"}))
    return risposta, json.loads(risposta.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_col_piano_ACCESO_il_giro_dichiara_di_essere_passato_a_consumo(
        casa, monkeypatch):
    """**Il reperto.** Il piano e' acceso e potrebbe rispondere; «Rifalla» non
    lo usa e paga a consumo. Prima non lo diceva nessuno.

    Mutazione ESEGUITA: non chiamare `who_answers` -- rossa."""
    app, _store, ident = casa
    app["bridge_active"] = True
    _piano_acceso(monkeypatch)

    risposta, corpo = await _rifai(app, ident)

    assert risposta.status == 200
    assert corpo["nota"], "il giro e' passato a consumo e non l'ha detto"
    assert "consumo" in corpo["nota"]
    assert "Claude API" in corpo["nota"], "non dice CHI ha risposto al suo posto"


@pytest.mark.asyncio
async def test_e_NON_dice_che_il_piano_ha_fallito(casa, monkeypatch):
    """La meta' che distingue le due frasi: il piano sta benissimo, e' la porta
    che non lo usa. Una nota che dicesse «il piano non ha risposto» manderebbe
    il proprietario a cercare un guasto che non c'e' -- lo stesso difetto che
    `downgrade_note` documenta per gli avvisi di `esegui`.

    Mutazione ESEGUITA: riusare `downgrade_note` per questo caso -- rossa."""
    app, _store, ident = casa
    app["bridge_active"] = True
    _piano_acceso(monkeypatch)

    _risposta, corpo = await _rifai(app, ident)

    assert "non ha risposto" not in corpo["nota"]
    assert "subito" in corpo["nota"], (
        "non dice PERCHE' il piano non e' stato usato: risponde in differita")


@pytest.mark.asyncio
async def test_col_piano_che_NON_PUO_rispondere_si_usano_le_parole_del_ripiego(
        casa, monkeypatch):
    """Il caso gia' noto: tetto pieno. Qui la frase giusta e' quella delle
    altre porte, con le sue tre parole di vocabolario.

    Mutazione ESEGUITA: usare la frase della porta sincrona anche qui --
    rossa."""
    app, _store, ident = casa
    app["bridge_active"] = True
    app["models_config"] = {"ponte": {"tetto_giornaliero": 0}}
    _piano_acceso(monkeypatch)

    _risposta, corpo = await _rifai(app, ident)

    assert "tetto" in corpo["nota"], "non dice cosa e' successo al piano"
    assert "Claude API" in corpo["nota"]


@pytest.mark.asyncio
async def test_senza_piano_NON_si_dice_niente(casa):
    """La contropartita, e vale quanto il reperto: chi non ha mai avuto il
    piano non perde niente, e annunciarglielo a ogni giro direbbe che sta
    perdendo qualcosa che non ha.

    Mutazione ESEGUITA: scrivere la nota sempre -- rossa."""
    app, _store, ident = casa

    risposta, corpo = await _rifai(app, ident)

    assert risposta.status == 200
    assert "nota" not in corpo


@pytest.mark.asyncio
async def test_la_proposta_si_riscrive_comunque(casa, monkeypatch):
    """La dichiarazione non e' un rifiuto: il giro si fa, la proposta si
    riscrive. Togliere una funzione al proprietario per dirgli che costa
    sarebbe un'altra cosa, e non e' questa.

    Mutazione ESEGUITA: rifiutare col piano acceso -- rossa."""
    app, store, ident = casa
    app["bridge_active"] = True
    _piano_acceso(monkeypatch)

    _risposta, _corpo = await _rifai(app, ident)

    assert store.proposals()[0]["testo"] == "Sposta la lavatrice dopo le 14"
